"""Add evidence-backed journalist picks.

Revision ID: 20261118_0004
Revises: 20261118_0003
Create Date: 2026-11-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261118_0004"
down_revision: str | None = "20261118_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "journalist_picks",
        sa.Column("id", sa.String(26), primary_key=True, nullable=False),
        sa.Column("source_document_version_id", sa.String(26), nullable=False),
        sa.Column("source_fact_id", sa.String(26), nullable=False),
        sa.Column("meeting_code", sa.String(20), nullable=False),
        sa.Column("race_number", sa.Integer(), nullable=False),
        sa.Column("selection_rank", sa.Integer(), nullable=False),
        sa.Column("mandil", sa.Integer()),
        sa.Column("horse_name_raw", sa.String(255), nullable=False),
        sa.Column("journalist_name", sa.String(255), nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("requires_review", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_document_version_id"],
            ["document_versions.id"],
            name="fk_journalist_pick_document_version",
        ),
        sa.ForeignKeyConstraint(
            ["source_fact_id"],
            ["extracted_facts.id"],
            name="fk_journalist_pick_source_fact",
        ),
        sa.UniqueConstraint("source_fact_id", name="uq_journalist_picks_source_fact"),
        sa.UniqueConstraint(
            "source_document_version_id",
            "meeting_code",
            "race_number",
            "selection_rank",
            name="uq_journalist_picks_document_race_rank",
        ),
        sa.CheckConstraint("length(id) = 26", name="ck_journalist_picks_id_length"),
        sa.CheckConstraint(
            "race_number > 0", name="ck_journalist_picks_race_number_positive"
        ),
        sa.CheckConstraint(
            "selection_rank > 0", name="ck_journalist_picks_selection_rank_positive"
        ),
        sa.CheckConstraint(
            "mandil IS NULL OR mandil > 0", name="ck_journalist_picks_mandil_positive"
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_journalist_picks_confidence_range",
        ),
    )
    op.create_index(
        "ix_journalist_picks_meeting_race",
        "journalist_picks",
        ["meeting_code", "race_number"],
    )


def downgrade() -> None:
    op.drop_index("ix_journalist_picks_meeting_race", table_name="journalist_picks")
    op.drop_table("journalist_picks")
