import hashlib
import json
import re

from fastapi import HTTPException
from sqlalchemy import select

from app.database.models import (
    Deployment,
    DeploymentEvent,
    Distribution,
    FirmwareArtifact,
    SoftwareModule,
    Target,
    utcnow,
)
from app.management.auth import record

STAGES = {
    "WAITING_FOR_TARGET": 0,
    "DISCOVERED": 1,
    "DOWNLOADING": 2,
    "DOWNLOADED": 3,
    "INSTALLING": 4,
}


def event(session, deployment, kind, message="", raw=None, **extra):
    item = DeploymentEvent(
        deployment_id=deployment.id, kind=kind, message=message, raw=raw or {}, **extra
    )
    session.add(item)
    deployment.last_updated_at = utcnow()
    return item


def advance(deployment, state):
    if deployment.active and STAGES.get(state, -1) > STAGES.get(deployment.internal_status, -1):
        deployment.internal_status = state
        deployment.last_updated_at = utcnow()


def assign(session, user, payload, storage, retry_of=None):
    existing = session.scalar(
        select(Deployment).where(Deployment.request_key == payload.request_key)
    )
    if existing:
        if (existing.target_id, existing.distribution_id, existing.mode) != (
            payload.target_id,
            payload.distribution_id,
            payload.mode,
        ):
            raise HTTPException(409, "Request key already belongs to a different assignment")
        return existing
    target = session.scalar(select(Target).where(Target.id == payload.target_id).with_for_update())
    if target is None or not target.enabled or target.deleted_at is not None:
        raise HTTPException(400, "Select an enabled target")
    if session.scalar(
        select(Deployment.id).where(Deployment.target_id == target.id, Deployment.active.is_(True))
    ):
        raise HTTPException(409, "Target already has an active deployment")
    distribution = session.get(Distribution, payload.distribution_id)
    if distribution is None:
        raise HTTPException(404, "Distribution not found")
    module = session.get(SoftwareModule, distribution.module_id)
    # Share the artifact lock with withdrawal so an action cannot race availability changes.
    artifact = session.scalar(
        select(FirmwareArtifact).where(FirmwareArtifact.id == module.artifact_id).with_for_update()
    )
    if not artifact.available or not storage.path(artifact.storage_key).is_file():
        raise HTTPException(409, "Release artifact is unavailable")
    if (
        payload.expected_compatible != artifact.compatible
        or payload.expected_version != distribution.version
    ):
        raise HTTPException(409, "Compatible string or release version does not match confirmation")
    snapshot = {
        "distribution_name": distribution.name,
        "distribution_version": distribution.version,
        "module_name": module.name,
        "module_version": module.version,
        "module_type": module.type,
        "filename": artifact.filename,
        "size": artifact.size,
        "sha256": artifact.sha256,
        "sha1": artifact.sha1,
        "md5": artifact.md5,
        "compatible": artifact.compatible,
        "storage_key": artifact.storage_key,
    }
    deployment = Deployment(
        request_key=payload.request_key,
        retry_of=retry_of.id if retry_of else None,
        tenant_id=target.tenant_id,
        target_id=target.id,
        distribution_id=distribution.id,
        module_id=module.id,
        artifact_id=artifact.id,
        mode=payload.mode,
        snapshot=snapshot,
        created_by=user.id,
        attempt_count=retry_of.attempt_count + 1 if retry_of else 1,
    )
    session.add(deployment)
    session.flush()
    event(session, deployment, "assigned", payload.approval_note)
    record(
        session,
        user,
        "deployment.assigned",
        "deployment",
        deployment.id,
        target_id=target.id,
        mode=payload.mode,
        approval_note=payload.approval_note,
    )
    return deployment


def receive_feedback(session, target, deployment, payload):
    raw = payload.model_dump(mode="json", exclude_none=True)
    fingerprint = hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()
    if session.scalar(
        select(DeploymentEvent.id).where(
            DeploymentEvent.deployment_id == deployment.id,
            DeploymentEvent.fingerprint == fingerprint,
        )
    ):
        return
    details = payload.status.details
    percentages = [
        int(p)
        for line in details
        for p in re.findall(r"(?<!\d)(\d{1,3})%", line)
        if 0 <= int(p) <= 100
    ]
    progress = max(percentages) if percentages else None
    message = "\n".join(details)
    event(
        session,
        deployment,
        "feedback",
        message,
        raw,
        fingerprint=fingerprint,
        device_time=payload.time,
        progress=progress,
    )
    target.last_seen_at = target.last_request_at = utcnow()
    if not deployment.active:
        # Preserve late events, never reopen or overwrite a terminal result.
        return
    execution, finished = payload.status.execution, payload.status.result.finished
    if progress is not None:
        deployment.progress = max(deployment.progress or 0, progress)
    if execution == "closed":
        if finished == "success":
            deployment.internal_status = (
                "DOWNLOAD_SUCCEEDED" if deployment.mode == "download_only" else "INSTALL_SUCCEEDED"
            )
            deployment.progress = 100
            target.config_requested = True
        elif finished == "failure":
            deployment.internal_status = "INSTALL_FAILED"
            deployment.error_message = message or "Target reported failure"
        else:
            raise HTTPException(400, "Closed feedback requires a terminal result")
        deployment.active = False
        deployment.completed_at = utcnow()
    elif execution in {"rejected", "canceled"}:
        deployment.internal_status = execution.upper()
        deployment.error_message = message or None
        deployment.active = False
        deployment.completed_at = utcnow()
    else:
        text = message.lower()
        if execution == "download":
            advance(deployment, "DOWNLOADING")
        elif execution == "downloaded":
            advance(deployment, "DOWNLOADED")
        elif "file checksum ok" in text:
            advance(deployment, "DOWNLOADED")
            if deployment.mode == "download_only":
                deployment.internal_status = "DOWNLOAD_SUCCEEDED"
                deployment.active = False
                deployment.progress = 100
                deployment.completed_at = utcnow()
        elif "download complete" in text:
            advance(deployment, "DOWNLOADED")
        elif progress is not None or any(
            s in text for s in ("install", "copying image", "checking slot")
        ):
            advance(deployment, "INSTALLING")
        else:
            advance(deployment, "DISCOVERED")
