import re
from datetime import UTC, datetime

from sqlalchemy import select, update

from app.core.security import generate_token, hash_token
from app.database.models import AuditLog, Target, TargetAttribute, TargetCredential, Tenant


def audit(session, operation, target_id=None, actor="local-operator", **details):
    session.add(
        AuditLog(
            actor=actor,
            operation=operation,
            resource_type="target",
            resource_id=str(target_id) if target_id is not None else None,
            details=details,
        )
    )


def find_target(session, tenant_code, controller_id, lock=False):
    statement = (
        select(Target)
        .join(Tenant)
        .where(
            Tenant.tenant_code == tenant_code,
            Target.controller_id == controller_id,
            Target.deleted_at.is_(None),
        )
    )
    if lock:
        statement = statement.with_for_update()
    return session.scalar(statement)


def provision(session, tenant_code, controller_id, name=None, actor="local-operator"):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", tenant_code):
        raise ValueError("Tenant must contain 1–64 letters, numbers, underscores or hyphens")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", controller_id) or controller_id in {".", ".."}:
        raise ValueError("Controller ID must be 1–128 safe URL characters")
    tenant = session.scalar(select(Tenant).where(Tenant.tenant_code == tenant_code))
    if tenant is None:
        tenant = Tenant(tenant_code=tenant_code, name=tenant_code)
        session.add(tenant)
        session.flush()
    target = Target(tenant_id=tenant.id, controller_id=controller_id, name=name or controller_id)
    session.add(target)
    session.flush()
    token = rotate(session, target, actor=actor)
    audit(session, "target.created", target.id, actor=actor)
    return target, token


def revoke(session, target, actor="local-operator"):
    session.execute(
        update(TargetCredential)
        .where(TargetCredential.target_id == target.id, TargetCredential.is_active.is_(True))
        .values(is_active=False, revoked_at=datetime.now(UTC))
    )
    audit(session, "token.revoked", target.id, actor=actor)


def rotate(session, target, actor="local-operator"):
    # Caller holds a target row lock; the partial unique index is the final concurrency guard.
    revoke(session, target, actor=actor)
    token = generate_token()
    session.add(TargetCredential(target_id=target.id, token_hash=hash_token(token)))
    audit(session, "token.rotated", target.id, actor=actor)
    return token


def describe(session, target, threshold):
    last_seen = target.last_seen_at
    if target.deleted_at is not None:
        status = "Deleted"
    elif not target.enabled:
        status = "Disabled"
    elif last_seen is None:
        status = "Never Connected"
    else:
        # SQLite returns naive datetimes even for DateTime(timezone=True).
        age = (datetime.now(UTC) - last_seen.replace(tzinfo=UTC)).total_seconds()
        status = "Online" if age <= threshold else "Offline"
    attributes = session.scalars(
        select(TargetAttribute).where(TargetAttribute.target_id == target.id)
    )
    return {
        "id": target.id,
        "controller_id": target.controller_id,
        "name": target.name,
        "tenant_id": target.tenant_id,
        "enabled": target.enabled,
        "deleted_at": target.deleted_at.isoformat() if target.deleted_at else None,
        "connection_status": status,
        "last_seen_at": last_seen.isoformat() if last_seen else None,
        "last_poll_at": target.last_poll_at.isoformat() if target.last_poll_at else None,
        "last_request_at": target.last_request_at.isoformat() if target.last_request_at else None,
        "attributes": {a.attribute_key: a.attribute_value for a in attributes},
        "boot_confirmation": "UNKNOWN",
        "running_firmware": None,
    }
