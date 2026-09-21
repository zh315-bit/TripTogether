from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Identity, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.expense_split import ExpenseSplit


class Expense(Base):
    __tablename__ = "expenses"
    __table_args__ = (
        CheckConstraint("amount > 0 AND amount <= 9999999999.99", name="ck_expenses_amount"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_expenses_currency"),
        CheckConstraint("length(btrim(description)) > 0", name="ck_expenses_description"),
    )

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    trip_id: Mapped[int] = mapped_column(
        ForeignKey("trips.id", name="fk_expenses_trip", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    paid_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", name="fk_expenses_payer", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    expense_date: Mapped[date] = mapped_column(Date, nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", name="fk_expenses_creator", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
        onupdate=func.statement_timestamp(),
    )
    splits: Mapped[list[ExpenseSplit]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True, order_by=ExpenseSplit.user_id,
    )
