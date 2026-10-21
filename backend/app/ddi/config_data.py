import logging

from fastapi import HTTPException, Request, Response
from sqlalchemy import select

from app.database.models import TargetAttribute, utcnow
from app.ddi.auth import Device
from app.ddi.controller import router
from app.ddi.schemas import ConfigData
from app.services.targets import audit

log = logging.getLogger("ota")


@router.put("/configData", response_class=Response, status_code=200)
def put_config_data(request: Request, payload: ConfigData, device: Device):
    session, target = device.session, device.target
    current = {
        a.attribute_key: a
        for a in session.scalars(
            select(TargetAttribute).where(TargetAttribute.target_id == target.id)
        )
    }
    if payload.mode == "merge" and len(current.keys() | payload.data.keys()) > 100:
        raise HTTPException(400, "Target attribute limit exceeded")
    for key, attribute in current.items():
        if (
            payload.mode == "replace"
            and key not in payload.data
            or payload.mode == "remove"
            and key in payload.data
        ):
            session.delete(attribute)
    if payload.mode != "remove":
        for key, value in payload.data.items():
            if key in current:
                current[key].attribute_value = value
            else:
                session.add(
                    TargetAttribute(target_id=target.id, attribute_key=key, attribute_value=value)
                )
    target.config_requested = False
    target.last_seen_at = target.last_request_at = utcnow()
    audit(
        session,
        "device.config_data",
        target.id,
        actor="device",
        mode=payload.mode,
        attribute_count=len(payload.data),
        request_id=request.state.request_id,
    )
    log.info(
        "device.config_data",
        extra={"fields": {"target_id": target.id, "request_id": request.state.request_id}},
    )
    return Response(status_code=200)
