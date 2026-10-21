from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker


def build_engine(url):
    kwargs = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
    engine = create_engine(url, **kwargs)
    if url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def configure_sqlite(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=30000")

    return engine


def session_factory(engine):
    return sessionmaker(engine, expire_on_commit=False)


def schema_head():
    from pathlib import Path

    config = Config()
    config.set_main_option("script_location", str(Path(__file__).parents[2] / "migrations"))
    return ScriptDirectory.from_config(config).get_current_head()
