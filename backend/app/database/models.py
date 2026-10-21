from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow():
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Target(Base):
    __tablename__ = "targets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "controller_id", name="uq_target_tenant_controller"),
        CheckConstraint(
            "polling_interval_seconds BETWEEN 1 AND 86399", name="ck_target_poll_interval"
        ),
        Index("ix_targets_last_seen_at", "last_seen_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"))
    controller_id: Mapped[str] = mapped_column(String(128))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(2048), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    config_requested: Mapped[bool] = mapped_column(Boolean, default=True)
    polling_interval_seconds: Mapped[int | None] = mapped_column(Integer)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_request_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class TargetAttribute(Base):
    __tablename__ = "target_attributes"
    __table_args__ = (UniqueConstraint("target_id", "attribute_key", name="uq_target_attribute"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("targets.id", ondelete="CASCADE"))
    attribute_key: Mapped[str] = mapped_column(String(128))
    attribute_value: Mapped[str] = mapped_column(String(2048))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class TargetCredential(Base):
    __tablename__ = "target_credentials"
    __table_args__ = (
        Index(
            "uq_active_target_credential",
            "target_id",
            unique=True,
            sqlite_where=text("is_active = true"),
            postgresql_where=text("is_active = true"),
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    target_id: Mapped[int] = mapped_column(ForeignKey("targets.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    actor: Mapped[str] = mapped_column(String(128))
    operation: Mapped[str] = mapped_column(String(64), index=True)
    resource_type: Mapped[str] = mapped_column(String(64))
    resource_id: Mapped[str | None] = mapped_column(String(128))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    details: Mapped[dict] = mapped_column(JSON, default=dict)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(16), default="viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UserSession(Base):
    __tablename__ = "user_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class LoginThrottle(Base):
    __tablename__ = "login_throttles"
    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    window_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FirmwareArtifact(Base):
    __tablename__ = "firmware_artifacts"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    vendor: Mapped[str] = mapped_column(String(255), default="")
    compatible: Mapped[str] = mapped_column(String(255))
    filename: Mapped[str] = mapped_column(String(200))
    storage_key: Mapped[str] = mapped_column(String(64), unique=True)
    size: Mapped[int] = mapped_column(BigInteger)
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    sha1: Mapped[str] = mapped_column(String(40))
    md5: Mapped[str] = mapped_column(String(32))
    available: Mapped[bool] = mapped_column(Boolean, default=True)
    signature_status: Mapped[str] = mapped_column(String(32), default="NOT_VERIFIED")
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SoftwareModule(Base):
    __tablename__ = "software_modules"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_module_version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(128))
    type: Mapped[str] = mapped_column(String(32), default="os")
    vendor: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    artifact_id: Mapped[int] = mapped_column(
        ForeignKey("firmware_artifacts.id", ondelete="RESTRICT")
    )


class Distribution(Base):
    __tablename__ = "distributions"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_distribution_version"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(128))
    description: Mapped[str] = mapped_column(Text, default="")
    type: Mapped[str] = mapped_column(String(32), default="os")
    module_id: Mapped[int] = mapped_column(ForeignKey("software_modules.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Deployment(Base):
    __tablename__ = "deployments"
    __table_args__ = (
        Index(
            "uq_active_deployment",
            "target_id",
            unique=True,
            sqlite_where=text("active = true"),
            postgresql_where=text("active = true"),
        ),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    request_key: Mapped[str] = mapped_column(String(64), unique=True)
    retry_of: Mapped[int | None] = mapped_column(ForeignKey("deployments.id", ondelete="RESTRICT"))
    tenant_id: Mapped[int] = mapped_column(ForeignKey("tenants.id", ondelete="RESTRICT"))
    target_id: Mapped[int] = mapped_column(
        ForeignKey("targets.id", ondelete="RESTRICT"), index=True
    )
    distribution_id: Mapped[int] = mapped_column(
        ForeignKey("distributions.id", ondelete="RESTRICT")
    )
    module_id: Mapped[int] = mapped_column(ForeignKey("software_modules.id", ondelete="RESTRICT"))
    artifact_id: Mapped[int] = mapped_column(
        ForeignKey("firmware_artifacts.id", ondelete="RESTRICT")
    )
    mode: Mapped[str] = mapped_column(String(32), default="forced")
    internal_status: Mapped[str] = mapped_column(String(32), default="WAITING_FOR_TARGET")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    snapshot: Mapped[dict] = mapped_column(JSON)
    progress: Mapped[int | None] = mapped_column(Integer)
    boot_confirmation: Mapped[str] = mapped_column(String(32), default="UNKNOWN")
    error_message: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="RESTRICT"))
    attempt_count: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DeploymentEvent(Base):
    __tablename__ = "deployment_events"
    __table_args__ = (UniqueConstraint("deployment_id", "fingerprint", name="uq_feedback_event"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    deployment_id: Mapped[int] = mapped_column(
        ForeignKey("deployments.id", ondelete="RESTRICT"), index=True
    )
    kind: Mapped[str] = mapped_column(String(64))
    fingerprint: Mapped[str | None] = mapped_column(String(64))
    raw: Mapped[dict] = mapped_column(JSON, default=dict)
    message: Mapped[str] = mapped_column(Text, default="")
    progress: Mapped[int | None] = mapped_column(Integer)
    device_time: Mapped[str | None] = mapped_column(String(32))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
