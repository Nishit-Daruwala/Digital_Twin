"""check-in slots (morning / afternoon / evening) and user timezone

Up to three check-ins per day instead of one. Existing check-ins were one per day with no
reliable time of day, so they become 'morning'; this does not bias the learned rhythm, which
only uses days with two or more check-ins. Their time is kept when they were saved that day.

Revision ID: 5d1e7c0a9b42
Revises: 13527c564c3a
Create Date: 2026-11-19 10:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5d1e7c0a9b42"
down_revision: str | None = "13527c564c3a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("timezone", sa.String(length=64), nullable=True))
    op.add_column(
        "checkins",
        sa.Column("slot", sa.String(length=10), server_default="morning", nullable=False),
    )
    op.add_column("checkins", sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE checkins SET checked_at = created_at WHERE created_at::date = date")
    op.create_check_constraint(
        "slot_valid", "checkins", "slot IN ('morning', 'afternoon', 'evening')"
    )
    op.drop_constraint("uq_checkins_user_date", "checkins", type_="unique")
    op.create_unique_constraint(
        "uq_checkins_user_date_slot", "checkins", ["user_id", "date", "slot"]
    )


def downgrade() -> None:
    # Keep one check-in per day (the earliest slot) so the old unique constraint can return.
    op.execute(
        """
        DELETE FROM checkins c USING checkins d
        WHERE c.user_id = d.user_id AND c.date = d.date
          AND array_position(ARRAY['morning','afternoon','evening'], c.slot)
            > array_position(ARRAY['morning','afternoon','evening'], d.slot)
        """
    )
    op.drop_constraint("uq_checkins_user_date_slot", "checkins", type_="unique")
    op.create_unique_constraint("uq_checkins_user_date", "checkins", ["user_id", "date"])
    op.drop_constraint("slot_valid", "checkins", type_="check")
    op.drop_column("checkins", "checked_at")
    op.drop_column("checkins", "slot")
    op.drop_column("users", "timezone")
