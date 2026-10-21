import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from app.database.models import AuditLog, Target, TargetCredential
from app.main import create_app
from app.services.targets import describe, provision


def config_payload():
    return json.loads((Path(__file__).parent / "fixtures/config_data.json").read_text())


def test_initial_poll_exact_response(client, device, app):
    response = client.get(device["path"], headers=device["headers"])
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {
        "config": {"polling": {"sleep": "00:01:00"}},
        "_links": {"configData": {"href": "http://testserver" + device["path"] + "/configData"}},
    }
    with app.state.sessions() as session:
        target = session.get(Target, device["id"])
        assert target.last_seen_at == target.last_poll_at == target.last_request_at
        assert describe(session, target, 180)["connection_status"] == "Online"


def test_config_capture_and_no_deployment(client, device, app):
    response = client.put(
        device["path"] + "/configData", headers=device["headers"], json=config_payload()
    )
    assert response.status_code == 200 and response.content == b""
    assert client.get(device["path"], headers=device["headers"]).json() == {
        "config": {"polling": {"sleep": "00:01:00"}},
        "_links": {},
    }
    with app.state.sessions() as session:
        result = describe(session, session.get(Target, device["id"]), 180)
        assert result["attributes"] == config_payload()["data"]
        assert result["boot_confirmation"] == "UNKNOWN"
        assert result["running_firmware"] is None


@pytest.mark.parametrize(
    "header", [None, "", "Bearer wrong", "TargetToken wrong", "TargetToken", "TargetToken x y"]
)
def test_bad_auth(client, device, header, app):
    response = client.get(device["path"], headers={"Authorization": header} if header else {})
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "TargetToken"
    with app.state.sessions() as session:
        assert session.get(Target, device["id"]).last_seen_at is None
        assert (
            session.scalar(
                select(AuditLog).where(AuditLog.operation == "device.authentication_failed")
            )
            is not None
        )


@pytest.mark.parametrize(
    "path", ["/OTHER/controller/v1/test-target", "/DEFAULT/controller/v1/other-target"]
)
def test_unknown_identity(client, device, path):
    assert client.get(path, headers=device["headers"]).status_code == 401


def test_cross_target_cross_tenant_and_disabled(client, device, app):
    with app.state.sessions() as session, session.begin():
        provision(session, "DEFAULT", "second")
        provision(session, "OTHER", "test-target")
    for path in ("/DEFAULT/controller/v1/second", "/OTHER/controller/v1/test-target"):
        assert client.get(path, headers=device["headers"]).status_code == 401
        assert (
            client.put(
                path + "/configData", headers=device["headers"], json=config_payload()
            ).status_code
            == 401
        )
    with app.state.sessions() as session, session.begin():
        session.get(Target, device["id"]).enabled = False
    assert client.get(device["path"], headers=device["headers"]).status_code == 401


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"data": {}},
        {"data": {"model": 2}},
        {"data": {"": "value"}},
        {"data": {"x": "v" * 2049}},
        {"mode": "invalid", "data": {"x": "v"}},
        {"data": {str(i): "v" for i in range(101)}},
    ],
)
def test_malformed_config(client, device, payload):
    response = client.put(device["path"] + "/configData", headers=device["headers"], json=payload)
    assert response.status_code == 400
    assert (
        "deploymentBase"
        not in client.get(device["path"], headers=device["headers"]).json()["_links"]
    )


def test_invalid_json_media_and_chunked_limits(client, device):
    path = device["path"] + "/configData"
    headers = {**device["headers"], "Content-Type": "application/json;charset=UTF-8"}
    assert client.put(path, headers=headers, content=b"{").status_code == 400
    assert client.put(path, headers=device["headers"], content=b"{}").status_code == 415
    assert client.put(path, headers=headers, content=iter([b"x" * 1000] * 70)).status_code == 413


def test_merge_replace_remove_idempotent(client, device, app):
    path, headers = device["path"] + "/configData", device["headers"]
    for _ in range(2):
        assert client.put(path, headers=headers, json=config_payload()).status_code == 200
    assert (
        client.put(path, headers=headers, json={"data": {"custom_key": "custom"}}).status_code
        == 200
    )
    with app.state.sessions() as session:
        target = session.get(Target, device["id"])
        assert len(describe(session, target, 180)["attributes"]) == 4
    for payload in (
        {"mode": "replace", "data": {"new": "value", "remove": "this"}},
        {"mode": "remove", "data": {"remove": "ignored"}},
    ):
        assert client.put(path, headers=headers, json=payload).status_code == 200
    with app.state.sessions() as session:
        assert describe(session, session.get(Target, device["id"]), 180)["attributes"] == {
            "new": "value"
        }


def test_concurrent_config_data(client, device, app):
    def send(i):
        return client.put(
            device["path"] + "/configData",
            headers=device["headers"],
            json={"data": {"same": str(i), f"key{i}": "value"}},
        ).status_code

    with ThreadPoolExecutor(max_workers=8) as pool:
        assert list(pool.map(send, range(8))) == [200] * 8
    with app.state.sessions() as session:
        assert len(describe(session, session.get(Target, device["id"]), 180)["attributes"]) == 9


def test_settings_and_state_survive_restart(client, device, app, configured):
    client.put(device["path"] + "/configData", headers=device["headers"], json=config_payload())
    with app.state.sessions() as session, session.begin():
        session.get(Target, device["id"]).polling_interval_seconds = 3661
    with TestClient(create_app(configured[0])) as restarted:
        response = restarted.get(device["path"], headers=device["headers"])
        assert response.json() == {"config": {"polling": {"sleep": "01:01:01"}}, "_links": {}}


def test_connectivity_and_never_connected(app, device):
    with app.state.sessions() as session:
        target = session.get(Target, device["id"])
        assert describe(session, target, 180)["connection_status"] == "Never Connected"
        target.last_seen_at = datetime.now(UTC) - timedelta(seconds=181)
        assert describe(session, target, 180)["connection_status"] == "Offline"
        target.enabled = False
        assert describe(session, target, 180)["connection_status"] == "Disabled"


def test_secrets_hashed_and_not_in_audit(app, device):
    with app.state.sessions() as session:
        credential = session.scalar(select(TargetCredential))
        assert credential.token_hash != device["token"]
        assert len(credential.token_hash) == 64
        assert device["token"] not in str(session.execute(text("SELECT * FROM audit_logs")).all())


def test_unique_identity_within_tenant(app, device):
    with pytest.raises(IntegrityError), app.state.sessions() as session, session.begin():
        provision(session, "DEFAULT", "test-target")


def test_device_token_cannot_assign_and_unassigned_artifacts_are_denied(client, device):
    assert client.post("/api/deployments", headers=device["headers"]).status_code == 401
    for method, path in (
        ("GET", device["path"] + "/deploymentBase/7"),
        ("GET", device["path"] + "/softwaremodules/1/artifacts/bundle.raucb"),
    ):
        assert client.request(method, path, headers=device["headers"]).status_code == 404
