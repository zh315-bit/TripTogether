"""create membership and invitations

Revision ID: 0003
Revises: 0002
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0003"
down_revision: Union[str, Sequence[str], None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trip_invitations",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("trip_id", sa.Integer(), nullable=False),
        sa.Column("inviter_id", sa.Integer(), nullable=False),
        sa.Column("invitee_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=8), server_default=sa.text("'pending'"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "(status = 'pending' AND responded_at IS NULL) OR "
            "(status IN ('accepted', 'rejected') AND responded_at IS NOT NULL)",
            name="ck_trip_invitations_response",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected')",
            name="ck_trip_invitations_status",
        ),
        sa.CheckConstraint("inviter_id <> invitee_id", name="ck_trip_invitations_not_self"),
        sa.ForeignKeyConstraint(
            ["invitee_id"], ["users.id"], name="fk_trip_invitations_invitee", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["inviter_id"], ["users.id"], name="fk_trip_invitations_inviter", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["trip_id"], ["trips.id"], name="fk_trip_invitations_trip", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_trip_invitations_invitee_id", "trip_invitations", ["invitee_id"])
    op.create_index("ix_trip_invitations_trip_id", "trip_invitations", ["trip_id"])
    op.create_index(
        "uq_trip_invitations_pending", "trip_invitations", ["trip_id", "invitee_id"],
        unique=True, postgresql_where=sa.text("status = 'pending'"),
    )
    op.create_table(
        "trip_members",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("trip_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=6), nullable=False),
        sa.Column(
            "joined_at", sa.DateTime(timezone=True),
            server_default=sa.text("now()"), nullable=False,
        ),
        sa.CheckConstraint("role IN ('owner', 'member')", name="ck_trip_members_role"),
        sa.ForeignKeyConstraint(
            ["trip_id"], ["trips.id"], name="fk_trip_members_trip", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_trip_members_user", ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trip_id", "user_id", name="uq_trip_members_trip_user"),
    )
    op.create_index("ix_trip_members_user_id", "trip_members", ["user_id"])
    # Existing trips predate memberships. Re-running the INSERT cannot duplicate a pair.
    op.execute(sa.text("""
        INSERT INTO trip_members (trip_id, user_id, role, joined_at)
        SELECT id, owner_id, 'owner', created_at FROM trips
        ON CONFLICT (trip_id, user_id) DO NOTHING
    """))


def downgrade() -> None:
    op.drop_index("ix_trip_members_user_id", table_name="trip_members")
    op.drop_table("trip_members")
    op.drop_index("uq_trip_invitations_pending", table_name="trip_invitations")
    op.drop_index("ix_trip_invitations_trip_id", table_name="trip_invitations")
    op.drop_index("ix_trip_invitations_invitee_id", table_name="trip_invitations")
    op.drop_table("trip_invitations")
