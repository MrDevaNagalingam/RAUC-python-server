import re

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import delete, func, select, update
from starlette.concurrency import run_in_threadpool
from starlette.formparsers import MultiPartException, MultiPartParser

from app.database.models import (
    AuditLog,
    Deployment,
    DeploymentEvent,
    Distribution,
    FirmwareArtifact,
    SoftwareModule,
    Target,
    Tenant,
    User,
    UserSession,
    utcnow,
)
from app.management.auth import (
    Admin,
    CurrentUser,
    UserCreate,
    Writer,
    password_hasher,
    record,
    user_view,
)
from app.management.schemas import (
    DeploymentCreate,
    DistributionCreate,
    DistributionPatch,
    FirmwareMetadata,
    ModuleCreate,
    RetryRequest,
    TargetCreate,
    TargetPatch,
    TargetPurge,
    UserPatch,
)
from app.services.deployment_engine import assign, event
from app.services.targets import describe, provision, revoke, rotate

router = APIRouter(prefix="/api", tags=["Management"])


def row(item, omit=()):
    return {
        column.name: getattr(item, column.name)
        for column in item.__table__.columns
        if column.name not in omit
    }


def get(session, model, item_id, lock=False):
    statement = select(model).where(model.id == item_id)
    item = session.scalar(statement.with_for_update() if lock else statement)
    if item is None:
        raise HTTPException(404, "Resource not found")
    return item


def live_target(session, target_id, lock=False):
    target = get(session, Target, target_id, lock=lock)
    if target.deleted_at is not None:
        raise HTTPException(404, "Target has been deleted; restore it before making changes")
    return target


def target_view(request, session, target):
    output = describe(session, target, request.app.state.settings.offline_threshold_seconds)
    output.update(
        tenant=session.get(Tenant, target.tenant_id).tenant_code,
        description=target.description,
        polling_interval_seconds=target.polling_interval_seconds,
    )
    latest = session.scalar(
        select(Deployment)
        .where(Deployment.target_id == target.id)
        .order_by(Deployment.id.desc())
        .limit(1)
    )
    output["deployment"] = row(latest) if latest else None
    installed = session.scalar(
        select(Deployment)
        .where(Deployment.target_id == target.id, Deployment.internal_status == "INSTALL_SUCCEEDED")
        .order_by(Deployment.id.desc())
        .limit(1)
    )
    output["last_installed_version"] = installed.snapshot["module_version"] if installed else None
    return output


@router.get("/targets")
def targets(request: Request, ctx: CurrentUser, include_deleted: bool = False):
    query = select(Target).order_by(Target.id)
    if not include_deleted:
        query = query.where(Target.deleted_at.is_(None))
    return [target_view(request, ctx.session, target) for target in ctx.session.scalars(query)]


@router.post("/targets", status_code=201)
def create_target(request: Request, payload: TargetCreate, ctx: Admin):
    existing = ctx.session.scalar(
        select(Target)
        .join(Tenant)
        .where(
            Tenant.tenant_code == payload.tenant,
            Target.controller_id == payload.controller_id,
        )
    )
    if existing:
        detail = (
            'Enable "Show deleted targets" and click Restore on the existing target.'
            if existing.deleted_at is not None
            else "Manage the existing target or use a different controller ID for a new device."
        )
        raise HTTPException(
            409, f"Target {payload.tenant}/{payload.controller_id} already exists. {detail}"
        )
    try:
        target, token = provision(
            ctx.session,
            payload.tenant,
            payload.controller_id,
            payload.name,
            actor=f"user:{ctx.user.id}",
        )
    except ValueError:
        raise HTTPException(400, "Invalid tenant or controller ID") from None
    target.description = payload.description
    record(ctx.session, ctx.user, "target.created", "target", target.id)
    return {"target": target_view(request, ctx.session, target), "token": token}


@router.get("/targets/{target_id}")
def target(request: Request, target_id: int, ctx: CurrentUser):
    return target_view(request, ctx.session, live_target(ctx.session, target_id))


@router.patch("/targets/{target_id}")
def edit_target(request: Request, target_id: int, payload: TargetPatch, ctx: Admin):
    target = live_target(ctx.session, target_id, lock=True)
    for key, value in payload.model_dump(exclude_unset=True).items():
        if value is None and key != "polling_interval_seconds":
            raise HTTPException(400, "Target fields cannot be null")
        setattr(target, key, value)
    record(ctx.session, ctx.user, "target.updated", "target", target.id)
    return target_view(request, ctx.session, target)


@router.post("/targets/{target_id}/rotate-token")
def rotate_token(target_id: int, ctx: Admin):
    token = rotate(
        ctx.session, live_target(ctx.session, target_id, lock=True), actor=f"user:{ctx.user.id}"
    )
    record(ctx.session, ctx.user, "target.token_rotated", "target", target_id)
    return {"token": token}


@router.post("/targets/{target_id}/revoke-token", status_code=204)
def revoke_token(target_id: int, ctx: Admin):
    revoke(ctx.session, live_target(ctx.session, target_id, lock=True), actor=f"user:{ctx.user.id}")
    record(ctx.session, ctx.user, "target.token_revoked", "target", target_id)


@router.delete("/targets/{target_id}", status_code=204)
def delete_target(target_id: int, ctx: Admin):
    target = get(ctx.session, Target, target_id, lock=True)
    if target.deleted_at is not None:
        return  # Idempotent deletion; retain the original audit timestamp.
    if ctx.session.scalar(
        select(Deployment.id).where(Deployment.target_id == target.id, Deployment.active.is_(True))
    ):
        raise HTTPException(
            409,
            "Target has an active deployment. Finish it or cancel it before discovery.",
        )
    target.enabled = False
    target.deleted_at = utcnow()
    revoke(ctx.session, target, actor=f"user:{ctx.user.id}")
    record(
        ctx.session,
        ctx.user,
        "target.deleted",
        "target",
        target.id,
        tenant_id=target.tenant_id,
        controller_id=target.controller_id,
    )


@router.post("/targets/{target_id}/restore")
def restore_target(request: Request, target_id: int, ctx: Admin):
    target = get(ctx.session, Target, target_id, lock=True)
    if target.deleted_at is not None:
        target.deleted_at = None
        target.enabled = False
        target.config_requested = True
        record(ctx.session, ctx.user, "target.restored", "target", target.id)
    return target_view(request, ctx.session, target)


@router.delete("/targets/{target_id}/permanent", status_code=204)
def purge_target(target_id: int, payload: TargetPurge, ctx: Admin):
    target = get(ctx.session, Target, target_id, lock=True)
    if target.deleted_at is None:
        raise HTTPException(409, "Delete the target before deleting it permanently")
    if payload.controller_id_confirmation != target.controller_id:
        raise HTTPException(400, "Type the exact controller ID to confirm permanent deletion")
    if ctx.session.scalar(
        select(Deployment.id).where(Deployment.target_id == target.id, Deployment.active.is_(True))
    ):
        raise HTTPException(409, "Target has an active deployment")
    deployments = select(Deployment.id).where(Deployment.target_id == target.id)
    ctx.session.execute(
        delete(DeploymentEvent).where(DeploymentEvent.deployment_id.in_(deployments))
    )
    # Clear retry links before removing the target's deployment history.
    ctx.session.execute(
        update(Deployment).where(Deployment.target_id == target.id).values(retry_of=None)
    )
    ctx.session.execute(delete(Deployment).where(Deployment.target_id == target.id))
    record(
        ctx.session,
        ctx.user,
        "target.permanently_deleted",
        "target",
        target.id,
        tenant_id=target.tenant_id,
        controller_id=target.controller_id,
        name=target.name,
    )
    # Attributes and credentials are removed by their ON DELETE CASCADE constraints.
    ctx.session.delete(target)


@router.get("/targets/{target_id}/history")
def target_history(target_id: int, ctx: CurrentUser):
    get(ctx.session, Target, target_id)
    return [
        row(d)
        for d in ctx.session.scalars(
            select(Deployment)
            .where(Deployment.target_id == target_id)
            .order_by(Deployment.id.desc())
        )
    ]


@router.get("/firmware")
def firmware(ctx: CurrentUser):
    return [
        row(a, ("storage_key",))
        for a in ctx.session.scalars(select(FirmwareArtifact).order_by(FirmwareArtifact.id.desc()))
    ]


@router.get("/firmware/{artifact_id}")
def firmware_detail(artifact_id: int, ctx: CurrentUser):
    return row(get(ctx.session, FirmwareArtifact, artifact_id), ("storage_key",))


class UploadTooLarge(MultiPartException):
    pass


@router.post("/firmware/upload", status_code=201)
async def upload(request: Request, ctx: Writer):
    # Authenticate before parsing/spooling; multipart parser writes large file parts to disk.
    limit = request.app.state.settings.max_upload_size_mb * 1024 * 1024
    total = 0

    async def bounded_stream():
        nonlocal total
        async for chunk in request.stream():
            total += len(chunk)
            if total > limit + 65536:
                raise UploadTooLarge("Firmware upload exceeds limit")
            yield chunk

    parser = MultiPartParser(
        request.headers, bounded_stream(), max_files=1, max_fields=5, max_part_size=16384
    )
    try:
        form = await parser.parse()
    except UploadTooLarge:
        raise HTTPException(413, "Firmware upload exceeds limit") from None
    except MultiPartException:
        raise HTTPException(400, "Invalid multipart firmware upload") from None
    try:
        file = form.get("file")
        if not hasattr(file, "file") or not file.filename:
            raise HTTPException(400, "Select a .raucb firmware file")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,193}\.raucb", file.filename):
            raise HTTPException(400, "Use a safe .raucb filename (letters, numbers, dots, _ or -)")
        try:
            metadata = FirmwareMetadata.model_validate(
                {k: v for k, v in form.items() if k != "file"}
            )
        except ValueError:
            raise HTTPException(
                400, "Firmware name, version and compatible string are required"
            ) from None
        try:
            info = await run_in_threadpool(request.app.state.storage.publish, file.file, limit)
        except OSError:
            raise HTTPException(507, "Artifact storage is unavailable or full") from None
        existing = ctx.session.scalar(
            select(FirmwareArtifact).where(FirmwareArtifact.sha256 == info["sha256"])
        )
        if existing:
            detail = (
                "It is withdrawn. Close this dialog and click Restore on the Firmware page."
                if not existing.available
                else "Use the existing firmware on the Firmware page."
            )
            raise HTTPException(
                409, f"Identical artifact already exists as firmware #{existing.id}. {detail}"
            )
        artifact = FirmwareArtifact(
            **metadata.model_dump(), **info, filename=file.filename, uploaded_by=ctx.user.id
        )
        ctx.session.add(artifact)
        ctx.session.flush()
        record(
            ctx.session,
            ctx.user,
            "firmware.uploaded",
            "firmware",
            artifact.id,
            sha256=artifact.sha256,
            size=artifact.size,
        )
        return row(artifact, ("storage_key",))
    finally:
        await form.close()


@router.delete("/firmware/{artifact_id}", status_code=204)
def withdraw(artifact_id: int, ctx: Writer):
    artifact = get(ctx.session, FirmwareArtifact, artifact_id, lock=True)
    if ctx.session.scalar(
        select(Deployment.id).where(
            Deployment.artifact_id == artifact_id, Deployment.active.is_(True)
        )
    ):
        raise HTTPException(409, "Artifact is required by an active deployment")
    artifact.available = False
    # Tombstone only: historical action references remain intact, no unlink/download race.
    record(ctx.session, ctx.user, "firmware.withdrawn", "firmware", artifact.id)


@router.post("/firmware/{artifact_id}/restore")
def restore_firmware(artifact_id: int, ctx: Writer):
    artifact = get(ctx.session, FirmwareArtifact, artifact_id, lock=True)
    if not artifact.available:
        artifact.available = True
        record(ctx.session, ctx.user, "firmware.restored", "firmware", artifact.id)
    return row(artifact, ("storage_key",))


@router.get("/software-modules")
def modules(ctx: CurrentUser):
    return [
        row(m)
        for m in ctx.session.scalars(select(SoftwareModule).order_by(SoftwareModule.id.desc()))
    ]


@router.post("/software-modules", status_code=201)
def create_module(payload: ModuleCreate, ctx: Writer):
    if not get(ctx.session, FirmwareArtifact, payload.artifact_id).available:
        raise HTTPException(409, "Artifact is withdrawn")
    module = SoftwareModule(**payload.model_dump())
    ctx.session.add(module)
    ctx.session.flush()
    record(ctx.session, ctx.user, "module.created", "module", module.id)
    return row(module)


@router.get("/distributions")
def distributions(ctx: CurrentUser):
    return [
        row(d) for d in ctx.session.scalars(select(Distribution).order_by(Distribution.id.desc()))
    ]


@router.post("/distributions", status_code=201)
def create_distribution(payload: DistributionCreate, ctx: Writer):
    get(ctx.session, SoftwareModule, payload.module_id)
    distribution = Distribution(**payload.model_dump())
    ctx.session.add(distribution)
    ctx.session.flush()
    record(ctx.session, ctx.user, "distribution.created", "distribution", distribution.id)
    return row(distribution)


@router.patch("/distributions/{distribution_id}")
def edit_distribution(distribution_id: int, payload: DistributionPatch, ctx: Writer):
    distribution = get(ctx.session, Distribution, distribution_id, lock=True)
    distribution.description = payload.description
    record(ctx.session, ctx.user, "distribution.updated", "distribution", distribution.id)
    return row(distribution)


@router.get("/deployments")
def deployments(ctx: CurrentUser):
    return [row(d) for d in ctx.session.scalars(select(Deployment).order_by(Deployment.id.desc()))]


@router.post("/deployments", status_code=201)
def create_deployment(request: Request, payload: DeploymentCreate, ctx: Writer):
    return row(assign(ctx.session, ctx.user, payload, request.app.state.storage))


@router.get("/deployments/{deployment_id}")
def deployment(deployment_id: int, ctx: CurrentUser):
    return row(get(ctx.session, Deployment, deployment_id))


@router.get("/deployments/{deployment_id}/events")
def events(deployment_id: int, ctx: CurrentUser):
    get(ctx.session, Deployment, deployment_id)
    return [
        row(e)
        for e in ctx.session.scalars(
            select(DeploymentEvent)
            .where(DeploymentEvent.deployment_id == deployment_id)
            .order_by(DeploymentEvent.id)
        )
    ]


@router.post("/deployments/{deployment_id}/cancel")
def cancel(deployment_id: int, ctx: Writer):
    initial = get(ctx.session, Deployment, deployment_id)
    get(ctx.session, Target, initial.target_id, lock=True)
    deployment = get(ctx.session, Deployment, deployment_id, lock=True)
    ctx.session.refresh(deployment)
    if not deployment.active or deployment.internal_status != "WAITING_FOR_TARGET":
        raise HTTPException(409, "Only an undiscovered assignment can be canceled safely")
    deployment.active = False
    deployment.internal_status = "CANCELED"
    deployment.completed_at = utcnow()
    event(ctx.session, deployment, "canceled", "Canceled by operator before discovery")
    record(ctx.session, ctx.user, "deployment.canceled", "deployment", deployment.id)
    return row(deployment)


@router.post("/deployments/{deployment_id}/retry", status_code=201)
def retry(request: Request, deployment_id: int, payload: RetryRequest, ctx: Writer):
    previous = get(ctx.session, Deployment, deployment_id)
    if previous.active or previous.internal_status not in {"INSTALL_FAILED", "REJECTED"}:
        raise HTTPException(409, "Only a failed or rejected deployment can be explicitly retried")
    confirmation = DeploymentCreate(
        **payload.model_dump(),
        target_id=previous.target_id,
        distribution_id=previous.distribution_id,
        mode=previous.mode,
        expected_compatible=previous.snapshot["compatible"],
        expected_version=previous.snapshot["distribution_version"],
    )
    return row(assign(ctx.session, ctx.user, confirmation, request.app.state.storage, previous))


@router.get("/dashboard/summary")
def summary(request: Request, ctx: CurrentUser):
    statuses = [
        describe(ctx.session, t, request.app.state.settings.offline_threshold_seconds)[
            "connection_status"
        ]
        for t in ctx.session.scalars(select(Target).where(Target.deleted_at.is_(None)))
    ]
    counts = dict(
        ctx.session.execute(
            select(Deployment.internal_status, func.count()).group_by(Deployment.internal_status)
        ).all()
    )
    return {
        "total_targets": len(statuses),
        "online_targets": statuses.count("Online"),
        "offline_targets": statuses.count("Offline"),
        "never_connected": statuses.count("Never Connected"),
        "firmware_versions": ctx.session.scalar(select(func.count()).select_from(FirmwareArtifact)),
        "active_deployments": ctx.session.scalar(
            select(func.count()).select_from(Deployment).where(Deployment.active.is_(True))
        ),
        "successful_installations": counts.get("INSTALL_SUCCEEDED", 0),
        "failed_installations": counts.get("INSTALL_FAILED", 0),
        "pending_deployments": counts.get("WAITING_FOR_TARGET", 0),
        "states": counts,
    }


@router.get("/audit-logs")
def audit_logs(ctx: Admin, limit: int = 100, before: int | None = None):
    query = select(AuditLog).order_by(AuditLog.id.desc()).limit(max(1, min(limit, 500)))
    if before:
        query = query.where(AuditLog.id < before)
    return [row(a) for a in ctx.session.scalars(query)]


@router.get("/settings")
def settings(request: Request, ctx: CurrentUser):
    config = request.app.state.settings
    return {
        k: getattr(config, k)
        for k in (
            "app_name",
            "app_env",
            "public_base_url",
            "polling_interval_seconds",
            "offline_threshold_seconds",
            "max_upload_size_mb",
            "session_hours",
        )
    }


@router.get("/users")
def users(ctx: Admin):
    return [user_view(user) for user in ctx.session.scalars(select(User).order_by(User.id))]


@router.post("/users", status_code=201)
def create_user(payload: UserCreate, ctx: Admin):
    user = User(
        username=payload.username,
        password_hash=password_hasher.hash(payload.password),
        role=payload.role,
    )
    ctx.session.add(user)
    ctx.session.flush()
    record(ctx.session, ctx.user, "user.created", "user", user.id, role=user.role)
    return user_view(user)


@router.patch("/users/{user_id}")
def edit_user(user_id: int, payload: UserPatch, ctx: Admin):
    if user_id == ctx.user.id:
        raise HTTPException(409, "Cannot disable your own account")
    user = get(ctx.session, User, user_id, lock=True)
    user.is_active = payload.is_active
    if not user.is_active:
        for login in ctx.session.scalars(select(UserSession).where(UserSession.user_id == user.id)):
            ctx.session.delete(login)
    record(ctx.session, ctx.user, "user.updated", "user", user.id, active=user.is_active)
    return user_view(user)
