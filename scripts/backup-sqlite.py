"""Create a consistent, private backup before a schema upgrade. Run from backend/."""

import os
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import Settings
from sqlalchemy.engine import make_url

settings = Settings()
url = make_url(settings.database_url)
if url.get_backend_name() != "sqlite":
    raise SystemExit(
        "Use your PostgreSQL backup procedure before migration (for example pg_dump)."
    )
source_path = Path(url.database).resolve()
if not source_path.is_file():
    raise SystemExit("No existing SQLite database to back up.")
directory = Path(settings.artifact_storage_path).parent / "backups"
directory.mkdir(parents=True, exist_ok=True, mode=0o700)
destination = directory / (
    "ota-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f") + ".sqlite3"
)
fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
os.close(fd)
try:
    with (
        closing(sqlite3.connect(source_path.as_uri() + "?mode=ro", uri=True)) as source,
        closing(sqlite3.connect(destination)) as backup,
    ):
        source.backup(backup)
except Exception:
    destination.unlink(missing_ok=True)
    raise
print(f"Private SQLite backup created: {destination}")
