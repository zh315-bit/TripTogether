from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import logging
import os
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker

from app.core import config
from app.core.config import get_database_url
from app.main import create_app
from app.models import TripPlace
from app.services import geocoding
from app.services.geocoding import (
    FakeProvider, GeocodingService, GeocoderBusyError, GeocoderUnavailableError,
    NominatimProvider, ResultCache, UpstreamRefusedError, acquire_slot, parse_nominatim_item,
)
from test_api_contract import error_contract
from test_membership import collaboration


PREFIX = "/api/v1"
USER_AGENT = "TripTogether-tests/1.0 (tests@example.com)"
ROW = {
    "osm_type": "node", "osm_id": 123, "name": "Senso-ji",
    "display_name": "Senso-ji, 2-3-1 Asakusa, Taito, Tokyo, Japan",
    "lat": "35.7147655", "lon": "139.7966553",
}


class Upstream:
    """httpx MockTransport that records every outbound request."""

    def __init__(self, status=200, payload=None, error=None, content=None):
        self.requests = []
        self.status, self.payload, self.error, self.content = status, payload, error, content

    def __call__(self, request):
        self.requests.append(request)
        if self.error is not None:
            raise self.error
        if self.content is not None:
            return httpx.Response(self.status, content=self.content)
        return httpx.Response(self.status, json=[ROW] if self.payload is None else self.payload)

    def provider(self):
        return NominatimProvider("https://nominatim.example", USER_AGENT,
                                 transport=httpx.MockTransport(self))


# ---- Nominatim parsing ---------------------------------------------------

def test_parse_uses_stable_osm_identity_and_storage_scale():
    result = parse_nominatim_item({**ROW, "place_id": 999})
    assert result.provider == "nominatim" and result.provider_place_id == "N123"
    assert result.name == "Senso-ji" and result.address == ROW["display_name"]
    # Seven upstream decimals are rounded half-even to Numeric(9,6).
    assert result.latitude == Decimal("35.714766") and result.longitude == Decimal("139.796655")
    for osm_type, prefix in (("way", "W"), ("relation", "R")):
        assert parse_nominatim_item({**ROW, "osm_type": osm_type}).provider_place_id == f"{prefix}123"


def test_parse_falls_back_to_first_display_segment():
    assert parse_nominatim_item({**ROW, "name": " "}).name == "Senso-ji"
    long = parse_nominatim_item({**ROW, "name": "x" * 300, "display_name": "y" * 600})
    assert len(long.name) == 200 and len(long.address) == 500


@pytest.mark.parametrize("changes", [
    {"osm_type": "area"}, {"osm_type": None}, {"osm_id": 0}, {"osm_id": "123"}, {"osm_id": True},
    {"display_name": None}, {"display_name": " ", "name": None},
    {"lat": "91"}, {"lon": "-180.000001"}, {"lat": "NaN"}, {"lat": "Infinity"},
    {"lat": 35.7}, {"lat": "north"}, {"lon": None},
])
def test_parse_skips_unusable_rows(changes):
    assert parse_nominatim_item({**ROW, **changes}) is None
    assert parse_nominatim_item("not an object") is None


# ---- Nominatim transport -------------------------------------------------

def test_request_identifies_app_and_never_autocompletes():
    upstream = Upstream(payload=[ROW, {**ROW, "lat": "1"}, {**ROW, "osm_id": 456}, {"bad": 1}])
    results = upstream.provider().search("Senso-ji Tokyo", 5)
    request, = upstream.requests
    assert request.url.host == "nominatim.example" and request.url.path == "/search"
    assert dict(request.url.params) == {
        "q": "Senso-ji Tokyo", "format": "jsonv2", "limit": "5", "addressdetails": "0",
    }
    assert request.headers["user-agent"] == USER_AGENT
    # Duplicate OSM objects collapse to the first row; malformed rows are skipped.
    assert [r.provider_place_id for r in results] == ["N123", "N456"]
    assert upstream.provider().search("x", 1) and len(upstream.provider().search("x", 1)) == 1


@pytest.mark.parametrize("status", [403, 429])
def test_refusal_is_distinguished_for_cooldown(status):
    with pytest.raises(UpstreamRefusedError):
        Upstream(status=status).provider().search("Tokyo", 5)


@pytest.mark.parametrize("upstream", [
    Upstream(status=500), Upstream(status=302), Upstream(status=404),
    Upstream(content=b"not json"), Upstream(payload={"error": "x"}),
    Upstream(error=httpx.ConnectTimeout("slow")), Upstream(error=httpx.ReadTimeout("slow")),
    Upstream(error=httpx.ConnectError("down")),
])
def test_transport_failures_are_unavailable_without_retry(upstream):
    with pytest.raises(GeocoderUnavailableError):
        upstream.provider().search("Tokyo", 5)
    assert len(upstream.requests) == 1


def test_timeouts_are_bounded():
    client = Upstream().provider()._client
    assert client.timeout.connect == 3.0 and client.timeout.read == 5.0
    assert client.follow_redirects is False


# ---- Cache and fake provider ---------------------------------------------

def test_cache_expires_and_evicts_least_recent():
    now = [0.0]
    cache = ResultCache(ttl_seconds=10, max_entries=2, clock=lambda: now[0])
    cache.put(("a",), ())
    cache.put(("b",), ())
    assert cache.get(("a",)) == ()
    cache.put(("c",), ())
    assert cache.get(("b",)) is None and cache.get(("a",)) == ()
    now[0] = 10
    assert cache.get(("a",)) is None and cache.get(("c",)) is None


def test_fake_provider_is_offline_and_deterministic():
    assert [r.name for r in FakeProvider().search("tokyo", 2)] == ["Senso-ji", "Tokyo Tower"]
    assert FakeProvider().search("nowhere", 5) == []
    assert FakeProvider().throttled is False and NominatimProvider.throttled is True


# ---- Configuration -------------------------------------------------------

@pytest.fixture
def geocoder_env(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "ENV_FILE", tmp_path / "absent.env")
    for name in ("APP_ENV", "GEOCODER_PROVIDER", "GEOCODER_USER_AGENT", "GEOCODER_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    geocoding.get_geocoding_service.cache_clear()
    yield monkeypatch
    geocoding.get_geocoding_service.cache_clear()


def test_disabled_by_default(geocoder_env):
    assert config.get_geocoder_settings().provider == "disabled"
    assert geocoding.get_geocoding_service().provider is None


@pytest.mark.parametrize("env", [
    {"GEOCODER_PROVIDER": "google"},
    {"GEOCODER_PROVIDER": "fake", "APP_ENV": "production"},
    {"GEOCODER_PROVIDER": "nominatim"},
    {"GEOCODER_PROVIDER": "nominatim", "GEOCODER_USER_AGENT": "short"},
    {"GEOCODER_PROVIDER": "nominatim", "GEOCODER_USER_AGENT": "python-httpx/0.28.1"},
    {"GEOCODER_PROVIDER": "nominatim",
     "GEOCODER_USER_AGENT": "TripTogether/1.0 (contact: you@example.com)"},
    {"GEOCODER_PROVIDER": "nominatim", "GEOCODER_USER_AGENT": "TripTogether\ttests (x@example.com)"},
    {"GEOCODER_PROVIDER": "nominatim", "GEOCODER_USER_AGENT": USER_AGENT,
     "GEOCODER_BASE_URL": "http://nominatim.example", "APP_ENV": "production"},
    {"GEOCODER_PROVIDER": "nominatim", "GEOCODER_USER_AGENT": USER_AGENT,
     "GEOCODER_BASE_URL": "https://user:pw@nominatim.example"},
    {"GEOCODER_PROVIDER": "nominatim", "GEOCODER_USER_AGENT": USER_AGENT,
     "GEOCODER_BASE_URL": "ftp://nominatim.example"},
])
def test_invalid_configuration_rejected_and_service_fails_closed(geocoder_env, env, caplog):
    for name, value in env.items():
        geocoder_env.setenv(name, value)
    with pytest.raises(ValueError):
        config.get_geocoder_settings()
    assert geocoding.get_geocoding_service().provider is None
    assert "Geocoder configuration invalid" in caplog.text


def test_valid_nominatim_configuration(geocoder_env):
    geocoder_env.setenv("APP_ENV", "production")
    geocoder_env.setenv("GEOCODER_PROVIDER", "nominatim")
    geocoder_env.setenv("GEOCODER_USER_AGENT", USER_AGENT)
    settings = config.get_geocoder_settings()
    assert settings.base_url == "https://nominatim.openstreetmap.org"
    assert isinstance(geocoding.build_provider(settings), NominatimProvider)


def test_production_startup_rejects_invalid_geocoder(geocoder_env, jwt_environment):
    geocoder_env.setenv("APP_ENV", "production")
    geocoder_env.setenv("CORS_ORIGINS", "[]")
    geocoder_env.setenv("DATABASE_URL", "postgresql+psycopg://user:placeholder@localhost/db")
    geocoder_env.setenv("GEOCODER_PROVIDER", "nominatim")
    with pytest.raises(RuntimeError, match="Production configuration invalid"):
        with TestClient(create_app()):
            pass


def test_httpx_request_logging_is_suppressed():
    from app.core.logging import configure_logging
    configure_logging()
    assert not logging.getLogger("httpx").isEnabledFor(logging.INFO)


# ---- Endpoint and shared throttle ----------------------------------------

@pytest.fixture
def geocode_api(collaboration):
    from app.main import app
    client, conn, _, users, _ = collaboration
    services = {}

    def use(service):
        services["current"] = service
        app.dependency_overrides[geocoding.get_geocoding_service] = lambda: services["current"]
        return service

    try:
        yield client, conn, users["alice"][1], use
    finally:
        app.dependency_overrides.pop(geocoding.get_geocoding_service, None)


def search(client, headers, q, **params):
    return client.get(PREFIX + "/geocode", headers=headers, params={"q": q, **params})


def test_fake_search_contract(geocode_api):
    client, _, headers, use = geocode_api
    use(GeocodingService(FakeProvider()))
    response = search(client, headers, "  Tokyo   Tower ", limit=3)
    assert response.status_code == 200
    assert response.json() == [{
        "provider": "fake", "provider_place_id": "W1000002", "name": "Tokyo Tower",
        "address": "4-2-8 Shibakoen, Minato, Tokyo, Japan",
        "latitude": 35.658581, "longitude": 139.745433,
    }]
    assert search(client, headers, "nowhere").json() == []


@pytest.mark.parametrize("params", [
    {"q": "a"}, {"q": "  a  "}, {"q": "x" * 201}, {"q": "ab\x00"}, {},
    {"q": "Tokyo", "limit": 0}, {"q": "Tokyo", "limit": 11}, {"q": "Tokyo", "limit": "x"},
])
def test_query_validation(geocode_api, params):
    client, _, headers, use = geocode_api
    use(GeocodingService(FakeProvider()))
    error_contract(client.get(PREFIX + "/geocode", headers=headers, params=params),
                   422, "VALIDATION_ERROR")


def test_disabled_switch(geocode_api):
    client, _, headers, use = geocode_api
    use(GeocodingService(None))
    error_contract(search(client, headers, "Tokyo"), 503, "GEOCODER_DISABLED")


def test_global_throttle_cache_and_recovery(geocode_api):
    client, conn, headers, use = geocode_api
    upstream = Upstream()
    use(GeocodingService(upstream.provider()))
    first = search(client, headers, "Senso-ji")
    assert first.status_code == 200 and first.json()[0]["provider_place_id"] == "N123"
    busy = search(client, headers, "Tokyo Tower")
    error_contract(busy, 429, "GEOCODER_BUSY")
    assert busy.headers["retry-after"] == "1"
    # Cached queries (whitespace/case-insensitive) skip both throttle and upstream.
    assert search(client, headers, " senso-JI ").json() == first.json()
    assert len(upstream.requests) == 1
    conn.execute(text("UPDATE geocoder_throttle SET next_allowed_at = '-infinity'"))
    assert search(client, headers, "Tokyo Tower").status_code == 200
    assert len(upstream.requests) == 2


def test_upstream_refusal_starts_shared_cooldown(geocode_api, caplog):
    client, conn, headers, use = geocode_api
    refused = Upstream(status=429)
    use(GeocodingService(refused.provider()))
    error_contract(search(client, headers, "private search text"), 503, "GEOCODER_UNAVAILABLE")
    remaining = conn.scalar(text(
        "SELECT extract(epoch FROM next_allowed_at - clock_timestamp()) FROM geocoder_throttle"
    ))
    assert 50 < remaining <= 60
    # Another provider instance (another worker) still sees the cooldown.
    healthy = Upstream()
    use(GeocodingService(healthy.provider()))
    error_contract(search(client, headers, "Tokyo"), 429, "GEOCODER_BUSY")
    assert healthy.requests == [] and len(refused.requests) == 1
    assert "private search text" not in caplog.text
    assert "refused" in caplog.text


def test_failures_are_not_cached(geocode_api):
    client, conn, headers, use = geocode_api
    upstream = Upstream(error=httpx.ConnectError("down"))
    use(GeocodingService(upstream.provider()))
    error_contract(search(client, headers, "Tokyo"), 503, "GEOCODER_UNAVAILABLE")
    upstream.error = None
    conn.execute(text("UPDATE geocoder_throttle SET next_allowed_at = '-infinity'"))
    assert search(client, headers, "Tokyo").status_code == 200
    assert len(upstream.requests) == 2


def test_missing_throttle_row_fails_closed(geocode_api):
    client, conn, headers, use = geocode_api
    upstream = Upstream()
    use(GeocodingService(upstream.provider()))
    conn.execute(text("DELETE FROM geocoder_throttle"))
    error_contract(search(client, headers, "Tokyo"), 429, "GEOCODER_BUSY")
    assert upstream.requests == []


def test_throttle_migration_seed(migrated_database):
    conn, _ = migrated_database
    # psycopg cannot load -infinity as a datetime, so compare in SQL.
    assert conn.execute(text(
        "SELECT id, next_allowed_at = '-infinity'::timestamptz FROM geocoder_throttle"
    )).all() == [(1, True)]
    with pytest.raises(Exception):
        with conn.begin_nested():
            conn.execute(text("INSERT INTO geocoder_throttle VALUES (2, now())"))


@pytest.fixture
def independent_sessions():
    """Committed schema so each thread uses its own connection, like separate workers."""
    if os.environ.get("RUN_POSTGRES_TESTS") != "1":
        pytest.skip("Set RUN_POSTGRES_TESTS=1 with real PostgreSQL.")
    schema = "test_geocoder_" + uuid4().hex
    admin = create_engine(get_database_url())
    engine = None
    try:
        with admin.begin() as connection:
            connection.execute(text(f'CREATE SCHEMA "{schema}"'))
        engine = create_engine(get_database_url(), connect_args={
            "options": f"-csearch_path={schema} -clock_timeout=5000 -cstatement_timeout=10000",
        })
        with engine.begin() as connection:
            alembic = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
            alembic.attributes["connection"] = connection
            command.upgrade(alembic, "head")
        yield sessionmaker(engine)
    finally:
        if engine is not None:
            engine.dispose()
        # This random private schema belongs solely to this test, never public.
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE'))
        admin.dispose()


def test_simultaneous_workers_get_exactly_one_slot(independent_sessions):
    workers = 8
    barrier = Barrier(workers, timeout=10)

    def claim():
        with independent_sessions() as db:
            barrier.wait()
            return acquire_slot(db)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = [future.result(timeout=20) for future in [pool.submit(claim) for _ in range(workers)]]
    assert results.count(True) == 1


# ---- Saving search results as places -------------------------------------

def test_search_results_save_unchanged(geocode_api, collaboration):
    # Regression: fake results (provider "fake") were rejected with 422 on save.
    client, _, headers, use = geocode_api
    trip = collaboration[4]
    use(GeocodingService(FakeProvider()))
    result, = search(client, headers, "Senso-ji").json()
    created = client.post(f"{PREFIX}/trips/{trip['id']}/places", headers=headers, json=result)
    assert created.status_code == 201, created.text
    assert {key: created.json()[key] for key in result} == result
    error_contract(client.post(f"{PREFIX}/trips/{trip['id']}/places", headers=headers, json=result),
                   409, "PLACE_DUPLICATE")


def test_saved_search_result_is_deduplicated_per_trip(geocode_api, collaboration):
    client, conn, _, users, trip = collaboration
    ah = users["alice"][1]
    geocode_api[3](GeocodingService(Upstream().provider()))
    path = f"{PREFIX}/trips/{trip['id']}/places"
    body = {"name": "Senso-ji", "latitude": 35.714766, "longitude": 139.796655,
            "provider": "nominatim", "provider_place_id": "N123"}
    created = client.post(path, headers=ah, json=body)
    assert created.status_code == 201
    assert created.json()["provider"] == "nominatim"
    assert created.json()["provider_place_id"] == "N123"
    error_contract(client.post(path, headers=ah, json=body), 409, "PLACE_DUPLICATE")
    other = client.post("/trips", headers=ah, json={
        "name": "Other", "destination": "Tokyo", "start_date": "2027-06-10", "end_date": "2027-06-11",
    }).json()
    assert client.post(f"{PREFIX}/trips/{other['id']}/places", headers=ah, json=body).status_code == 201
    # Manual places never collide with each other.
    manual = {"name": "Hotel", "latitude": 35.7, "longitude": 139.8}
    assert all(client.post(path, headers=ah, json=manual).status_code == 201 for _ in range(2))
    assert conn.scalar(text("SELECT count(*) FROM trip_places WHERE provider = 'manual'")) == 2


@pytest.mark.parametrize("changes", [
    {"provider": "nominatim"}, {"provider_place_id": "N123"},
    {"provider": "manual", "provider_place_id": "N123"},
    {"provider": "google", "provider_place_id": "N123"},
    {"provider": "nominatim", "provider_place_id": "X123"},
    {"provider": "nominatim", "provider_place_id": "N0"},
    {"provider": "nominatim", "provider_place_id": "n123"},
    {"provider": "nominatim", "provider_place_id": "N" + "1" * 21},
    {"provider": None, "provider_place_id": "N123"},
])
def test_provider_identity_validation(collaboration, changes):
    client, conn, _, users, trip = collaboration
    body = {"name": "Senso-ji", "latitude": 35.7, "longitude": 139.8, **changes}
    error_contract(client.post(f"{PREFIX}/trips/{trip['id']}/places",
                               headers=users["alice"][1], json=body), 422, "VALIDATION_ERROR")
    assert conn.scalar(select(TripPlace.id)) is None


# ---- Saved provider must match the active geocoder -----------------------

NOMINATIM_RESULT = {"name": "Senso-ji", "latitude": 35.714766, "longitude": 139.796655,
                    "provider": "nominatim", "provider_place_id": "N123"}
FAKE_RESULT = {**NOMINATIM_RESULT, "provider": "fake", "provider_place_id": "N1000001"}
MANUAL_PLACE = {"name": "Hotel", "latitude": 35.69, "longitude": 139.70}


def test_production_configuration_rejects_fake_results(collaboration, geocoder_env):
    # No dependency override: the service is built from real production-style env.
    geocoder_env.setenv("APP_ENV", "production")
    geocoder_env.setenv("GEOCODER_PROVIDER", "nominatim")
    geocoder_env.setenv("GEOCODER_USER_AGENT", USER_AGENT)
    client, conn, _, users, trip = collaboration
    path = f"{PREFIX}/trips/{trip['id']}/places"
    body = error_contract(client.post(path, headers=users["alice"][1], json=FAKE_RESULT),
                          422, "VALIDATION_ERROR")
    assert body["details"] == [{
        "loc": ["body", "provider"], "type": "value_error",
        "msg": "provider must match the configured place search (nominatim); omit provider for a manual place",
    }]
    assert conn.scalar(text("SELECT count(*) FROM trip_places")) == 0
    assert client.post(path, headers=users["alice"][1], json=NOMINATIM_RESULT).status_code == 201
    assert client.post(path, headers=users["alice"][1], json=MANUAL_PLACE).status_code == 201


def test_development_fake_configuration_saves_fake_results(collaboration, geocoder_env):
    geocoder_env.setenv("GEOCODER_PROVIDER", "fake")
    client, _, _, users, trip = collaboration
    path = f"{PREFIX}/trips/{trip['id']}/places"
    created = client.post(path, headers=users["alice"][1], json=FAKE_RESULT)
    assert created.status_code == 201 and created.json()["provider"] == "fake"
    error_contract(client.post(path, headers=users["alice"][1], json=NOMINATIM_RESULT), 422, "VALIDATION_ERROR")


def test_disabled_search_allows_manual_places_only(geocode_api, collaboration):
    client, conn, headers, use = geocode_api
    trip = collaboration[4]
    path = f"{PREFIX}/trips/{trip['id']}/places"
    use(GeocodingService(Upstream().provider()))
    saved = client.post(path, headers=headers, json=NOMINATIM_RESULT).json()
    # The operator turns search off: new imported rows are refused...
    use(GeocodingService(None))
    for result in (NOMINATIM_RESULT, {**FAKE_RESULT, "provider_place_id": "N9"}):
        body = error_contract(client.post(path, headers=headers, json=result), 422, "VALIDATION_ERROR")
        assert "(disabled)" in body["details"][0]["msg"]
    manual = client.post(path, headers=headers, json=MANUAL_PLACE)
    assert manual.status_code == 201 and manual.json()["provider"] == "manual"
    # ...while existing imported places stay readable, editable and deletable.
    assert [place["id"] for place in client.get(path, headers=headers).json()] == [saved["id"], manual.json()["id"]]
    renamed = client.patch(f"{path}/{saved['id']}", headers=headers, json={"name": "Asakusa"})
    assert renamed.status_code == 200 and renamed.json()["provider"] == "nominatim"
    assert client.delete(f"{path}/{saved['id']}", headers=headers).status_code == 204


def test_provider_policy_is_not_a_database_constraint(migrated_database):
    conn, _ = migrated_database
    constraints = conn.execute(text(
        "SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE conrelid = 'trip_places'::regclass AND contype = 'c'"
    )).all()
    assert not any("nominatim" in definition or "fake" in definition for _, definition in constraints)
