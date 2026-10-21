"""Initial polling-only target schema"""

import sqlalchemy as sa
from alembic import op

revision = "fbc914596651"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("audit_logs", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_audit_logs_operation"), ["operation"], unique=False)
        batch_op.create_index(batch_op.f("ix_audit_logs_timestamp"), ["timestamp"], unique=False)

    op.create_table(
        "tenants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_code"),
    )
    op.create_table(
        "targets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("controller_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=2048), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("config_requested", sa.Boolean(), nullable=False),
        sa.Column("polling_interval_seconds", sa.Integer(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_poll_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_request_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "polling_interval_seconds BETWEEN 1 AND 86399", name="ck_target_poll_interval"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "controller_id", name="uq_target_tenant_controller"),
    )
    with op.batch_alter_table("targets", schema=None) as batch_op:
        batch_op.create_index("ix_targets_last_seen_at", ["last_seen_at"], unique=False)

    op.create_table(
        "target_attributes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("attribute_key", sa.String(length=128), nullable=False),
        sa.Column("attribute_value", sa.String(length=2048), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["target_id"], ["targets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("target_id", "attribute_key", name="uq_target_attribute"),
    )
    op.create_table(
        "target_credentials",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["target_id"], ["targets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    with op.batch_alter_table("target_credentials", schema=None) as batch_op:
        batch_op.create_index(
            "uq_active_target_credential",
            ["target_id"],
            unique=True,
            sqlite_where=sa.text("is_active = true"),
            postgresql_where=sa.text("is_active = true"),
        )


def downgrade():
    with op.batch_alter_table("target_credentials", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_active_target_credential",
            sqlite_where=sa.text("is_active = true"),
            postgresql_where=sa.text("is_active = true"),
        )

    op.drop_table("target_credentials")
    op.drop_table("target_attributes")
    with op.batch_alter_table("targets", schema=None) as batch_op:
        batch_op.drop_index("ix_targets_last_seen_at")

    op.drop_table("targets")
    op.drop_table("tenants")
    with op.batch_alter_table("audit_logs", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_audit_logs_timestamp"))
        batch_op.drop_index(batch_op.f("ix_audit_logs_operation"))

    op.drop_table("audit_logs")
