"""Opt-in real frontend/FastAPI/PostgreSQL smoke, without printing credentials."""
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from uuid import uuid4

import httpx
from sqlalchemy import delete, select

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.db.session import get_engine  # noqa: E402
from app.models import User  # noqa: E402


def main():
    identity = uuid4().hex
    username = "step13_" + identity
    email = "step13_" + identity + "@example.com"
    engine = get_engine()
    # Verify the development schema exists before starting or creating any user.
    with engine.connect() as connection:
        connection.execute(select(User.id).limit(1))
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    origin = "http://127.0.0.1:5173"
    base = f"http://127.0.0.1:{port}"
    environment = {
        **os.environ, "APP_ENV": "development",
        "JWT_SECRET_KEY": secrets.token_urlsafe(48),
        "CORS_ORIGINS": f'["{origin}"]',
    }
    server = None
    result = 1
    try:
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app",
             "--host", "127.0.0.1", "--port", str(port)],
            cwd=ROOT / "backend", env=environment,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        with httpx.Client(base_url=base, timeout=5, trust_env=False) as client:
            for _ in range(50):
                if server.poll() is not None:
                    raise RuntimeError("Temporary backend failed to start.")
                try:
                    if client.get("/ready").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(0.1)
            else:
                raise RuntimeError("Temporary backend did not become ready.")
            preflight = client.options("/api/v1/auth/me", headers={
                "Origin": origin, "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            })
            if preflight.status_code != 200 or preflight.headers.get("access-control-allow-origin") != origin:
                raise RuntimeError("CORS preflight failed.")
            print("Temporary backend ready; PostgreSQL and Bearer CORS verified.", flush=True)
        test_environment = {
            **os.environ, "RUN_AUTH_INTEGRATION": "1", "AUTH_TEST_BASE_URL": base,
            "AUTH_TEST_USERNAME": username, "AUTH_TEST_EMAIL": email,
        }
        result = subprocess.run(
            ["npm", "test", "--", "src/auth/realAuth.test.tsx"],
            cwd=ROOT / "frontend", env=test_environment,
        ).returncode
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait()
        # The exact generated identity belongs to this run; never delete by prefix.
        with engine.begin() as connection:
            removed = connection.execute(delete(User).where(
                User.username == username, User.email == email,
            )).rowcount
        engine.dispose()
        print(f"Temporary user cleanup: {removed} row(s); temporary backend stopped.", flush=True)
    return result


if __name__ == "__main__":
    try:
        code = main()
    except Exception:
        print("Auth integration failed. Check local PostgreSQL schema and permissions.", file=sys.stderr)
        code = 1
    raise SystemExit(code)
