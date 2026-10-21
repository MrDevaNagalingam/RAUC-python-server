import argparse
import getpass
import json
import os
import re
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import Settings
from app.database.models import Target, Tenant, User, UserSession
from app.database.session import build_engine, session_factory
from app.services.targets import audit, describe, find_target, provision, revoke, rotate


def write_secret(path, token):
    # Refuse overwrite and symlink following. Tokens never go into stdout or shell arguments.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(token + "\n")
            stream.flush()
            os.fsync(stream.fileno())
    except OSError:
        Path(path).unlink(missing_ok=True)
        raise


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="OTA local operator CLI (requires database access)"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    for command in (
        "target-create",
        "target-show",
        "target-disable",
        "target-enable",
        "token-rotate",
        "token-revoke",
        "request-config",
    ):
        cmd = commands.add_parser(command)
        cmd.add_argument("controller_id")
        cmd.add_argument("--tenant", default=None)
        if command in {"target-create", "token-rotate"}:
            cmd.add_argument("--token-file", required=True)
        if command == "target-create":
            cmd.add_argument("--name")
    commands.add_parser("target-list")
    for action in ("admin-create", "admin-password-reset"):
        cmd = commands.add_parser(action)
        cmd.add_argument("username")
    args = parser.parse_args(argv)
    settings = Settings()
    engine = build_engine(settings.database_url)
    secret_created = False
    try:
        if args.command in {"admin-create", "admin-password-reset"}:
            from app.management.auth import password_hasher, record

            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", args.username):
                raise ValueError("Invalid username")
            password = getpass.getpass("New administrator password (minimum 12 characters): ")
            if len(password) < 12 or len(password) > 256:
                raise ValueError("Password must contain 12–256 characters")
            if password != getpass.getpass("Confirm password: "):
                raise ValueError("Passwords do not match")
            with session_factory(engine)() as session, session.begin():
                user = session.scalar(select(User).where(User.username == args.username))
                if args.command == "admin-create":
                    if user:
                        raise ValueError("Username already exists")
                    user = User(
                        username=args.username,
                        password_hash=password_hasher.hash(password),
                        role="admin",
                    )
                    session.add(user)
                    session.flush()
                else:
                    if user is None or user.role != "admin":
                        raise ValueError("Administrator not found")
                    user.password_hash = password_hasher.hash(password)
                    user.is_active = True
                    for login in session.scalars(
                        select(UserSession).where(UserSession.user_id == user.id)
                    ):
                        session.delete(login)
                record(session, user, args.command, "user", user.id)
            print("Administrator credentials saved. Sign in at your server's dashboard URL.")
            return
        with session_factory(engine)() as session, session.begin():
            if args.command == "target-list":
                output = [
                    describe(session, t, settings.offline_threshold_seconds)
                    for t in session.scalars(
                        select(Target).where(Target.deleted_at.is_(None)).order_by(Target.id)
                    )
                ]
            else:
                tenant = args.tenant or settings.default_tenant
                if args.command == "target-create":
                    target, token = provision(session, tenant, args.controller_id, args.name)
                else:
                    target = find_target(session, tenant, args.controller_id, lock=True)
                    if target is None:
                        raise ValueError("Target not found")
                    if args.command == "token-rotate":
                        token = rotate(session, target)
                    elif args.command == "token-revoke":
                        revoke(session, target)
                    elif args.command in {"target-disable", "target-enable"}:
                        target.enabled = args.command == "target-enable"
                        audit(session, args.command, target.id)
                    elif args.command == "request-config":
                        target.config_requested = True
                        audit(session, "config.requested", target.id)
                session.flush()
                if args.command in {"target-create", "token-rotate"}:
                    write_secret(args.token_file, token)
                    secret_created = True
                output = describe(session, target, settings.offline_threshold_seconds)
                output["tenant"] = session.get(Tenant, target.tenant_id).tenant_code
        print(json.dumps(output, indent=2))
    except (ValueError, OSError, SQLAlchemyError):
        if secret_created:
            Path(args.token_file).unlink(missing_ok=True)
        # DB exception messages may contain bound credentials or sensitive paths.
        parser.exit(
            1,
            "Operation failed. Check target identity, duplicates, migrations, "
            "database access and token-file permissions (file must not exist).\n",
        )
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
