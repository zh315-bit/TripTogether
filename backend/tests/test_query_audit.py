from sqlalchemy import event
import pytest

from test_itinerary import add, shared, collaboration, invite


@pytest.mark.parametrize("changed", [False, True])
def test_reorder_does_not_reload_each_item_after_commit(shared, changed):
    client, connection, _, users, trip = shared
    items = [add(shared, title=f"Item {i}") for i in range(10)]
    statements = []

    def capture(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("SELECT"):
            statements.append(statement)

    event.listen(connection, "before_cursor_execute", capture)
    try:
        response = client.patch(f"/trips/{trip['id']}/itinerary/reorder",
                                headers=users["alice"][1], json={
                                    "date": "2027-06-10",
                                    "item_ids": [item["id"] for item in (items[::-1] if changed else items)],
                                })
    finally:
        event.remove(connection, "before_cursor_execute", capture)
    assert response.status_code == 200
    assert len(statements) == 4  # User, locked Trip, day, bulk final snapshot.


@pytest.mark.parametrize("size", [1, 10])
def test_collection_queries_are_constant(shared, size):
    client, connection, _, users, trip = shared
    ah = users["alice"][1]
    ids = [user[0]["id"] for name, user in users.items() if name != "charlie"]
    base = f"/api/v1/trips/{trip['id']}"
    for index in range(size):
        add(shared, title=f"Item {index}")
        assert client.post(base + "/expenses", headers=ah, json={
            "description": "Dinner", "amount": "100.00", "currency": "USD",
            "paid_by_user_id": ids[0], "participant_user_ids": ids, "expense_date": "2027-05-01",
        }).status_code == 201
    for path, expected in [
        ("/api/v1/trips", 2), (base + "/members", 3), (base + "/itinerary", 3),
        (base + "/expenses", 3), (base + "/balances", 2),
    ]:
        queries = []
        def capture(conn, cursor, statement, parameters, context, executemany):
            if statement.startswith(("SELECT", "WITH")):
                queries.append(statement)
        event.listen(connection, "before_cursor_execute", capture)
        try:
            response = client.get(path, headers=ah)
        finally:
            event.remove(connection, "before_cursor_execute", capture)
        assert response.status_code == 200
        assert len(queries) == expected
