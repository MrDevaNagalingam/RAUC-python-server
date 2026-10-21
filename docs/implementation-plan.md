# Implementation status · v0.2

The first polling gate was satisfied by the user's supplied lab output: test-target
Online, authenticated activity timestamps and model/hw_revision/mac_address stored.
This turn implements the previously selected management, firmware and dashboard work.
No physical installation or reboot is authorized by simply requesting implementation.

| Phase | Current state | Remaining gate |
|---|---|---|
| 1 Foundation | FastAPI/settings/logging/health, SQLAlchemy and explicit migrations tested | Complete for local foundation |
| 2 DDI communication | Poll/config/token tests plus actual v1.3 C-client tests; user supplied lab communication evidence | Periodic timing/TLS/capture details remain outside directly collected evidence |
| 3 Firmware and deployment | Real upload/storage/module/distribution/assignment/DDI/download/feedback APIs; actual C Download Only test | Forced signed-bundle RAUC installation on hardware, with explicit operator approval |
| 4 Dashboard | React/TypeScript login, overview, targets, firmware upload, modules, distributions, deployments/details, history, settings, users and audit | Visual browser QA unavailable in this session |
| 5 Hardening | Roles, Argon2id, server sessions, CSRF/origin checking, login throttling, DB constraints/locks, Docker/TLS templates and PostgreSQL test support | TLS, restore, long-duration/capacity/retention tests and Compose orchestration |
| 6 Hardware validation | Prior user-reported polling/config evidence retained | Real signed bundle, RAUC progress/install, slot inspection, approved reboot and boot confirmation |

## Changes

Backend: new management authentication/schemas/resources modules; deployment,
download and feedback DDI handlers; storage and deployment-engine services;
expanded models and revision `b61672b156bf`; administrator bootstrap/reset CLI;
updated application factory/middleware/configuration and security/state tests.
Existing target identities/tokens are retained across migration.

Frontend: React/TypeScript/Vite project with typed API client, credential/CSRF
handling, reusable dialog/field/badge/progress components and responsive fleet UI.
Authentication gates all data; available actions follow roles. Firmware transfer
progress uses XMLHttpRequest; device progress uses original feedback/events.
The server serves the build at `/`, resolving the previous expected root 404.

Operations: locked dependency additions, multi-stage Docker build, bounded Nginx
upload route, updated Compose paths, SQLite online backup helper and current docs.
Run available tests per validation-results.md; no deferred acceptance criterion is
represented as passed solely because the UI exists.

## Deliberate limits

- One OS module with one bundle per release/action, matching the verified v1.3 parser.
- Forced and Download Only only. Soft/Time Forced/maintenance windows disabled.
- Cancellation only before link discovery; no simulated in-progress cancellation.
- Network retries keep action identity. Explicit failed reattempts create a new
  linked action to isolate stale feedback; automatic retries/reinstallation absent.
- Server checks supplied confirmation against metadata, not the actual signature or
  hardware. RAUC remains mandatory; uploaded signature status is NOT_VERIFIED.
- Firmware withdrawal retains objects/history, with active-action guards. No physical
  deletion/retention job or S3 adapter exists yet.
- No inferred boot success, running firmware or rollback from installation feedback.
- Management roles are server-wide. Per-tenant user permissions, external identity,
  automatic timeout actions and very large catalog pagination are future work.
- Configuration is inspected in the dashboard and changed through host environment
  plus restart, rather than unaudited runtime configuration mutation.

## Manual verification

Upgrade using README (stop, backup, dependencies, migration, admin creation, restart).
Open `/`, sign in and confirm the existing target/attributes remain present. Inspect
API auth separation and ordinary no-action polling. For firmware exercises prepare
a trusted compatible bundle and recovery path. Upload, create an OS module and a
release; verify upload/catalog creation alone advertises no action. Review Download
Only first if appropriate. Any Forced assignment requires explicit operator review.
Installation does not authorize reboot: obtain separate approval and inspect slots
and mark-good independently. Follow hardware-testing.md.
