from decimal import Decimal, localcontext
from random import Random

import pytest

from app.services.balances import InconsistentLedgerError, suggest_settlements


@pytest.mark.parametrize("values,expected", [
    (["60", "-60"], [(2, 1, "60")]),
    (["170", "-40", "-130"], [(3, 1, "130"), (2, 1, "40")]),
    (["80", "20", "-50", "-50"], [(3, 1, "50"), (4, 1, "30"), (4, 2, "20")]),
    (["0", "0"], []), ([], []), (["0"], []),
    (["0.01", "-0.01"], [(2, 1, "0.01")]),
    (["66.66", "-33.33", "-33.33"], [(2, 1, "33.33"), (3, 1, "33.33")]),
])
def test_examples(values, expected):
    balances = {i: Decimal(value) for i, value in enumerate(values, 1)}
    original = dict(balances)
    result = suggest_settlements(balances)
    assert [(s.from_user_id, s.to_user_id, s.amount) for s in result] == [
        (debtor, creditor, Decimal(amount)) for debtor, creditor, amount in expected
    ]
    assert balances == original
    assert suggest_settlements(dict(reversed(list(balances.items())))) == result
    for suggestion in result:
        assert isinstance(suggestion.amount, Decimal)
        assert suggestion.amount > 0
        assert suggestion.from_user_id != suggestion.to_user_id
        balances[suggestion.from_user_id] += suggestion.amount
        balances[suggestion.to_user_id] -= suggestion.amount
        assert suggestion.model_dump(mode="json")["amount"] == format(suggestion.amount, ".2f")
    assert all(value == 0 for value in balances.values())


def test_conservation_many_inputs():
    random = Random(10)
    for size in range(2, 52):
        units = [random.randint(-100000, 100000) for _ in range(size - 1)]
        units.append(-sum(units))
        balances = {i: Decimal(value).scaleb(-2) for i, value in enumerate(units, 1)}
        final = dict(balances)
        result = suggest_settlements(balances)
        assert sum((s.amount for s in result), Decimal(0)) == sum(
            (value for value in balances.values() if value > 0), Decimal(0),
        )
        for suggestion in result:
            assert suggestion.amount > 0
            assert suggestion.from_user_id != suggestion.to_user_id
            final[suggestion.from_user_id] += suggestion.amount
            final[suggestion.to_user_id] -= suggestion.amount
        assert all(value == 0 for value in final.values())
        assert len(result) <= size - 1
        assert result == suggest_settlements(dict(reversed(list(balances.items()))))


@pytest.mark.parametrize("value", [
    1.0, 1, "1", True, Decimal("NaN"), Decimal("sNaN"), Decimal("Infinity"),
    Decimal("-Infinity"), Decimal("0.001"), Decimal("1.00"),
])
def test_invalid_or_unbalanced_input_fails_closed(value):
    with pytest.raises(InconsistentLedgerError):
        suggest_settlements({1: value})


def test_large_totals_are_not_limited_to_expense_amount_or_ambient_precision():
    value = Decimal("123456789012345678901234567890.01")
    with localcontext() as context:
        context.prec = 6
        result = suggest_settlements({1: value, 2: value.copy_negate()})
    assert result[0].amount == value
