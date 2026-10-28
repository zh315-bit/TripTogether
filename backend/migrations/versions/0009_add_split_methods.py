"""add split methods and share weights

Revision ID: 0009
Revises: 0008
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0009"
down_revision: Union[str, Sequence[str], None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Existing rows are equal splits; weights only exist for `shares`.
    op.add_column("expenses", sa.Column(
        "split_method", sa.String(length=6), nullable=False, server_default="equal"))
    op.create_check_constraint(
        "ck_expenses_split_method", "expenses", "split_method IN ('equal', 'shares', 'exact')")
    op.add_column("expense_splits", sa.Column("weight", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_expense_splits_weight", "expense_splits", "weight IS NULL OR weight >= 1")


def downgrade() -> None:
    op.drop_constraint("ck_expense_splits_weight", "expense_splits", type_="check")
    op.drop_column("expense_splits", "weight")
    op.drop_constraint("ck_expenses_split_method", "expenses", type_="check")
    op.drop_column("expenses", "split_method")
