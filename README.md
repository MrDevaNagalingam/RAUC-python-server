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

## New PC: clone, configure and run

These commands are for **Linux or WSL2 with Bash**. You need Git, Python **3.11**
with venv/pip support, and Node.js **22+** with npm. Check prerequisites first:

```bash
git --version
python3.11 --version
python3.11 -m venv --help
node --version
npm --version
```

If a prerequisite is missing, install it before continuing. Docker Engine can
replace the local Node.js build step below; the Docker Compose alternative is in
[the deployment guide](docs/deployment-guide.md).

### 1. Clone the repository

```bash
git clone https://github.com/MrDevaNagalingam/RAUC-python-server.git
cd RAUC-python-server
```

The clone directory is `RAUC-python-server`; it does not have to match the original
PC's `python-server` directory. All following paths are relative to this checkout.

### 2. Create the Python environment

Run from the repository root:

```bash
python3.11 -m venv .venv
.venv/bin/pip install -r backend/requirements.lock
.venv/bin/pip install --no-deps -e backend
```

### 3. Create the local configuration

Still from the repository root:

```bash
cp backend/.env.example backend/.env
nano backend/.env
```

Use any text editor if `nano` is not installed.

For access only from this new PC, the example defaults work:

```dotenv
PUBLIC_BASE_URL=http://127.0.0.1:8081
ALLOWED_HOSTS=["localhost","127.0.0.1","testserver"]
```

For access from the PHYTEC gateway or another PC, replace `YOUR_HOST_IP` below
with this **new PC's actual reachable IP address** (use `hostname -I` on Linux to
inspect addresses). Save real values in `.env`, not the literal placeholder:

```dotenv
PUBLIC_BASE_URL=http://YOUR_HOST_IP:8081
ALLOWED_HOSTS=["localhost","127.0.0.1","YOUR_HOST_IP"]
```

Do not copy the old PC's address unless the new PC actually uses it. Ensure the
chosen port is free and reachable through the host/network firewall. Settings
persist in `.env`; you do not need to prefix every launch command with them.
These HTTP instructions are for controlled development/lab use. Production needs
PostgreSQL and trusted HTTPS; see [deployment](docs/deployment-guide.md).

### 4. Build the dashboard

`frontend/dist` and `frontend/node_modules` are deliberately excluded from Git.
A fresh clone must build them. From the repository root:

```bash
cd frontend
npm ci
npm run build
cd ..
```

**Alternative when Node.js is absent:** replace the preceding block with this
Docker command, also run from the repository root:

```bash
docker run --rm --user "$(id -u):$(id -g)" \
  -v "$PWD/frontend:/app" -w /app node:22-alpine \
  sh -c 'npm ci && npm run build'
```

### 5. Initialize the database and administrator

From the repository root, enter `backend/`:

```bash
cd backend
../.venv/bin/alembic upgrade head
../.venv/bin/ota admin-create admin
```

Choose a private password at the prompt (minimum 12 characters). There is no
default administrator or password. On a fresh installation the database starts
empty: users, targets, firmware and history from the old PC are **not** in Git.
Do not run the backup helper on a fresh installation with no existing database.

### 6. Start the server

**Stay in `backend/`** and run:

```bash
../.venv/bin/uvicorn app.main:create_app --factory \
  --host 0.0.0.0 --port 8081 --no-proxy-headers --no-access-log
```

Keep the terminal running. Open `http://127.0.0.1:8081/` on this PC, or
`http://YOUR_HOST_IP:8081/` from the lab network after configuring its origin/hosts.
Sign in with the administrator just created. `/docs` is the API explorer.
The dashboard initially has no targets or firmware; that is expected.

From another terminal, check:

```bash
curl --fail http://127.0.0.1:8081/health
curl --fail http://127.0.0.1:8081/ready
```

Expected responses: `{"status":"ok","stage":"management"}` and
`{"status":"ready"}`. On later launches, run only the server command from
`backend/`; repeat migrations after schema upgrades, and rebuild the dashboard
when frontend source changes. Do not recreate the administrator each time.

### 7. Enroll a target

Use **Targets → Add target** in the dashboard and save the one-time credential
privately. Configure the existing target updater with this server's reachable
`HOST_IP:8081`, the same tenant/controller ID, and that credential. Keep the target's
RAUC service, trust/keyring, Barebox, partitions and updater executable unchanged.
For the controlled HTTP lab set `ssl=false`, `ssl_verify=false` and keep
`post_update_reboot=false`. Full hardware procedures are in
[hardware testing](docs/hardware-testing.md).

Enroll manually instead if desired (from `backend/`):

```bash
../.venv/bin/ota target-create gateway-001 --token-file /tmp/gateway-001.token
```

The token file must not already exist. A new target starts as `Never Connected`;
it becomes `Online` after authenticated updater activity. Creating a target or
uploading firmware never assigns a deployment.

## Move existing server data to another PC

Choose this path when you want the old users, target credentials, firmware and
history, rather than a new empty installation. Git contains application code only.
Privately back up/transfer the database and artifact storage together, and configure
the new PC's `.env` for the restored paths and new public address. Do not commit
these files. Use [the backup and deployment instructions](docs/deployment-guide.md)
and keep the source server stopped while taking a consistent migration copy.

For the default SQLite layout, restore the DB as `backend/ota.db` and retain the
content-addressed artifact files under `backend/storage/artifacts/`. If you used
custom paths, configure those restored paths instead. Use a proper SQLite backup,
not an arbitrary copy of a live `ota.db` that may depend on WAL files. Apply
`alembic upgrade head` to the restored DB, then sign in with an existing account;
**skip `admin-create admin` when that account already exists**. Existing device
credentials remain valid when the full DB is preserved, but the updater must reach
the new server address. For PostgreSQL use your normal dump/restore procedure.

## Upgrade an existing installation

Stop its Uvicorn process with **Ctrl+C**. From your actual checkout root:

```bash
.venv/bin/pip install -r backend/requirements.lock
.venv/bin/pip install --no-deps -e backend
cd backend
../.venv/bin/python ../scripts/backup-sqlite.py
../.venv/bin/alembic upgrade head
```

The backup helper writes a private SQLite backup including WAL contents. For
PostgreSQL, use your normal backup procedure instead. Create an administrator only
if upgrading an old polling-only installation that has none. Preserve the private
`.env`, existing database and target credentials; do not recopy `.env.example`
over your configured file or recreate working targets. Build the frontend as in
step 4, return to `backend/`, and restart with the command in step 6.

## Files intentionally excluded from Git

| Local item | New PC action |
|---|---|
| `.venv/` | Recreate and install the locked Python dependencies |
| `frontend/node_modules/` | Run `npm ci` |
| `frontend/dist/` | Run `npm run build` |
| `backend/.env` | Copy `.env.example` and configure the new host |
| Database, WAL and backups | Initialize a fresh DB or privately restore existing data |
| `storage/` | Upload firmware again or privately restore its artifact files |
| `*.token` | Provision securely; never commit device tokens |

All source, migrations, `.env.example` and dependency lock files are tracked.
Ignoring local files does not delete them from the original PC. Native Windows
commands use different paths; use WSL2 for the Bash procedure above.

## Common startup problems

| Symptom | Check/fix |
|---|---|
| Database schema is not current | Run `alembic upgrade head` from **backend/** against the intended DB |
| It fails after launching from frontend/ | Stop it; `cd` to backend/ before migrations, CLI or Uvicorn |
| Dashboard build missing | Build frontend/, then restart Uvicorn so assets mount correctly |
| Port already in use | Stop the intended old instance or choose a free port; update public URL and target configuration consistently |
| Localhost works, LAN IP is refused | Bind with `--host 0.0.0.0`; check interface address, routing and firewall |
| Invalid host header | Add the actual hostname/IP (without port) to ALLOWED_HOSTS and restart |
| Fresh dashboard has no old targets/users | Expected: Git does not include server data; enroll new devices or restore a private backup |

## Setup verification

Fresh-setup verification: the procedure was checked on Linux using an isolated
checkout containing only Git-tracked files, a new Python 3.11 environment and the
Node.js 22 Docker build alternative. Migrations, administrator bootstrap/login,
HTTP health/readiness, dashboard HTML/assets and an empty fresh database passed.
No existing `.env`, database, firmware storage or compiled build was reused.

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
../.venv/bin/ota target-list
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
