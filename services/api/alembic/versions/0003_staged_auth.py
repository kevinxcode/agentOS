"""Persist authentication stages, replay protection, and shared rate limits."""

import sqlalchemy as sa

from alembic import op

revision = "0003_staged_auth"
down_revision = "0002_exact_singleton"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing sessions are deliberately downgraded; no pre-migration token gains privilege.
    with op.batch_alter_table("sessions") as batch:
        batch.add_column(
            sa.Column("stage", sa.String(16), nullable=False, server_default="preauth")
        )
        batch.create_check_constraint("ck_sessions_stage", "stage IN ('preauth', 'full')")
    with op.batch_alter_table("sessions") as batch:
        batch.alter_column("stage", server_default=None, existing_type=sa.String(16))
    op.add_column("totp_enrollments", sa.Column("last_used_counter", sa.Integer(), nullable=True))
    op.create_table(
        "auth_rate_limits",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("window_started_at", sa.Integer(), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("auth_rate_limits")
    with op.batch_alter_table("totp_enrollments") as batch:
        batch.drop_column("last_used_counter")
    with op.batch_alter_table("sessions") as batch:
        batch.drop_constraint("ck_sessions_stage", type_="check")
        batch.drop_column("stage")
