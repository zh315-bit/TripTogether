from decimal import Decimal
from typing import Optional

from sqlalchemy import CheckConstraint, ForeignKey, Identity, Integer, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ExpenseSplit(Base):
    __tablename__ = "expense_splits"
    __table_args__ = (
        UniqueConstraint("expense_id", "user_id", name="uq_expense_splits_expense_user"),
        CheckConstraint(
            "share_amount >= 0 AND share_amount <= 9999999999.99",
            name="ck_expense_splits_amount",
        ),
        CheckConstraint("weight IS NULL OR weight >= 1", name="ck_expense_splits_weight"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    expense_id: Mapped[int] = mapped_column(
        ForeignKey("expenses.id", name="fk_expense_splits_expense", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", name="fk_expense_splits_user", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    share_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    # Set only for `shares` splits; equal and exact splits carry no weight.
    weight: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
