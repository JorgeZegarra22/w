"""Add history import batches and horse race results.

Revision ID: 20261118_0003
Revises: 20261118_0002
Create Date: 2026-11-18
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261118_0003"
down_revision: str | None = "20261118_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "history_import_batches",
        sa.Column("id", sa.String(26), primary_key=True, nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("source_filename", sa.Text(), nullable=False),
        sa.Column("file_format", sa.String(20), nullable=False),
        sa.Column("row_count", sa.Integer(), nullable=False),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "file_sha256", name="uq_history_import_batches_file_sha256"
        ),
        sa.CheckConstraint("length(id) = 26", name="ck_history_import_batches_id_length"),
        sa.CheckConstraint(
            "length(file_sha256) = 64",
            name="ck_history_import_batches_file_sha256_length",
        ),
        sa.CheckConstraint(
            "file_sha256 = lower(file_sha256)",
            name="ck_history_import_batches_file_sha256_lowercase",
        ),
        sa.CheckConstraint(
            "file_format = 'csv'", name="ck_history_import_batches_file_format_csv"
        ),
        sa.CheckConstraint(
            "row_count > 0", name="ck_history_import_batches_row_count_positive"
        ),
    )
    op.create_table(
        "horse_race_results",
        sa.Column("id", sa.String(26), primary_key=True, nullable=False),
        sa.Column("import_batch_id", sa.String(26), nullable=False),
        sa.Column("horse_id", sa.String(26), nullable=False),
        sa.Column("race_date", sa.Date(), nullable=False),
        sa.Column("finishing_position", sa.Integer(), nullable=False),
        sa.Column("distance_meters", sa.Integer(), nullable=False),
        sa.Column("elapsed_time_seconds", sa.Numeric(9, 3), nullable=False),
        sa.Column("surface", sa.String(20), nullable=False),
        sa.Column("track_condition", sa.String(50), nullable=False),
        sa.Column("meeting_code", sa.String(20)),
        sa.Column("race_number", sa.Integer()),
        sa.Column("row_fingerprint", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["import_batch_id"],
            ["history_import_batches.id"],
            name="fk_horse_result_import_batch",
        ),
        sa.ForeignKeyConstraint(
            ["horse_id"], ["horses.id"], name="fk_horse_result_horse"
        ),
        sa.UniqueConstraint(
            "row_fingerprint", name="uq_horse_race_results_row_fingerprint"
        ),
        sa.CheckConstraint("length(id) = 26", name="ck_horse_race_results_id_length"),
        sa.CheckConstraint(
            "finishing_position > 0", name="ck_horse_race_results_position_positive"
        ),
        sa.CheckConstraint(
            "distance_meters > 0", name="ck_horse_race_results_distance_positive"
        ),
        sa.CheckConstraint(
            "elapsed_time_seconds > 0",
            name="ck_horse_race_results_elapsed_time_positive",
        ),
        sa.CheckConstraint(
            "surface IN ('arena', 'cesped')",
            name="ck_horse_race_results_surface_values",
        ),
        sa.CheckConstraint(
            "length(trim(track_condition)) > 0",
            name="ck_horse_race_results_track_condition_nonempty",
        ),
        sa.CheckConstraint(
            "race_number IS NULL OR race_number > 0",
            name="ck_horse_race_results_race_number_positive",
        ),
        sa.CheckConstraint(
            "length(row_fingerprint) = 64",
            name="ck_horse_race_results_row_fingerprint_length",
        ),
        sa.CheckConstraint(
            "row_fingerprint = lower(row_fingerprint)",
            name="ck_horse_race_results_row_fingerprint_lowercase",
        ),
    )
    op.create_index(
        "ix_horse_results_horse_date",
        "horse_race_results",
        ["horse_id", "race_date"],
    )
    op.create_index(
        "ix_horse_results_horse_distance_date",
        "horse_race_results",
        ["horse_id", "distance_meters", "race_date"],
    )
    op.create_index(
        "ix_horse_results_horse_surface_date",
        "horse_race_results",
        ["horse_id", "surface", "race_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_horse_results_horse_surface_date", table_name="horse_race_results")
    op.drop_index("ix_horse_results_horse_distance_date", table_name="horse_race_results")
    op.drop_index("ix_horse_results_horse_date", table_name="horse_race_results")
    op.drop_table("horse_race_results")
    op.drop_table("history_import_batches")
