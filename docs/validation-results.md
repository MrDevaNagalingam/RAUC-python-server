# Validation results — 2026-10-21 · v0.2

## Executed successfully

| Check | Result |
|---|---|
| SQLite complete suite | **92 passed**, including both actual v1.3 C-client tests |
| PostgreSQL 17 complete suite | **92 passed**, same API/migration/security/concurrency tests; disposable instance and isolated per-test schemas |
| TypeScript / frontend build | `npm run build` passed (TypeScript check and Vite production build) |
| Dependency installation | Locked Python requirements and frontend npm lock; npm audit during install reported zero vulnerabilities |
| Code quality | Ruff lint and formatting checks passed |
| Migrations | Upgrade/downgrade/upgrade and no model drift on both database engines |
| Actual unchanged C client | Pinned v1.3 source; polling/ConfigData and Download Only metadata/download/SHA-1 verification/feedback; no RAUC simulator |
| Docker | Multi-stage Node/Python image build succeeded; disposable non-root container served dashboard HTML, protected management reads, health/readiness and migration checks |
| Documentation | Local linked paths checked for existence |

The SQLite and PostgreSQL runs each emitted 49 warnings from Starlette's HTTPX
TestClient deprecation and AnyIO cancellation deprecations. No final test failure
remains. PostgreSQL used an explicitly disposable Docker instance; the test harness
created/dropped unique schemas per test. These checks did not modify the running
lab server's DB or create assignments for its real target.

## Coverage

The 0.1 foundation tests remain, updated for the new health stage and protected
management routes. New coverage includes:

- Administrator bootstrap/reset, Argon2 password storage, hashed sessions, CSRF,
  logout, origin rejection, login throttling, viewer permissions and account disable.
- Target enrollment, one-time credentials, metadata, revocation and no device-token
  management access.
- Multipart auth/metadata/name checks, empty/duplicate/oversized uploads, exact 1 MiB
  limit boundaries, hashes, private publication and temporary-file cleanup.
- Explicit confirmed assignments, exact version/compatibility checks, idempotency,
  active-action conflicts and concurrent assignment serialization.
- Verified DDI metadata fields/hashes/link relations, full/single-range/suffix/open
  downloads, HEAD, If-Range, invalid ranges and cross-target/cross-tenant ACLs.
- Feedback URL/body validation, immutable snapshots, monotonic progress, duplicate
  and late terminal protection, cancellation before discovery and linked explicit
  retries isolated from old feedback.
- Download Only remaining distinct from installation success; all boot fields unknown.
- Consistent private SQLite backup and retained data.

## Actual client evidence

Source: [v1.3 commit e19bc259](https://github.com/rauc/rauc-hawkbit-updater/tree/e19bc259a615ea31584c4056f365db46237d70f9).
It was compiled outside the repository with systemd/API docs disabled and no source
changes. The development host lacked some curl/json-glib development headers; the
previous build extracted matching package contents under /tmp without replacing
host runtime libraries. The executable reports `Version 1.3`.

The actual-client tests run against temporary Uvicorn loopback listeners. One
executes two one-shot polling/config cycles. The other creates a **Download Only**
action in a disposable DB, downloads a synthetic fixture, verifies exact contents,
receives checksum OK and confirms installation is skipped. The fixture is not a
signed RAUC bundle and is never passed to RAUC. These establish the real C parser,
link, SHA-1 and feedback behavior; forced RAUC installation is not represented as tested.

Host reproduction from backend/:

```bash
UPDATER_V13_BIN=/absolute/path/to/rauc-hawkbit-updater ../.venv/bin/pytest -q
```

For PostgreSQL, additionally set OTA_TEST_POSTGRES_URL to a disposable PostgreSQL
URL. Without the updater path, both C-client tests skip explicitly (90 passed,
2 skipped for the rest of the suite); a skip is not actual-client verification.

## Verification limits

- The user supplied real lab communication output (Online plus attributes). No
  additional direct gateway capture or periodic timing measurement was collected.
- No real signed bundle installation, RAUC D-Bus installation run, partition access,
  target slot inspection, reboot, mark-good or rollback verification was performed.
- No target-side TLS/certificate or live Nginx reverse-proxy validation was run.
- Browser QA could not run: no browsers were connected and the in-app browser provider
  returned `Browser is not available: iab`. The UI production build, served HTML and
  API behavior passed; rendered appearance and interactive browser behavior remain
  unverified by automation. No alternate browser-control tooling was substituted.
- Compose v2 is absent (`docker compose` unavailable). Docker image/container checks
  succeeded directly; Compose YAML parsing is not orchestration verification.
- No multi-gigabyte real bundle load, large fleet stress, forced socket-interruption
  recovery, production restoration, retention or long-duration reliability test ran.

The old host Uvicorn process and DB were left untouched for an explicit stop/backup/
migrate/admin-bootstrap/restart upgrade. No credentials were seeded into that DB.
Temporary test listeners/containers are stopped after checks. The local image is
`phytec-ota:management-dev`; frontend/dist contains the current production build.
Git has no commits; generated builds/DBs/venvs/secrets are ignored.

## Target deletion update

The complete suite passed again on SQLite (92 tests) and PostgreSQL 17 (92 tests).
New coverage verifies admin-only deletion/restoration, CSRF, immediate token
revocation, hidden fleet counts, idempotent deletion, retained events/history,
blocked deletion during active actions, and the deletion/assignment race. Restoring
never revives a previous credential. Migration 362b5f20d41c and model drift/roundtrip
checks passed on both engines. React TypeScript/Vite build and Ruff checks passed.
No existing lab target or live database was deleted or modified; apply the new
migration during the documented stop/backup/migrate/restart procedure. Browser
visual QA remains unavailable as documented above.
