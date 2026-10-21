import logging
import re

from fastapi import HTTPException, Request, Response
from sqlalchemy import select
from starlette.responses import StreamingResponse

from app.database.models import Deployment, utcnow
from app.ddi.auth import Device
from app.ddi.controller import router
from app.ddi.schemas import Feedback
from app.services.deployment_engine import advance, event, receive_feedback

log = logging.getLogger("ota")


def owned(device, action_id):
    deployment = device.session.scalar(
        select(Deployment)
        .where(
            Deployment.id == action_id,
            Deployment.target_id == device.target.id,
            Deployment.tenant_id == device.target.tenant_id,
        )
        .with_for_update()
    )
    if deployment is None:
        raise HTTPException(404, "Action not found")
    return deployment


@router.get("/deploymentBase/{action_id}")
def deployment_base(request: Request, action_id: int, device: Device):
    deployment = owned(device, action_id)
    if not deployment.active:
        raise HTTPException(410, "Action is no longer active")
    advance(deployment, "DISCOVERED")
    deployment.started_at = deployment.started_at or utcnow()
    device.target.last_seen_at = device.target.last_request_at = utcnow()
    snapshot = deployment.snapshot
    base = request.app.state.settings.public_base_url
    controller_path = request.url.path.rsplit("/deploymentBase/", 1)[0]
    url = (
        f"{base}{controller_path}/softwaremodules/{deployment.module_id}"
        f"/artifacts/{snapshot['filename']}"
    )
    link_name = "download" if base.startswith("https:") else "download-http"
    return {
        "id": str(deployment.id),
        "deployment": {
            "download": "forced",
            "update": "skip" if deployment.mode == "download_only" else "forced",
            "chunks": [
                {
                    "part": snapshot["module_type"],
                    "version": snapshot["module_version"],
                    "name": snapshot["module_name"],
                    "artifacts": [
                        {
                            "filename": snapshot["filename"],
                            "size": snapshot["size"],
                            "hashes": {key: snapshot[key] for key in ("sha1", "md5", "sha256")},
                            "_links": {link_name: {"href": url}},
                        }
                    ],
                }
            ],
        },
    }


@router.post("/deploymentBase/{action_id}/feedback", response_class=Response, status_code=200)
def feedback(action_id: int, payload: Feedback, device: Device):
    if payload.id != str(action_id):
        raise HTTPException(400, "Feedback ID does not match action URL")
    deployment = owned(device, action_id)
    receive_feedback(device.session, device.target, deployment, payload)
    return Response(status_code=200)


def parse_range(value, size):
    if not value:
        return 0, size - 1, 200
    match = re.fullmatch(r"bytes=(\d{0,20})-(\d{0,20})", value)
    if not match or not any(match.groups()):
        raise HTTPException(
            416, "Unsupported byte range", headers={"Content-Range": f"bytes */{size}"}
        )
    left, right = match.groups()
    if left:
        start = int(left)
        end = min(int(right), size - 1) if right else size - 1
    else:
        start, end = max(0, size - int(right)), size - 1
    if start > end or start >= size:
        raise HTTPException(
            416, "Unsatisfiable byte range", headers={"Content-Range": f"bytes */{size}"}
        )
    return start, end, 206


@router.api_route("/softwaremodules/{module_id}/artifacts/{filename}", methods=["GET", "HEAD"])
def artifact_download(request: Request, module_id: int, filename: str, device: Device):
    # A module ID never authorizes access by itself; require this target's active action.
    deployment = device.session.scalar(
        select(Deployment)
        .where(
            Deployment.target_id == device.target.id,
            Deployment.tenant_id == device.target.tenant_id,
            Deployment.module_id == module_id,
            Deployment.active.is_(True),
        )
        .with_for_update()
    )
    if deployment is None or deployment.snapshot["filename"] != filename:
        raise HTTPException(404, "Artifact not assigned to this target")
    snapshot = deployment.snapshot
    path = request.app.state.storage.path(snapshot["storage_key"])
    if not path.is_file() or path.stat().st_size != snapshot["size"]:
        raise HTTPException(503, "Assigned artifact is unavailable")
    etag = '"' + snapshot["sha256"] + '"'
    range_header = request.headers.get("range")
    if request.headers.get("if-range") not in {None, etag}:
        range_header = None
    start, end, status = parse_range(range_header, snapshot["size"])
    headers = {
        "Content-Length": str(end - start + 1),
        "Accept-Ranges": "bytes",
        "ETag": etag,
        "Content-Disposition": f'attachment; filename="{snapshot["filename"]}"',
    }
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{snapshot['size']}"
    device.target.last_seen_at = device.target.last_request_at = utcnow()
    if request.method == "HEAD":
        return Response(status_code=status, headers=headers, media_type="application/octet-stream")
    advance(deployment, "DOWNLOADING")
    event(device.session, deployment, "download.requested", f"Serving bytes {start}-{end}")

    def stream():
        remaining = end - start + 1
        try:
            with path.open("rb") as source:
                source.seek(start)
                while remaining:
                    chunk = source.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise OSError("Artifact changed during download")
                    remaining -= len(chunk)
                    yield chunk
        finally:
            log.info(
                "artifact.stream_finished",
                extra={
                    "fields": {
                        "action_id": deployment.id,
                        "target_id": device.target.id,
                        "request_id": request.state.request_id,
                        "complete_stream": remaining == 0,
                        "bytes_read": end - start + 1 - remaining,
                    }
                },
            )
        # Serving a complete stream is not proof of client checksum/install completion.

    return StreamingResponse(
        stream(), status_code=status, headers=headers, media_type="application/octet-stream"
    )
