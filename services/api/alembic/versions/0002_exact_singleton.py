"""Enforce the singleton Boolean exactly across PostgreSQL and SQLite."""

from alembic import op

revision = "0002_exact_singleton"
down_revision = "0001_auth_and_audit"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("admin_users") as batch:
        batch.drop_constraint("ck_admin_users_singleton_key", type_="check")
        batch.create_check_constraint("ck_admin_users_singleton_key", "singleton_key = true")


def downgrade() -> None:
    with op.batch_alter_table("admin_users") as batch:
        batch.drop_constraint("ck_admin_users_singleton_key", type_="check")
        batch.create_check_constraint("ck_admin_users_singleton_key", "singleton_key")
