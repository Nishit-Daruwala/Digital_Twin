"""recommendation details: key, evidence, scores, rank, policy, feedback time

Revision ID: 7c3f9a1d2e65
Revises: 5d1e7c0a9b42
Create Date: 2026-11-22 10:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7c3f9a1d2e65"
down_revision: str | None = "5d1e7c0a9b42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("recommendations", sa.Column("key", sa.String(length=160), nullable=True))
    op.execute("UPDATE recommendations SET key = id::text WHERE key IS NULL")  # any old rows
    op.alter_column("recommendations", "key", nullable=False)
    op.add_column(
        "recommendations",
        sa.Column(
            "evidence",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column("recommendations", sa.Column("relevance", sa.Float(), nullable=True))
    op.add_column("recommendations", sa.Column("score", sa.Float(), nullable=True))
    op.add_column("recommendations", sa.Column("rank", sa.SmallInteger(), nullable=True))
    op.add_column("recommendations", sa.Column("policy", sa.String(length=12), nullable=True))
    op.add_column(
        "recommendations", sa.Column("feedback_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_unique_constraint(
        "uq_recommendation_key", "recommendations", ["user_id", "for_date", "key"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_recommendation_key", "recommendations", type_="unique")
    for col in ("feedback_at", "policy", "rank", "score", "relevance", "evidence", "key"):
        op.drop_column("recommendations", col)
