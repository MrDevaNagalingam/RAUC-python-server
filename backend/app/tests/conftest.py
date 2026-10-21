import os
import uuid
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema

from app.core.config import Settings
from app.database.session import build_engine
from app.main import create_app
from app.services.targets import provision


@pytest.fixture
def configured(tmp_path, monkeypatch):
    postgres_url = os.environ.get("OTA_TEST_POSTGRES_URL")
    postgres_engine = None
    schema = None
    if postgres_url:
        # Explicitly supplied disposable test instance, unique schema for every test.
        postgres_engine = build_engine(postgres_url)
        schema = "ota_test_" + uuid.uuid4().hex
        with postgres_engine.begin() as connection:
            connection.execute(CreateSchema(schema))
        scoped_url = make_url(postgres_url).update_query_dict(
            {"options": f"-csearch_path={schema}"}
        )
        monkeypatch.setenv("DATABASE_URL", scoped_url.render_as_string(hide_password=False))
    else:
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'ota.db'}")
    monkeypatch.setenv("ARTIFACT_STORAGE_PATH", str(tmp_path / "artifacts"))
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://testserver")
    monkeypatch.setenv("ALLOWED_HOSTS", '["testserver","127.0.0.1"]')
    settings = Settings(_env_file=None)
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    command.upgrade(config, "head")
    try:
        yield settings, config
    finally:
        if postgres_engine is not None:
            with postgres_engine.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
            postgres_engine.dispose()


@pytest.fixture
def app(configured):
    return create_app(configured[0])


@pytest.fixture
def client(app):
    with TestClient(app) as client:
        yield client


@pytest.fixture
def device(app):
    with app.state.sessions() as session, session.begin():
        target, token = provision(session, "DEFAULT", "test-target", "Lab gateway")
        target_id = target.id
    return {
        "id": target_id,
        "token": token,
        "headers": {
            "Authorization": f"TargetToken {token}",
            "Accept": "application/json;charset=UTF-8",
        },
        "path": "/DEFAULT/controller/v1/test-target",
    }
