"""create expenses and splits

Revision ID: 0005
Revises: 0004
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "expenses",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("trip_id", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("paid_by_user_id", sa.Integer(), nullable=False),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_expenses_currency"),
        sa.CheckConstraint("amount > 0 AND amount <= 9999999999.99", name="ck_expenses_amount"),
        sa.CheckConstraint("length(btrim(description)) > 0", name="ck_expenses_description"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"],
                                name="fk_expenses_creator", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["paid_by_user_id"], ["users.id"],
                                name="fk_expenses_payer", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["trip_id"], ["trips.id"],
                                name="fk_expenses_trip", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_expenses_created_by_user_id", "expenses", ["created_by_user_id"])
    op.create_index("ix_expenses_paid_by_user_id", "expenses", ["paid_by_user_id"])
    op.create_index("ix_expenses_trip_id", "expenses", ["trip_id"])
    op.create_table(
        "expense_splits",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("expense_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("share_amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.CheckConstraint("share_amount >= 0 AND share_amount <= 9999999999.99",
                           name="ck_expense_splits_amount"),
        sa.ForeignKeyConstraint(["expense_id"], ["expenses.id"],
                                name="fk_expense_splits_expense", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"],
                                name="fk_expense_splits_user", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("expense_id", "user_id", name="uq_expense_splits_expense_user"),
    )
    op.create_index("ix_expense_splits_user_id", "expense_splits", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_expense_splits_user_id", table_name="expense_splits")
    op.drop_table("expense_splits")
    op.drop_index("ix_expenses_trip_id", table_name="expenses")
    op.drop_index("ix_expenses_paid_by_user_id", table_name="expenses")
    op.drop_index("ix_expenses_created_by_user_id", table_name="expenses")
    op.drop_table("expenses")
