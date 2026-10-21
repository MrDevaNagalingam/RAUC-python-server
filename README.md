# Python OTA Server · v0.2

FastAPI + React/TypeScript OTA management for the existing PHYTEC gateway,
rauc-hawkbit-updater v1.3, RAUC 1.11.3 and Barebox A/B layout. **Run this server
on the host PC. Keep the existing updater and RAUC on the target.**

Implemented: dashboard login and roles, target management, streaming multipart
firmware upload, hashes, OS modules, distributions, explicit assignments,
DDI metadata, authenticated range downloads, feedback/history, safe cancellation,
explicit retry, user administration, audit logs and effective configuration.
The dashboard is served at `/`; the API explorer remains at `/docs`.

No firmware is assigned on startup or upload. Forced assignments authorize the
target to install on its next poll: use the dashboard's review form only after
checking the intended target, bundle trust/compatibility/version and recovery path.
Download Only skips installation. Boot confirmation remains `UNKNOWN` without
separate evidence. No real installation or reboot has been performed by this work.

## Upgrade the existing polling-only instance

Stop its Uvicorn process with **Ctrl+C** before upgrading. Do not recreate the
existing target or rotate its working token merely to upgrade the server.

```bash
cd /media/phytec/data/work/python-server
.venv/bin/pip install -r backend/requirements.lock
.venv/bin/pip install --no-deps -e backend
cd backend
../.venv/bin/python ../scripts/backup-sqlite.py
../.venv/bin/alembic upgrade head
../.venv/bin/ota admin-create admin
```

Choose a private password at the prompt (minimum 12 characters). No default
administrator/password is seeded. The backup uses SQLite's online backup API and
writes a private file under the storage directory. For PostgreSQL, use your normal
`pg_dump`/backup procedure instead. Keep backups and the database private.

The dashboard production build is already present in this workspace. To reproduce
it after source changes, use either local Node.js 22+:

```bash
# From the repository root
cd frontend
npm ci
npm run build
```

Or build using Docker when Node.js is unavailable on the host:

```bash
# From the repository root; use your actual absolute checkout path
 docker run --rm --user "$(id -u):$(id -g)" \
   -v "$PWD/frontend:/app" -w /app node:22-alpine sh -c 'npm ci && npm run build'
```

From `backend/`, edit the private `.env` with the host's reachable origin and
matching `ALLOWED_HOSTS`. Keep the same public port already used by the gateway:

```dotenv
PUBLIC_BASE_URL=http://YOUR_HOST_IP:8081
ALLOWED_HOSTS=["localhost","127.0.0.1","YOUR_HOST_IP"]
```

Then start the host server:

```bash
../.venv/bin/uvicorn app.main:create_app --factory \
  --host 0.0.0.0 --port 8081 --no-proxy-headers --no-access-log
```

Open `http://YOUR_HOST_IP:8081/` and sign in with the administrator you created.
The existing target continues polling the same DDI address and credential.
`--host 127.0.0.1` permits access only from the host itself. Relative database,
storage and frontend paths resolve from `backend/`; consistently run server/CLI
commands there. If the root page says the build is missing, build `frontend/` and
restart Uvicorn so the assets mount is registered.

## Fresh development setup

Python **3.11+** is required; the host's default `python3` may be older.

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r backend/requirements.lock
.venv/bin/pip install --no-deps -e backend
cd backend
cp .env.example .env
../.venv/bin/alembic upgrade head
../.venv/bin/ota admin-create admin
```

Build the frontend and start Uvicorn as above. Enroll devices through the dashboard
or `ota target-create CONTROLLER_ID --token-file /PRIVATE/NEW_FILE.token`. Tokens
are shown only on creation/rotation, never in normal list responses. Preserve the
existing updater's configuration and signature trust. The formerly exposed test
token mentioned in the master prompt must not be reused.

## Release workflow

1. **Firmware:** upload the original `.raucb` with name, version, vendor and RAUC
   compatible string. The server records SHA-256, SHA-1, MD5 and size. Its signature
   status is explicitly **not verified**; target RAUC verification remains mandatory.
2. **Software modules:** associate one available bundle with an OS module.
3. **Distributions:** create a versioned release from that module.
4. **Deployments:** choose the target/release and Forced or Download Only. Re-enter
   the release version and compatible string, record approval/recovery evidence,
   and confirm. Soft and Time Forced are disabled.
5. Open the deployment to inspect raw feedback, progress and history. Installation
   success is separate from confirmed running firmware, boot and rollback evidence.

Metadata changes do not alter an existing action's immutable bundle references.
A cancel is permitted only before the deployment link is first exposed to the
updater. Explicit retries create a new linked action, protecting it from delayed
feedback for a failed action. Network retries keep the same action ID. No automatic
retry or device reboot is performed.

## Checks and operations

```bash
# From backend/
curl --fail http://127.0.0.1:8081/health
curl --fail http://127.0.0.1:8081/ready
../.venv/bin/ota target-show test-target
../.venv/bin/pytest -q
../.venv/bin/ruff check .
../.venv/bin/alembic check
```

For actual C-client tests, set `UPDATER_V13_BIN` to an unmodified v1.3 executable.
For the same suite on a **disposable** PostgreSQL instance, set
`OTA_TEST_POSTGRES_URL=postgresql+psycopg://...`; tests create/drop unique schemas.
Never point this test variable at production. See [validation results](docs/validation-results.md).

Dashboard data refreshes every five seconds; an open deployment timeline refreshes
every three seconds. Browser refreshes are independent of target DDI polling.
Roles: viewers inspect fleet/releases/history; operators upload and assign;
administrators also manage targets, credentials, users and audit history.
Recover administrator access locally with `ota admin-password-reset USERNAME`.

Administrators can **Delete** targets from the Targets table after typing the
controller ID in the confirmation dialog. Active deployments block deletion.
Deletion removes the target from the normal fleet list and counts, disables DDI
access and revokes its tokens while retaining deployment, attribute and audit
history. **Show deleted targets → Restore** brings back a disabled target; enable
it and rotate/provision a fresh token before reconnecting. The controller ID stays
reserved within its tenant so its history cannot be confused with a new device.
Apply migration `362b5f20d41c` with `alembic upgrade head` before restarting for
this feature. No existing targets are deleted by the migration.

## Documentation

- [Architecture](docs/architecture.md)
- [Database schema and migrations](docs/database-schema.md)
- [DDI compatibility and pinned protocol sources](docs/ddi-compatibility.md)
- [Implementation status and limits](docs/implementation-plan.md)
- [Management API](docs/api-reference.md)
- [Docker, HTTP and HTTPS deployment](docs/deployment-guide.md)
- [Hardware validation](docs/hardware-testing.md)
- [Security](docs/security.md)

Real signed-bundle installation, A/B slot validation, controlled reboot and
post-boot confirmation still require separate operator-approved hardware testing.
The local browser integration is unavailable, so visual browser QA is unverified.
