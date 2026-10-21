import hmac
from dataclasses import dataclass
from datetime import UTC, timedelta
from typing import Annotated, Literal

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from app.core.security import generate_token, hash_token
from app.database.models import AuditLog, LoginThrottle, User, UserSession, utcnow

router = APIRouter(prefix="/api/auth", tags=["Management authentication"])
password_hasher = PasswordHasher()
dummy_hash = password_hasher.hash(generate_token())
COOKIE = "ota_session"


def as_utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def database(request: Request):
    with request.app.state.sessions() as session:
        if (
            session.bind.dialect.name == "sqlite"
            and request.method not in {"GET", "HEAD", "OPTIONS"}
            and request.url.path != "/api/firmware/upload"
        ):
            session.execute(text("BEGIN IMMEDIATE"))
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise


DB = Annotated[Session, Depends(database, scope="function")]


def record(session, user, operation, resource_type, resource_id=None, **details):
    session.add(
        AuditLog(
            actor=f"user:{user.id}" if user else "anonymous",
            operation=operation,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            details=details,
        )
    )


def check_origin(request):
    origin = request.headers.get("origin")
    if origin and origin not in {
        request.app.state.settings.public_base_url,
        str(request.base_url).rstrip("/"),
    }:
        raise HTTPException(403, "Origin not allowed")


@dataclass
class UserContext:
    session: Session
    user: User
    login: UserSession


def authenticated_user(request: Request, session: DB):
    token = request.cookies.get(COOKIE, "")
    login = session.get(UserSession, hash_token(token)) if token else None
    user = session.get(User, login.user_id) if login else None
    if not login or as_utc(login.expires_at) <= utcnow() or not user or not user.is_active:
        raise HTTPException(401, "Sign in required")
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        check_origin(request)
        if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), login.csrf_token):
            raise HTTPException(403, "Invalid CSRF token")
    return UserContext(session, user, login)


CurrentUser = Annotated[UserContext, Depends(authenticated_user)]


def writer(user: CurrentUser):
    if user.user.role not in {"admin", "operator"}:
        raise HTTPException(403, "Operator role required")
    return user


def administrator(user: CurrentUser):
    if user.user.role != "admin":
        raise HTTPException(403, "Administrator role required")
    return user


Writer = Annotated[UserContext, Depends(writer)]
Admin = Annotated[UserContext, Depends(administrator)]


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserCreate(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9_.-]{1,64}$")
    password: str = Field(min_length=12, max_length=256)
    role: Literal["admin", "operator", "viewer"] = "viewer"


def user_view(user):
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
        "is_active": user.is_active,
        "created_at": user.created_at,
    }


@router.post("/login")
def login(request: Request, response: Response, payload: LoginRequest, session: DB):
    check_origin(request)
    now = utcnow()
    # Persist throttling across workers/restarts; origin headers are never used as client IP.
    keys = [
        (hash_token("ip:" + (request.client.host if request.client else "unknown")), 50),
        (hash_token("user:" + payload.username), 8),
    ]
    throttles = []
    for key, limit in keys:
        throttle = session.scalar(
            select(LoginThrottle).where(LoginThrottle.key == key).with_for_update()
        )
        if throttle is None:
            throttle = LoginThrottle(key=key, count=0, window_at=now)
            session.add(throttle)
        elif now - as_utc(throttle.window_at) >= timedelta(minutes=5):
            throttle.count, throttle.window_at = 0, now
        if throttle.count >= limit:
            raise HTTPException(429, "Too many sign-in attempts; try again in five minutes")
        throttles.append(throttle)
    user = session.scalar(select(User).where(User.username == payload.username))
    valid = False
    try:
        valid = password_hasher.verify(user.password_hash if user else dummy_hash, payload.password)
    except VerificationError:
        pass
    if not valid or not user or not user.is_active:
        for throttle in throttles:
            throttle.count += 1
        record(session, None, "auth.login_failed", "user")
        session.commit()
        raise HTTPException(401, "Invalid username or password")
    throttles[1].count = 0
    # Keep expired sessions/throttles from growing without bounds.
    session.execute(
        delete(UserSession)
        .where(UserSession.expires_at <= now)
        .execution_options(synchronize_session=False)
    )
    session.execute(
        delete(LoginThrottle)
        .where(LoginThrottle.window_at < now - timedelta(days=1))
        .execution_options(synchronize_session=False)
    )
    token, csrf = generate_token(), generate_token()
    session.add(
        UserSession(
            token_hash=hash_token(token),
            user_id=user.id,
            csrf_token=csrf,
            expires_at=now + timedelta(hours=request.app.state.settings.session_hours),
        )
    )
    record(session, user, "auth.login", "user", user.id)
    response.set_cookie(
        COOKIE,
        token,
        httponly=True,
        samesite="strict",
        path="/",
        secure=request.app.state.settings.app_env == "production",
        max_age=request.app.state.settings.session_hours * 3600,
    )
    return {"user": user_view(user), "csrf_token": csrf}


@router.get("/me")
def me(context: CurrentUser):
    return {"user": user_view(context.user), "csrf_token": context.login.csrf_token}


@router.post("/logout", status_code=204)
def logout(response: Response, context: CurrentUser):
    context.session.delete(context.login)
    record(context.session, context.user, "auth.logout", "user", context.user.id)
    response.delete_cookie(COOKIE, path="/")
