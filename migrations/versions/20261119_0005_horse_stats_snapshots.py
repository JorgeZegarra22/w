"""Store source-backed horse profiles without changing prediction inputs."""

import sqlalchemy as sa
from alembic import op

revision = "20261119_0005"
down_revision = "20261118_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "horse_stats_snapshots",
        sa.Column("id", sa.String(26), primary_key=True, nullable=False),
        sa.Column("race_entry_id", sa.String(26), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("profile", sa.JSON(none_as_null=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["race_entry_id"], ["race_entries.id"],
            name="fk_horse_stats_snapshots_race_entry_id_race_entries",
        ),
        sa.UniqueConstraint("race_entry_id", "content_hash", name="uq_horse_snapshot_entry_hash"),
        sa.CheckConstraint(
            "length(content_hash) = 64", name="ck_horse_stats_snapshots_content_hash_length"
        ),
    )
    op.create_index(
        "ix_horse_stats_snapshots_entry_fetched",
        "horse_stats_snapshots",
        ["race_entry_id", "fetched_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_horse_stats_snapshots_entry_fetched", table_name="horse_stats_snapshots")
    op.drop_table("horse_stats_snapshots")
