from concurrent.futures import ThreadPoolExecutor
from threading import Event

from sqlalchemy import event

from test_itinerary_concurrency import participants
from test_membership_concurrency import concurrent_client


def test_balance_during_uncommitted_split_replacement(participants):
    client, engine, _, trip_id, ah, bh = participants
    ids = [m["user_id"] for m in client.get(f"/trips/{trip_id}/members", headers=ah).json()]
    path = f"/trips/{trip_id}"
    expense = client.post(path + "/expenses", headers=ah, json={
        "description": "Dinner", "amount": "120.00", "currency": "USD",
        "paid_by_user_id": ids[0], "participant_user_ids": ids, "expense_date": "2027-05-01",
    }).json()
    before = client.get(path + "/balances", headers=ah).json()
    split_deleted, release = Event(), Event()

    def pause_writer(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("DELETE FROM expense_splits"):
            split_deleted.set()
            assert release.wait(10)

    event.listen(engine, "after_cursor_execute", pause_writer)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            future = pool.submit(client.patch, f"{path}/expenses/{expense['id']}",
                                 headers=bh, json={"amount": "150.00"})
            try:
                assert split_deleted.wait(10)
                response = client.get(path + "/balances", headers=ah)
                assert response.status_code == 200
                assert response.json() == before
            finally:
                release.set()
            assert future.result(timeout=15).status_code == 200
    finally:
        release.set()
        event.remove(engine, "after_cursor_execute", pause_writer)
    after = client.get(path + "/balances", headers=ah)
    assert after.status_code == 200
    assert [m["balance"] for m in after.json()["members"]] == ["75.00", "-75.00"]


def test_commit_after_read_statement_does_not_change_its_snapshot(participants):
    client, engine, _, trip_id, ah, bh = participants
    ids = [m["user_id"] for m in client.get(f"/trips/{trip_id}/members", headers=ah).json()]
    path = f"/trips/{trip_id}"
    expense = client.post(path + "/expenses", headers=ah, json={
        "description": "Dinner", "amount": "120.00", "currency": "USD",
        "paid_by_user_id": ids[0], "participant_user_ids": ids, "expense_date": "2027-05-01",
    }).json()
    before = client.get(path + "/balances", headers=ah).json()
    selected, release = Event(), Event()

    def pause_reader(connection, cursor, statement, parameters, context, executemany):
        if statement.startswith("WITH balance_trip"):
            selected.set()
            assert release.wait(10)

    event.listen(engine, "after_cursor_execute", pause_reader)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            future = pool.submit(client.get, path + "/balances", headers=ah)
            try:
                assert selected.wait(10)
                changed = client.patch(f"{path}/expenses/{expense['id']}",
                                       headers=bh, json={"amount": "150.00"})
                assert changed.status_code == 200
            finally:
                release.set()
            response = future.result(timeout=15)
            assert response.status_code == 200 and response.json() == before
    finally:
        release.set()
        event.remove(engine, "after_cursor_execute", pause_reader)
    assert [m["balance"] for m in client.get(
        path + "/balances", headers=ah,
    ).json()["members"]] == ["75.00", "-75.00"]
