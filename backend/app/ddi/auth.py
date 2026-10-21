import logging
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.security import hash_token, verify_token
from app.database.models import Target, TargetCredential
from app.services.targets import audit, find_target

log = logging.getLogger("ota")


@dataclass
class DeviceContext:
    session: Session
    target: Target


def authenticated_device(request: Request, tenant: str, controller_id: str):
    with request.app.state.sessions() as session:
        # SQLite has no row locks. Serialize these short write transactions in local development.
        # PostgreSQL locks only the selected target row, allowing unrelated targets concurrently.
        if session.bind.dialect.name == "sqlite":
            session.execute(text("BEGIN IMMEDIATE"))
        try:
            target = find_target(session, tenant, controller_id, lock=True)
            credential = (
                session.scalar(
                    select(TargetCredential).where(
                        TargetCredential.target_id == target.id,
                        TargetCredential.is_active.is_(True),
                    )
                )
                if target
                else None
            )
            header = request.headers.get("authorization", "")
            parts = header.split(" ")
            scheme_ok = len(parts) == 2 and parts[0].lower() == "targettoken"
            token = parts[1] if scheme_ok else ""
            expected_hash = credential.token_hash if credential else hash_token("dummy-credential")
            valid = verify_token(token, expected_hash)
            if (
                not scheme_ok
                or not token
                or len(token) > 512
                or not valid
                or not target
                or not target.enabled
                or not credential
            ):
                audit(session, "device.authentication_failed", actor="anonymous-device")
                session.commit()
                log.warning(
                    "device.authentication_failed",
                    extra={"fields": {"request_id": request.state.request_id}},
                )
                raise HTTPException(
                    401, "Device authentication failed", headers={"WWW-Authenticate": "TargetToken"}
                )
            yield DeviceContext(session, target)
            session.commit()
        except Exception:
            session.rollback()
            raise


Device = Annotated[DeviceContext, Depends(authenticated_device, scope="function")]
