"""Rebuild the demo trip now: `python scripts/reset_demo.py` from backend/ with DATABASE_URL set."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import get_session_factory  # noqa: E402
from app.services.demo import ensure_demo  # noqa: E402


if __name__ == "__main__":
    with get_session_factory()() as db:
        users, trip = ensure_demo(db, reset=True)
        print(f"Demo trip #{trip.id} rebuilt for {', '.join(user.username for user in users.values())}")
