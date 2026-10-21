import logging

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.database.models import Deployment, utcnow
from app.ddi.auth import Device
from app.ddi.schemas import ControllerResponse
from app.services.deployment_engine import advance, event

router = APIRouter(prefix="/{tenant}/controller/v1/{controller_id}", tags=["DDI v1"])
log = logging.getLogger("ota")


@router.get("", response_model=ControllerResponse)
def poll(request: Request, device: Device):
    target = device.target
    now = utcnow()
    target.last_seen_at = target.last_request_at = target.last_poll_at = now
    interval = (
        target.polling_interval_seconds or request.app.state.settings.polling_interval_seconds
    )
    sleep = f"{interval // 3600:02}:{interval // 60 % 60:02}:{interval % 60:02}"
    links = {}
    deployment = device.session.scalar(
        select(Deployment)
        .where(Deployment.target_id == target.id, Deployment.active.is_(True))
        .with_for_update()
    )
    if deployment:
        if deployment.internal_status == "WAITING_FOR_TARGET":
            advance(deployment, "DISCOVERED")
            deployment.started_at = now
            event(device.session, deployment, "discovered", "Target received deployment link")
        links["deploymentBase"] = {
            "href": request.app.state.settings.public_base_url
            + request.url.path
            + f"/deploymentBase/{deployment.id}"
        }
    if target.config_requested:
        # Never derive public URLs from untrusted Host or X-Forwarded-* headers.
        links["configData"] = {
            "href": request.app.state.settings.public_base_url + request.url.path + "/configData"
        }
    log.info(
        "device.poll",
        extra={"fields": {"target_id": target.id, "request_id": request.state.request_id}},
    )
    return {"config": {"polling": {"sleep": sleep}}, "_links": links}
