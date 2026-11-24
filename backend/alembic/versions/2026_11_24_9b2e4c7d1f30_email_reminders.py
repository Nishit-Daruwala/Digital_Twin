"""email reminders: users.email_reminders and the reminders log

Revision ID: 9b2e4c7d1f30
Revises: 7c3f9a1d2e65
Create Date: 2026-11-24 10:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9b2e4c7d1f30"
down_revision: str | None = "7c3f9a1d2e65"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_reminders", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.create_table(
        "reminders",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("for_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "for_date"),
    )


def downgrade() -> None:
    op.drop_table("reminders")
    op.drop_column("users", "email_reminders")
