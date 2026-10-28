from decimal import Decimal, localcontext
from typing import Mapping

from sqlalchemy import func, select, true
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models import Expense, ExpenseSplit, Trip, TripMember, User
from app.schemas.balance import BalanceResponse, MemberBalance, SettlementSuggestion, SettlementSummary
from app.services.trips import TripNotFoundError, accessible_to


class InconsistentLedgerError(Exception):
    pass


class BalanceUnavailableError(Exception):
    pass


# Exact search is O(2^n * n) over members with a nonzero balance; beyond this
# many it falls back to the greedy plan, which is still at most n - 1 transfers.
MAX_EXACT_MEMBERS = 14


def check_ledger(balances: Mapping[int, Decimal]) -> None:
    values = list(balances.values())
    if any(not isinstance(value, Decimal) or not value.is_finite()
           or value.as_tuple().exponent < -2 for value in values):
        raise InconsistentLedgerError()
    with localcontext() as context:
        # Leave room for exact sums, including totals larger than one Expense.
        context.prec = max(28, max((v.adjusted() + 3 for v in values), default=0)
                           + len(str(len(values))))
        if sum(values, Decimal("0.00")) != 0:
            raise InconsistentLedgerError()


def greedy_settlements(balances: Mapping[int, Decimal]) -> list[SettlementSuggestion]:
    """Pair the largest debt with the largest credit until everyone is settled.

    A group of k members always settles in at most k - 1 transfers this way.
    """
    with localcontext() as context:
        context.prec = 50
        debtors = sorted(
            [(user_id, -value) for user_id, value in balances.items() if value < 0],
            key=lambda pair: (-pair[1], pair[0]),
        )
        creditors = sorted(
            [(user_id, value) for user_id, value in balances.items() if value > 0],
            key=lambda pair: (-pair[1], pair[0]),
        )
        result = []
        debtor_index = creditor_index = 0
        while debtor_index < len(debtors) and creditor_index < len(creditors):
            debtor, debt = debtors[debtor_index]
            creditor, credit = creditors[creditor_index]
            amount = min(debt, credit)
            result.append(SettlementSuggestion(
                from_user_id=debtor, to_user_id=creditor, amount=amount,
            ))
            debtors[debtor_index] = (debtor, debt - amount)
            creditors[creditor_index] = (creditor, credit - amount)
            if debt == amount:
                debtor_index += 1
            if credit == amount:
                creditor_index += 1
        return result


def zero_sum_groups(accounts: list[tuple[int, int]]) -> list[list[int]]:
    """Partition nonzero balances (in cents) into the most zero-sum groups.

    Each group of k members settles in k - 1 transfers, so the most groups
    means the fewest transfers overall. dp[mask] is the best number of groups
    for the members in mask, built by removing one member at a time; a mask
    whose balances sum to zero closes a group. O(2^n * n) time and memory.
    """
    count = len(accounts)
    size = 1 << count
    sums = [0] * size
    best = [0] * size
    drop = [0] * size
    for mask in range(1, size):
        low = mask & -mask
        sums[mask] = sums[mask ^ low] + accounts[low.bit_length() - 1][1]
        best_value, choice, rest = -1, 0, mask
        while rest:
            bit = rest & -rest
            rest ^= bit
            if best[mask ^ bit] > best_value:
                best_value, choice = best[mask ^ bit], bit.bit_length() - 1
        best[mask] = best_value + (sums[mask] == 0)
        drop[mask] = choice
    groups: list[list[int]] = []
    group: list[int] = []
    mask = size - 1
    while mask:
        member = drop[mask]
        group.append(accounts[member][0])
        mask ^= 1 << member
        if sums[mask] == 0:
            groups.append(group)
            group = []
    return groups


def plan_settlements(balances: Mapping[int, Decimal]) -> tuple[list[SettlementSuggestion], bool]:
    """Suggest transfers that settle the ledger in the fewest steps we can find.

    Returns the suggestions and whether the count is provably minimal. Suggestions
    are not actual payments.
    """
    check_ledger(balances)
    accounts = sorted((user_id, int(value.scaleb(2))) for user_id, value in balances.items() if value)
    if len(accounts) > MAX_EXACT_MEMBERS:
        return greedy_settlements(balances), False
    result: list[SettlementSuggestion] = []
    for group in sorted(zero_sum_groups(accounts), key=min):
        result.extend(greedy_settlements({user_id: balances[user_id] for user_id in group}))
    return result, True


def suggest_settlements(balances: Mapping[int, Decimal]) -> list[SettlementSuggestion]:
    return plan_settlements(balances)[0]


def balance_query(trip_id: int, user_id: int):
    """One statement keeps authorization, membership, payments and splits in one snapshot."""
    scope = select(Trip.id, Trip.owner_id).where(
        Trip.id == trip_id, accessible_to(user_id),
    ).cte("balance_trip")
    participants = select(scope.c.owner_id.label("user_id")).union(
        select(TripMember.user_id).join(scope, TripMember.trip_id == scope.c.id),
    ).cte("balance_participants")
    expenses = select(
        Expense.id, Expense.amount, Expense.currency, Expense.paid_by_user_id,
    ).join(scope, Expense.trip_id == scope.c.id).cte("balance_expenses")
    splits = select(
        ExpenseSplit.expense_id, ExpenseSplit.user_id, ExpenseSplit.share_amount,
    ).join(expenses, ExpenseSplit.expense_id == expenses.c.id).cte("balance_splits")
    paid = select(
        expenses.c.paid_by_user_id.label("user_id"), func.sum(expenses.c.amount).label("paid"),
    ).group_by(expenses.c.paid_by_user_id).cte("balance_paid")
    shares = select(
        splits.c.user_id, func.sum(splits.c.share_amount).label("share"),
    ).group_by(splits.c.user_id).cte("balance_shares")
    split_totals = select(
        splits.c.expense_id, func.sum(splits.c.share_amount).label("total"),
    ).group_by(splits.c.expense_id).cte("balance_split_totals")
    audit = select(
        func.min(expenses.c.currency).label("currency"),
        func.count(func.distinct(expenses.c.currency)).label("currency_count"),
        func.count().filter(
            expenses.c.amount != func.coalesce(split_totals.c.total, Decimal("0.00")),
        ).label("invalid_expenses"),
    ).select_from(expenses.outerjoin(
        split_totals, split_totals.c.expense_id == expenses.c.id,
    )).cte("balance_audit")
    # Include financial identities too: never silently discard a former participant.
    identities = select(participants.c.user_id).union(
        select(paid.c.user_id), select(shares.c.user_id),
    ).cte("balance_identities")
    return select(
        identities.c.user_id, User.username,
        participants.c.user_id.is_not(None).label("is_participant"),
        func.coalesce(paid.c.paid, Decimal("0.00")).label("paid"),
        func.coalesce(shares.c.share, Decimal("0.00")).label("share"),
        audit.c.currency, audit.c.currency_count, audit.c.invalid_expenses,
    ).select_from(identities).join(User, User.id == identities.c.user_id).outerjoin(
        participants, participants.c.user_id == identities.c.user_id,
    ).outerjoin(paid, paid.c.user_id == identities.c.user_id).outerjoin(
        shares, shares.c.user_id == identities.c.user_id,
    ).join(audit, true()).order_by(identities.c.user_id)


def get_balances(db: Session, trip_id: int, user_id: int) -> BalanceResponse:
    try:
        rows = db.execute(balance_query(trip_id, user_id)).all()
        if not rows:
            raise TripNotFoundError()
        if (rows[0].currency_count > 1 or rows[0].invalid_expenses
                or any(not row.is_participant for row in rows)):
            raise InconsistentLedgerError()
        # INTEGER Expense IDs and NUMERIC(12,2) cap database totals well below 50 digits.
        with localcontext() as context:
            context.prec = 50
            members = [MemberBalance(
                user_id=row.user_id, username=row.username,
                paid=row.paid, share=row.share, balance=row.paid - row.share,
            ) for row in rows]
            balances = {m.user_id: m.balance for m in members}
            suggestions, minimal = plan_settlements(balances)
        return BalanceResponse(
            trip_id=trip_id, currency=rows[0].currency,
            members=members, suggested_settlements=suggestions,
            settlement=SettlementSummary(
                transfers=len(suggestions), minimal=minimal,
                unsettled_members=sum(1 for value in balances.values() if value),
            ),
        )
    except SQLAlchemyError:
        db.rollback()
        raise BalanceUnavailableError() from None
    except (TripNotFoundError, InconsistentLedgerError):
        db.rollback()
        raise
