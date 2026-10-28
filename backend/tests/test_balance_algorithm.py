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


@pytest.mark.parametrize("values,expected", [
    # Greedy would pay the 6 and the 5 from three debtors in four transfers;
    # splitting into {6, -3, -3} and {5, -5} settles in three.
    (["6", "5", "-3", "-3", "-5"], [(3, 1, "3"), (4, 1, "3"), (5, 2, "5")]),
    # Two independent pairs stay independent even when amounts interleave.
    (["10", "-7", "7", "-10"], [(4, 1, "10"), (2, 3, "7")]),
    # Three zero-sum pairs: three transfers, not five.
    (["1", "-1", "2", "-2", "3", "-3"], [(2, 1, "1"), (4, 3, "2"), (6, 5, "3")]),
    # Cents matter: {6.01, -3, -3.01} is a group of its own, so three transfers.
    (["6.01", "5", "-3", "-3.01", "-5"], [(4, 1, "3.01"), (3, 1, "3"), (5, 2, "5")]),
    # ...but 6.01 + 4.99 only balances as a whole: four greedy transfers.
    (["6.01", "4.99", "-3", "-3", "-5"], [(5, 1, "5"), (3, 1, "1.01"), (3, 2, "1.99"), (4, 2, "3")]),
])
def test_minimum_transfers_by_zero_sum_groups(values, expected):
    balances = {i: Decimal(value) for i, value in enumerate(values, 1)}
    result = suggest_settlements(balances)
    assert [(s.from_user_id, s.to_user_id, s.amount) for s in result] == [
        (debtor, creditor, Decimal(amount)) for debtor, creditor, amount in expected
    ]
    assert result == suggest_settlements(dict(reversed(list(balances.items()))))
    final = dict(balances)
    for suggestion in result:
        final[suggestion.from_user_id] += suggestion.amount
        final[suggestion.to_user_id] -= suggestion.amount
    assert all(value == 0 for value in final.values())


def test_exact_search_never_beats_itself_and_matches_brute_force():
    """For small ledgers, compare against an exhaustive search over all partitions."""
    from itertools import combinations

    from app.services.balances import plan_settlements

    def most_groups(items):
        if not items:
            return 0
        first, rest = items[0], items[1:]
        best = 0
        for size in range(len(rest) + 1):
            for others in combinations(rest, size):
                group = (first,) + others
                if sum(value for _, value in group) == 0:
                    remaining = [item for item in rest if item not in others]
                    best = max(best, 1 + most_groups(remaining))
        return best

    random = Random(3)
    for _ in range(120):
        size = random.randint(2, 8)
        units = [random.randint(-6, 6) for _ in range(size - 1)]
        units.append(-sum(units))
        balances = {i: Decimal(value).scaleb(-2) for i, value in enumerate(units, 1)}
        suggestions, minimal = plan_settlements(balances)
        nonzero = [(i, value) for i, value in balances.items() if value]
        assert minimal
        assert len(suggestions) == len(nonzero) - most_groups(nonzero)


def test_large_groups_fall_back_to_greedy_and_say_so():
    from app.services.balances import MAX_EXACT_MEMBERS, greedy_settlements, plan_settlements

    size = MAX_EXACT_MEMBERS + 1
    balances = {i: Decimal(1) for i in range(1, size)}
    balances[size] = Decimal(-(size - 1))
    suggestions, minimal = plan_settlements(balances)
    assert not minimal and suggestions == greedy_settlements(balances)
    assert len(suggestions) == size - 1
