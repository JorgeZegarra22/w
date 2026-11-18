"""Add master entities, races, and race entries.

Revision ID: 20261118_0002
Revises: 20261118_0001
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261118_0002"
down_revision: str | None = "20261118_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _create_master(name: str) -> None:
    op.create_table(
        name,
        sa.Column("id", sa.String(26), primary_key=True, nullable=False),
        sa.Column("canonical_name", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255), nullable=False),
        sa.Column("confirmation_status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("normalized_name", name=f"uq_{name}_normalized_name"),
        sa.CheckConstraint("length(id) = 26", name=f"ck_{name}_id_length"),
        sa.CheckConstraint(
            "length(trim(canonical_name)) > 0",
            name=f"ck_{name}_canonical_name_nonempty",
        ),
        sa.CheckConstraint(
            "length(trim(normalized_name)) > 0",
            name=f"ck_{name}_normalized_name_nonempty",
        ),
        sa.CheckConstraint(
            "confirmation_status IN ('confirmed', 'unconfirmed')",
            name=f"ck_{name}_confirmation_status_values",
        ),
    )


def upgrade() -> None:
    for name in ("horses", "jockeys", "trainers", "studs"):
        _create_master(name)

    op.create_table(
        "races",
        sa.Column("id", sa.String(26), primary_key=True, nullable=False),
        sa.Column("source_document_version_id", sa.String(26), nullable=False),
        sa.Column("meeting_code", sa.String(20), nullable=False),
        sa.Column("race_number", sa.Integer(), nullable=False),
        sa.Column("scheduled_date", sa.Date(), nullable=False),
        sa.Column("distance_meters", sa.Integer(), nullable=False),
        sa.Column("surface", sa.String(30), nullable=False),
        sa.Column("confirmation_status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_document_version_id"],
            ["document_versions.id"],
            name="fk_race_document_version",
        ),
        sa.UniqueConstraint("meeting_code", "race_number", name="uq_races_meeting_race"),
        sa.CheckConstraint("length(id) = 26", name="ck_races_id_length"),
        sa.CheckConstraint("race_number > 0", name="ck_races_race_number_positive"),
        sa.CheckConstraint("distance_meters > 0", name="ck_races_distance_positive"),
        sa.CheckConstraint("surface IN ('arena', 'cesped')", name="ck_races_surface_values"),
        sa.CheckConstraint(
            "confirmation_status IN ('confirmed', 'unconfirmed')",
            name="ck_races_confirmation_status_values",
        ),
    )
    op.create_table(
        "race_entries",
        sa.Column("id", sa.String(26), primary_key=True, nullable=False),
        sa.Column("race_id", sa.String(26), nullable=False),
        sa.Column("horse_id", sa.String(26), nullable=False),
        sa.Column("jockey_id", sa.String(26), nullable=False),
        sa.Column("trainer_id", sa.String(26), nullable=False),
        sa.Column("stud_id", sa.String(26), nullable=False),
        sa.Column("source_fact_id", sa.String(26), nullable=False),
        sa.Column("mandil", sa.Integer(), nullable=False),
        sa.Column("weight", sa.Numeric(5, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["race_id"], ["races.id"], name="fk_race_entry_race"),
        sa.ForeignKeyConstraint(["horse_id"], ["horses.id"], name="fk_race_entry_horse"),
        sa.ForeignKeyConstraint(["jockey_id"], ["jockeys.id"], name="fk_race_entry_jockey"),
        sa.ForeignKeyConstraint(
            ["trainer_id"], ["trainers.id"], name="fk_race_entry_trainer"
        ),
        sa.ForeignKeyConstraint(["stud_id"], ["studs.id"], name="fk_race_entry_stud"),
        sa.ForeignKeyConstraint(
            ["source_fact_id"],
            ["extracted_facts.id"],
            name="fk_race_entry_source_fact",
        ),
        sa.UniqueConstraint("source_fact_id", name="uq_race_entries_source_fact"),
        sa.UniqueConstraint("race_id", "mandil", name="uq_race_entries_race_mandil"),
        sa.CheckConstraint("length(id) = 26", name="ck_race_entries_id_length"),
        sa.CheckConstraint("mandil > 0", name="ck_race_entries_mandil_positive"),
        sa.CheckConstraint("weight > 0", name="ck_race_entries_weight_positive"),
    )


def downgrade() -> None:
    op.drop_table("race_entries")
    op.drop_table("races")
    for name in ("studs", "trainers", "jockeys", "horses"):
        op.drop_table(name)
