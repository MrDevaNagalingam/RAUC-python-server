import json

import pytest
from alembic import command
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import inspect, text

from app.cli import main
from app.core.config import Settings
from app.database.session import build_engine
from app.main import create_app


def test_health_ready_and_request_ids(client):
    health = client.get("/health")
    ready = client.get("/ready")
    assert health.json() == {"status": "ok", "stage": "management"}
    assert ready.status_code == 200
    assert health.headers["x-request-id"] != ready.headers["x-request-id"]
    assert health.headers["cache-control"] == "no-store"


def test_migration_roundtrip_and_drift(configured):
    settings, config = configured
    command.check(config)
    command.downgrade(config, "base")
    engine = build_engine(settings.database_url)
    assert "targets" not in inspect(engine).get_table_names()
    engine.dispose()
    command.upgrade(config, "head")
    command.check(config)


def test_unmigrated_startup_fails(configured):
    settings, config = configured
    command.downgrade(config, "base")
    with (
        pytest.raises(RuntimeError, match="alembic upgrade head"),
        TestClient(create_app(settings)),
    ):
        pass


def test_ready_detects_schema_change(client, app):
    with app.state.engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num='old'"))
    assert client.get("/ready").status_code == 503
    assert client.get("/health").status_code == 200


@pytest.mark.parametrize(
    "overrides",
    [
        {"polling_interval_seconds": 0},
        {"polling_interval_seconds": 86400},
        {"offline_threshold_seconds": 60},
        {"public_base_url": "http://evil.example"},
        {"public_base_url": "http://testserver/path"},
        {"allowed_hosts": ["*"]},
        {"app_env": "production"},
        {
            "app_env": "production",
            "public_base_url": "https://testserver",
            "database_url": "sqlite:///test.db",
        },
    ],
)
def test_invalid_settings(configured, overrides):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **overrides)


def test_host_and_forwarded_headers(client, device):
    assert client.get("/health", headers={"Host": "evil.example"}).status_code == 400
    response = client.get(
        device["path"],
        headers={
            **device["headers"],
            "X-Forwarded-Host": "evil.example",
            "X-Forwarded-Proto": "https",
        },
    )
    assert response.json()["_links"]["configData"]["href"].startswith("http://testserver/")


def test_cli_provision_rotate_revoke(configured, tmp_path, capsys):
    token_file = tmp_path / "target.token"
    main(["target-create", "cli-target", "--token-file", str(token_file)])
    output = capsys.readouterr().out
    token = token_file.read_text().strip()
    assert token not in output
    assert token_file.stat().st_mode & 0o777 == 0o600
    assert json.loads(output)["connection_status"] == "Never Connected"
    app = create_app(configured[0])
    path = "/DEFAULT/controller/v1/cli-target"
    with TestClient(app) as client:
        assert (
            client.get(path, headers={"Authorization": f"TargetToken {token}"}).status_code == 200
        )
        second = tmp_path / "second.token"
        main(["token-rotate", "cli-target", "--token-file", str(second)])
        assert (
            client.get(path, headers={"Authorization": f"TargetToken {token}"}).status_code == 401
        )
        headers = {"Authorization": f"TargetToken {second.read_text().strip()}"}
        assert client.get(path, headers=headers).status_code == 200
        main(["token-revoke", "cli-target"])
        assert client.get(path, headers=headers).status_code == 401


def test_cli_refuses_existing_secret_and_rolls_back(configured, tmp_path):
    path = tmp_path / "existing.token"
    path.write_text("keep")
    with pytest.raises(SystemExit):
        main(["target-create", "new-target", "--token-file", str(path)])
    assert path.read_text() == "keep"
    app = create_app(configured[0])
    with app.state.sessions() as session:
        assert session.execute(text("SELECT count(*) FROM targets")).scalar() == 0


def test_production_settings_require_https_postgres(configured):
    settings = Settings(
        _env_file=None,
        app_env="production",
        public_base_url="https://ota.example",
        allowed_hosts=["ota.example"],
        database_url="postgresql+psycopg://operator@db/ota",
    )
    assert settings.public_base_url == "https://ota.example"


def test_cli_write_failure_removes_partial_secret(configured, tmp_path, monkeypatch):
    def storage_failure(fd):
        raise OSError("simulated storage failure")

    monkeypatch.setattr("app.cli.os.fsync", storage_failure)
    path = tmp_path / "partial.token"
    with pytest.raises(SystemExit):
        main(["target-create", "new-target", "--token-file", str(path)])
    assert not path.exists()
    with build_engine(configured[0].database_url).connect() as connection:
        assert connection.execute(text("SELECT count(*) FROM targets")).scalar() == 0


def test_sqlite_backup_is_private_and_consistent(configured, tmp_path, monkeypatch):
    import sqlite3
    import subprocess
    import sys
    from contextlib import closing
    from pathlib import Path

    database = tmp_path / "backup-source.db"
    with closing(sqlite3.connect(database)) as source:
        source.execute("CREATE TABLE marker (value TEXT)")
        source.execute("INSERT INTO marker VALUES ('preserved')")
        source.commit()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database}")
    monkeypatch.setenv("ARTIFACT_STORAGE_PATH", str(tmp_path / "artifacts"))
    script = Path(__file__).resolve().parents[3] / "scripts/backup-sqlite.py"
    subprocess.run([sys.executable, str(script)], cwd=tmp_path, check=True, capture_output=True)
    backups = list((tmp_path / "backups").glob("*.sqlite3"))
    assert len(backups) == 1
    assert backups[0].stat().st_mode & 0o777 == 0o600
    with closing(sqlite3.connect(backups[0])) as backup:
        assert backup.execute("SELECT value FROM marker").fetchone()[0] == "preserved"
