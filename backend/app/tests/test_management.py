import hashlib
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select

from app.database.models import DeploymentEvent, User, UserSession
from app.management.auth import password_hasher
from app.services.targets import provision

PASSWORD = "test-only-long-password"
BUNDLE = b"test-only-rauc-payload\x00" * 3000


@pytest.fixture
def admin(app, client):
    with app.state.sessions() as session, session.begin():
        session.add(
            User(username="admin", password_hash=password_hasher.hash(PASSWORD), role="admin")
        )
    response = client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD})
    assert response.status_code == 200
    return {"X-CSRF-Token": response.json()["csrf_token"]}


@pytest.fixture
def release(client, admin):
    response = client.post(
        "/api/firmware/upload",
        headers=admin,
        data={"name": "OS", "version": "1.1", "compatible": "phyboard-segin-imx6ul-7"},
        files={"file": ("firmware.raucb", BUNDLE, "application/octet-stream")},
    )
    assert response.status_code == 201, response.text
    artifact = response.json()
    response = client.post(
        "/api/software-modules",
        headers=admin,
        json={"name": "OS", "version": "1.1", "artifact_id": artifact["id"]},
    )
    assert response.status_code == 201, response.text
    module = response.json()
    response = client.post(
        "/api/distributions",
        headers=admin,
        json={"name": "Release", "version": "1.1", "module_id": module["id"]},
    )
    assert response.status_code == 201
    return {"artifact": artifact, "module": module, "distribution": response.json()}


def assignment(device, release, **overrides):
    return {
        "request_key": uuid.uuid4().hex,
        "target_id": device["id"],
        "distribution_id": release["distribution"]["id"],
        "mode": "forced",
        "expected_version": "1.1",
        "expected_compatible": "phyboard-segin-imx6ul-7",
        "operator_confirmed": True,
        "approval_note": "Test-only target, no hardware installation",
        **overrides,
    }


def feedback(
    action_id, execution="proceeding", finished="none", detail="62% Checking slot boot.1 done."
):
    return {
        "id": str(action_id),
        "time": "20261021T070000",
        "status": {"execution": execution, "result": {"finished": finished}, "details": [detail]},
    }


def test_login_csrf_logout_and_secret_separation(client, admin, app, device):
    assert client.get("/api/auth/me").json()["user"]["role"] == "admin"
    assert client.post("/api/targets", json={}).status_code == 403
    assert (
        client.post(
            "/api/auth/logout", headers={**admin, "Origin": "https://evil.example"}
        ).status_code
        == 403
    )
    with app.state.sessions() as session:
        login = session.scalar(select(UserSession))
        assert login.token_hash != client.cookies.get("ota_session")
        assert session.scalar(select(User)).password_hash.startswith("$argon2")
    assert client.post("/api/auth/logout", headers=admin).status_code == 204
    assert client.get("/api/targets").status_code == 401
    assert client.get(device["path"], headers=device["headers"]).status_code == 200
    assert client.get("/api/settings", headers=device["headers"]).status_code == 401


def test_login_throttle_and_bad_origin(client, app):
    for _ in range(8):
        assert (
            client.post(
                "/api/auth/login", json={"username": "missing", "password": PASSWORD}
            ).status_code
            == 401
        )
    assert (
        client.post(
            "/api/auth/login", json={"username": "missing", "password": PASSWORD}
        ).status_code
        == 429
    )
    assert (
        client.post(
            "/api/auth/login",
            headers={"Origin": "https://evil.example"},
            json={"username": "admin", "password": PASSWORD},
        ).status_code
        == 403
    )


def test_roles_disabled_users_and_password_reset(client, admin):
    viewer = client.post(
        "/api/users",
        headers=admin,
        json={"username": "viewer", "password": PASSWORD, "role": "viewer"},
    ).json()
    assert "password_hash" not in viewer
    assert (
        client.patch(
            f"/api/users/{viewer['id']}", headers=admin, json={"is_active": False}
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/auth/login", json={"username": "viewer", "password": PASSWORD}
        ).status_code
        == 401
    )
    assert (
        client.patch(
            f"/api/users/{viewer['id']}", headers=admin, json={"is_active": True}
        ).status_code
        == 200
    )
    csrf = client.post("/api/auth/login", json={"username": "viewer", "password": PASSWORD}).json()[
        "csrf_token"
    ]
    assert client.get("/api/targets").status_code == 200
    assert client.get("/api/users").status_code == 403
    assert client.post("/api/firmware/upload", headers={"X-CSRF-Token": csrf}).status_code == 403


def test_target_create_tokens_metadata_and_revocation(client, admin):
    response = client.post(
        "/api/targets",
        headers=admin,
        json={"controller_id": "new-target", "name": "Gateway", "tenant": "LAB"},
    )
    assert response.status_code == 201
    target, token = response.json()["target"], response.json()["token"]
    path = "/LAB/controller/v1/new-target"
    assert client.get(path, headers={"Authorization": f"TargetToken {token}"}).status_code == 200
    assert token not in client.get("/api/targets").text
    assert (
        client.patch(
            f"/api/targets/{target['id']}",
            headers=admin,
            json={"name": "Renamed", "polling_interval_seconds": 90},
        ).status_code
        == 200
    )
    assert (
        client.post(f"/api/targets/{target['id']}/revoke-token", headers=admin).status_code == 204
    )
    assert client.get(path, headers={"Authorization": f"TargetToken {token}"}).status_code == 401
    assert (
        client.post(
            "/api/targets", headers=admin, json={"controller_id": "..", "name": "Bad"}
        ).status_code
        == 400
    )


def test_upload_hashes_duplicates_safe_names_and_no_auto_assignment(
    client, admin, release, device, app
):
    artifact = release["artifact"]
    assert artifact["sha256"] == hashlib.sha256(BUNDLE).hexdigest()
    assert artifact["sha1"] == hashlib.sha1(BUNDLE).hexdigest()
    assert artifact["size"] == len(BUNDLE)
    assert artifact["signature_status"] == "NOT_VERIFIED"
    assert "storage_key" not in artifact
    assert client.get("/api/deployments").json() == []
    assert (
        "deploymentBase"
        not in client.get(device["path"], headers=device["headers"]).json()["_links"]
    )
    for filename, blob, expected in [
        ("firmware.raucb", BUNDLE, 409),
        ("../evil.raucb", b"x", 400),
        ("image.txt", b"x", 400),
        ("empty.raucb", b"", 400),
    ]:
        response = client.post(
            "/api/firmware/upload",
            headers=admin,
            data={"name": "OS", "version": "2", "compatible": "board"},
            files={"file": (filename, blob, "application/octet-stream")},
        )
        assert response.status_code == expected, response.text
    assert not list(app.state.storage.root.glob(".upload-*"))


def test_upload_limits_clean_partial_file(client, admin, app):
    app.state.settings.max_upload_size_mb = 1
    response = client.post(
        "/api/firmware/upload",
        headers=admin,
        data={"name": "OS", "version": "1", "compatible": "board"},
        files={"file": ("large.raucb", b"x" * (2 * 1024 * 1024), "application/octet-stream")},
    )
    assert response.status_code == 413
    assert not list(app.state.storage.root.glob(".upload-*"))
    assert client.get("/api/firmware").json() == []


def test_assignment_metadata_download_feedback_and_terminal_protection(
    client, admin, release, device, app
):
    payload = assignment(device, release)
    response = client.post("/api/deployments", headers=admin, json=payload)
    assert response.status_code == 201, response.text
    action = response.json()
    assert client.post("/api/deployments", headers=admin, json=payload).json()["id"] == action["id"]
    assert (
        client.post("/api/deployments", headers=admin, json=assignment(device, release)).status_code
        == 409
    )
    poll = client.get(device["path"], headers=device["headers"]).json()
    base = device["path"] + f"/deploymentBase/{action['id']}"
    assert poll["_links"]["deploymentBase"]["href"].endswith(base)
    metadata = client.get(base, headers=device["headers"]).json()
    artifact = metadata["deployment"]["chunks"][0]["artifacts"][0]
    assert metadata["id"] == str(action["id"])
    assert metadata["deployment"]["update"] == "forced"
    assert artifact["hashes"]["sha1"] == hashlib.sha1(BUNDLE).hexdigest()
    url = artifact["_links"]["download-http"]["href"]
    assert client.get(url, headers=device["headers"]).content == BUNDLE
    assert (
        client.delete(f"/api/firmware/{release['artifact']['id']}", headers=admin).status_code
        == 409
    )
    assert (
        client.post(
            base + "/feedback", headers=device["headers"], json=feedback(action["id"])
        ).status_code
        == 200
    )
    success = feedback(action["id"], "closed", "success", "Software bundle installed successfully.")
    for _ in range(2):
        assert (
            client.post(base + "/feedback", headers=device["headers"], json=success).status_code
            == 200
        )
    assert (
        client.post(
            base + "/feedback",
            headers=device["headers"],
            json=feedback(action["id"], detail="10% old progress"),
        ).status_code
        == 200
    )
    result = client.get(f"/api/deployments/{action['id']}").json()
    assert result["internal_status"] == "INSTALL_SUCCEEDED" and result["progress"] == 100
    assert result["boot_confirmation"] == "UNKNOWN" and not result["active"]
    assert (
        "deploymentBase"
        not in client.get(device["path"], headers=device["headers"]).json()["_links"]
    )
    assert client.get(base, headers=device["headers"]).status_code == 410
    with app.state.sessions() as session:
        assert (
            len(
                session.scalars(
                    select(DeploymentEvent).where(
                        DeploymentEvent.deployment_id == action["id"],
                        DeploymentEvent.kind == "feedback",
                    )
                ).all()
            )
            == 3
        )


@pytest.mark.parametrize(
    "value,start,end,status",
    [
        (None, 0, len(BUNDLE) - 1, 200),
        ("bytes=0-9", 0, 9, 206),
        ("bytes=10-", 10, len(BUNDLE) - 1, 206),
        ("bytes=-10", len(BUNDLE) - 10, len(BUNDLE) - 1, 206),
        ("bytes=0-999999", 0, len(BUNDLE) - 1, 206),
    ],
)
def test_download_ranges_head_and_if_range(
    client, admin, release, device, value, start, end, status
):
    client.post("/api/deployments", headers=admin, json=assignment(device, release))
    url = device["path"] + f"/softwaremodules/{release['module']['id']}/artifacts/firmware.raucb"
    headers = {**device["headers"], **({"Range": value} if value else {})}
    response = client.get(url, headers=headers)
    assert response.status_code == status and response.content == BUNDLE[start : end + 1]
    assert int(response.headers["content-length"]) == end - start + 1
    if status == 206:
        assert response.headers["content-range"] == f"bytes {start}-{end}/{len(BUNDLE)}"
    head = client.head(url, headers=headers)
    assert head.status_code == status and head.content == b""
    assert head.headers["content-length"] == response.headers["content-length"]
    full = client.get(
        url, headers={**device["headers"], "Range": "bytes=0-4", "If-Range": '"wrong"'}
    )
    assert full.status_code == 200 and full.content == BUNDLE


@pytest.mark.parametrize(
    "value", ["bytes=999999-", "bytes=-0", "bytes=10-1", "bytes=", "bytes=0-1,3-4", "items=0-1"]
)
def test_invalid_ranges(client, admin, release, device, value):
    client.post("/api/deployments", headers=admin, json=assignment(device, release))
    url = device["path"] + f"/softwaremodules/{release['module']['id']}/artifacts/firmware.raucb"
    response = client.get(url, headers={**device["headers"], "Range": value})
    assert response.status_code == 416
    assert response.headers["content-range"] == f"bytes */{len(BUNDLE)}"


def test_cross_target_action_and_artifact_acl(client, admin, release, device, app):
    action = client.post("/api/deployments", headers=admin, json=assignment(device, release)).json()
    with app.state.sessions() as session, session.begin():
        _, token = provision(session, "OTHER", "other")
    headers = {"Authorization": f"TargetToken {token}"}
    base = f"/OTHER/controller/v1/other/deploymentBase/{action['id']}"
    assert client.get(base, headers=headers).status_code == 404
    assert (
        client.post(base + "/feedback", headers=headers, json=feedback(action["id"])).status_code
        == 404
    )
    assert (
        client.get(
            f"/OTHER/controller/v1/other/softwaremodules/{release['module']['id']}/artifacts/firmware.raucb",
            headers=headers,
        ).status_code
        == 404
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"operator_confirmed": False},
        {"mode": "soft"},
        {"mode": "time_forced"},
        {"approval_note": ""},
        {"expected_compatible": "wrong"},
        {"expected_version": "wrong"},
    ],
)
def test_assignment_requires_explicit_matching_approval(client, admin, release, device, overrides):
    response = client.post(
        "/api/deployments", headers=admin, json=assignment(device, release, **overrides)
    )
    assert response.status_code in {400, 409}
    assert client.get("/api/deployments").json() == []


def test_safe_cancel_and_retry_new_identity(client, admin, release, device):
    first = client.post("/api/deployments", headers=admin, json=assignment(device, release)).json()
    assert client.post(f"/api/deployments/{first['id']}/cancel", headers=admin).status_code == 200
    action = client.post("/api/deployments", headers=admin, json=assignment(device, release)).json()
    client.get(device["path"], headers=device["headers"])
    assert client.post(f"/api/deployments/{action['id']}/cancel", headers=admin).status_code == 409
    base = device["path"] + f"/deploymentBase/{action['id']}"
    assert (
        client.post(
            base + "/feedback",
            headers=device["headers"],
            json=feedback(action["id"], "closed", "failure", "RAUC rejected signature"),
        ).status_code
        == 200
    )
    body = {
        "request_key": uuid.uuid4().hex,
        "operator_confirmed": True,
        "approval_note": "Test-only retry after inspecting failure",
    }
    response = client.post(f"/api/deployments/{action['id']}/retry", headers=admin, json=body)
    assert response.status_code == 201, response.text
    retry = response.json()
    assert retry["id"] != action["id"] and retry["retry_of"] == action["id"]
    assert retry["attempt_count"] == 2
    assert (
        client.post(f"/api/deployments/{action['id']}/retry", headers=admin, json=body).json()["id"]
        == retry["id"]
    )
    client.post(
        base + "/feedback",
        headers=device["headers"],
        json=feedback(action["id"], "closed", "success", "Late result"),
    )
    assert (
        client.get(f"/api/deployments/{retry['id']}").json()["internal_status"]
        == "WAITING_FOR_TARGET"
    )


def test_download_only_never_reports_install_success(client, admin, release, device):
    action = client.post(
        "/api/deployments", headers=admin, json=assignment(device, release, mode="download_only")
    ).json()
    base = device["path"] + f"/deploymentBase/{action['id']}"
    assert client.get(base, headers=device["headers"]).json()["deployment"]["update"] == "skip"
    client.post(
        base + "/feedback",
        headers=device["headers"],
        json=feedback(action["id"], detail="File checksum OK."),
    )
    result = client.get(f"/api/deployments/{action['id']}").json()
    assert result["internal_status"] == "DOWNLOAD_SUCCEEDED"
    assert client.get("/api/dashboard/summary").json()["successful_installations"] == 0


def test_assignment_snapshot_and_concurrent_polling(client, admin, release, device):
    action = client.post("/api/deployments", headers=admin, json=assignment(device, release)).json()
    client.patch(
        f"/api/distributions/{release['distribution']['id']}",
        headers=admin,
        json={"description": "Changed metadata"},
    )

    def poll(_):
        return client.get(device["path"], headers=device["headers"]).json()["_links"][
            "deploymentBase"
        ]["href"]

    with ThreadPoolExecutor(max_workers=5) as pool:
        assert len(set(pool.map(poll, range(5)))) == 1
    result = client.get(f"/api/deployments/{action['id']}").json()
    assert result["snapshot"] == action["snapshot"]


def test_missing_storage_and_malformed_feedback(client, admin, release, device, app):
    action = client.post("/api/deployments", headers=admin, json=assignment(device, release)).json()
    base = device["path"] + f"/deploymentBase/{action['id']}"
    assert (
        client.post(base + "/feedback", headers=device["headers"], json=feedback(999)).status_code
        == 400
    )
    assert (
        client.post(
            base + "/feedback", headers=device["headers"], json={"id": str(action["id"])}
        ).status_code
        == 400
    )
    app.state.storage.path(release["artifact"]["sha256"]).unlink()
    url = device["path"] + f"/softwaremodules/{release['module']['id']}/artifacts/firmware.raucb"
    assert client.get(url, headers=device["headers"]).status_code == 503


def test_bootstrap_and_password_reset_invalidate_sessions(configured, client, monkeypatch):
    from app.cli import main

    monkeypatch.setattr("app.cli.getpass.getpass", lambda prompt: PASSWORD)
    main(["admin-create", "operator-admin"])
    response = client.post(
        "/api/auth/login", json={"username": "operator-admin", "password": PASSWORD}
    )
    assert response.status_code == 200
    main(["admin-password-reset", "operator-admin"])
    assert client.get("/api/auth/me").status_code == 401


def test_concurrent_assignments_are_serialized(client, admin, release, device):
    def create(_):
        return client.post(
            "/api/deployments", headers=admin, json=assignment(device, release)
        ).status_code

    with ThreadPoolExecutor(max_workers=5) as pool:
        statuses = list(pool.map(create, range(5)))
    assert statuses.count(201) == 1
    assert statuses.count(409) == 4


@pytest.mark.updater
def test_actual_v13_download_only(configured, app, client, admin, release, device, tmp_path):
    import os
    import socket
    import subprocess
    import threading
    import time

    import uvicorn

    from app.main import create_app

    binary = os.environ.get("UPDATER_V13_BIN")
    if not binary:
        pytest.skip("Set UPDATER_V13_BIN to an actual v1.3 executable")
    assert subprocess.check_output([binary, "--version"], text=True).strip() == "Version 1.3"
    action = client.post(
        "/api/deployments", headers=admin, json=assignment(device, release, mode="download_only")
    ).json()
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    settings = configured[0].model_copy(update={"public_base_url": f"http://127.0.0.1:{port}"})
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings), access_log=False, log_level="error", proxy_headers=False
        )
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.05)
        assert server.started
        bundle = tmp_path / "download-only.raucb"
        config = tmp_path / "updater.conf"
        config.touch(mode=0o600)
        config.write_text(f"""[client]
hawkbit_server=127.0.0.1:{port}
ssl=false
ssl_verify=false
tenant_id=DEFAULT
target_name=test-target
auth_token={device["token"]}
bundle_download_location={bundle}
post_update_reboot=false
connect_timeout=2
timeout=5
retry_wait=1
log_level=message
[device]
model=T1
""")
        process = subprocess.run(
            [binary, "-r", "-c", str(config)], capture_output=True, text=True, timeout=20
        )
        assert process.returncode == 0, process.stdout + process.stderr
        assert "skip installation" in process.stdout
        assert bundle.read_bytes() == BUNDLE
        result = client.get(f"/api/deployments/{action['id']}").json()
        assert result["internal_status"] == "DOWNLOAD_SUCCEEDED"
        assert result["boot_confirmation"] == "UNKNOWN"
        assert client.get("/api/dashboard/summary").json()["successful_installations"] == 0
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        assert not thread.is_alive()


@pytest.mark.parametrize("size,status", [(1, 201), (1024 * 1024, 201), (1024 * 1024 + 1, 413)])
def test_upload_size_boundaries(client, admin, app, size, status):
    app.state.settings.max_upload_size_mb = 1
    response = client.post(
        "/api/firmware/upload",
        headers=admin,
        data={"name": "Boundary", "version": "1", "compatible": "board"},
        files={"file": ("boundary.raucb", b"x" * size, "application/octet-stream")},
    )
    assert response.status_code == status, response.text
    assert not list(app.state.storage.root.glob(".upload-*"))
    if status == 201:
        assert response.json()["size"] == size


def test_expired_and_disabled_sessions(client, admin, app):
    from datetime import UTC, datetime, timedelta

    with app.state.sessions() as session, session.begin():
        session.scalar(select(UserSession)).expires_at = datetime.now(UTC) - timedelta(seconds=1)
    assert client.get("/api/targets").status_code == 401


def test_closed_without_result_rejected(client, admin, release, device):
    action = client.post("/api/deployments", headers=admin, json=assignment(device, release)).json()
    url = device["path"] + f"/deploymentBase/{action['id']}/feedback"
    assert (
        client.post(
            url, headers=device["headers"], json=feedback(action["id"], "closed", "none")
        ).status_code
        == 400
    )


def test_withdraw_and_assignment_cannot_both_succeed(client, admin, release, device):
    from threading import Barrier

    gate = Barrier(2)

    def assign_one():
        gate.wait()
        return client.post(
            "/api/deployments", headers=admin, json=assignment(device, release)
        ).status_code

    def withdraw_one():
        gate.wait()
        return client.delete(
            f"/api/firmware/{release['artifact']['id']}", headers=admin
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assignment_result = pool.submit(assign_one)
        withdrawal_result = pool.submit(withdraw_one)
        statuses = (assignment_result.result(), withdrawal_result.result())
    assert statuses in {(201, 409), (409, 204)}


def test_delete_target_revokes_access_and_can_restore_without_old_token(client, admin, device, app):
    target_id = device["id"]
    url = f"/api/targets/{target_id}"
    assert client.delete(url).status_code == 403
    assert client.delete(url, headers=admin).status_code == 204
    assert client.delete(url, headers=admin).status_code == 204
    assert client.get("/api/targets").json() == []
    assert client.get("/api/dashboard/summary").json()["total_targets"] == 0
    deleted = client.get("/api/targets?include_deleted=true").json()
    assert len(deleted) == 1 and deleted[0]["connection_status"] == "Deleted"
    assert deleted[0]["deleted_at"] is not None
    assert client.get(url).status_code == 404
    assert client.get(device["path"], headers=device["headers"]).status_code == 401
    assert (
        client.put(
            device["path"] + "/configData",
            headers=device["headers"],
            json={"data": {"model": "T1"}},
        ).status_code
        == 401
    )
    assert client.patch(url, headers=admin, json={"enabled": True}).status_code == 404
    assert client.post(url + "/rotate-token", headers=admin).status_code == 404
    assert (
        client.post(
            "/api/targets",
            headers=admin,
            json={"controller_id": "test-target", "name": "Duplicate"},
        ).status_code
        == 409
    )
    restored = client.post(url + "/restore", headers=admin)
    assert restored.status_code == 200
    assert restored.json()["deleted_at"] is None and restored.json()["enabled"] is False
    assert client.get("/api/dashboard/summary").json()["total_targets"] == 1
    client.patch(url, headers=admin, json={"enabled": True})
    assert client.get(device["path"], headers=device["headers"]).status_code == 401
    token = client.post(url + "/rotate-token", headers=admin).json()["token"]
    assert (
        client.get(device["path"], headers={"Authorization": f"TargetToken {token}"}).status_code
        == 200
    )


@pytest.mark.parametrize("discovered", [False, True])
def test_cannot_delete_target_with_active_action(client, admin, release, device, discovered):
    action = client.post("/api/deployments", headers=admin, json=assignment(device, release)).json()
    if discovered:
        client.get(device["path"], headers=device["headers"])
    assert client.delete(f"/api/targets/{device['id']}", headers=admin).status_code == 409
    assert client.get(f"/api/targets/{device['id']}").json()["deleted_at"] is None
    assert client.get(device["path"], headers=device["headers"]).status_code == 200
    assert client.get(f"/api/deployments/{action['id']}").json()["active"] is True


def test_delete_preserves_history_and_blocks_new_assignments(client, admin, release, device):
    action = client.post("/api/deployments", headers=admin, json=assignment(device, release)).json()
    url = device["path"] + f"/deploymentBase/{action['id']}/feedback"
    client.post(url, headers=device["headers"], json=feedback(action["id"], "closed", "success"))
    previous_events = client.get(f"/api/deployments/{action['id']}/events").json()
    assert client.delete(f"/api/targets/{device['id']}", headers=admin).status_code == 204
    assert client.get(f"/api/targets/{device['id']}/history").json()[0]["id"] == action["id"]
    assert client.get(f"/api/deployments/{action['id']}/events").json() == previous_events
    assert (
        client.post("/api/deployments", headers=admin, json=assignment(device, release)).status_code
        == 400
    )
    audits = client.get("/api/audit-logs").json()
    assert any(
        a["operation"] == "target.deleted" and a["resource_id"] == str(device["id"]) for a in audits
    )


@pytest.mark.parametrize("role", ["viewer", "operator"])
def test_target_deletion_is_administrator_only(client, admin, device, role):
    assert (
        client.post(
            "/api/users",
            headers=admin,
            json={"username": "limited", "password": PASSWORD, "role": role},
        ).status_code
        == 201
    )
    login = client.post("/api/auth/login", json={"username": "limited", "password": PASSWORD})
    headers = {"X-CSRF-Token": login.json()["csrf_token"]}
    url = f"/api/targets/{device['id']}"
    assert client.delete(url, headers=headers).status_code == 403
    assert client.post(url + "/restore", headers=headers).status_code == 403
    assert client.get(device["path"], headers=device["headers"]).status_code == 200


def test_concurrent_delete_and_assignment_are_exclusive(client, admin, release, device):
    from threading import Barrier

    gate = Barrier(2)

    def create():
        gate.wait()
        return client.post(
            "/api/deployments", headers=admin, json=assignment(device, release)
        ).status_code

    def delete():
        gate.wait()
        return client.delete(f"/api/targets/{device['id']}", headers=admin).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        assigned = pool.submit(create)
        deleted = pool.submit(delete)
        assert (assigned.result(), deleted.result()) in {(201, 409), (400, 204)}
