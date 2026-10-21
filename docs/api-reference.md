# API reference · v0.2

The running application exposes `/docs` and `/openapi.json`. Device and management
credentials are distinct. JSON errors omit submitted credentials and bound database
parameters. Invalid input returns 400, authorization 401/403, missing resources 404,
state/uniqueness conflicts 409 and database availability errors 503.

## Authentication

`POST /api/auth/login` accepts JSON `{ "username": "...", "password": "..." }`.
Success returns `{ "user": {id, username, role, is_active, created_at}, "csrf_token": "..." }`
and an HttpOnly, SameSite=Strict session cookie. The cookie is Secure in production.
`GET /api/auth/me` restores the user and CSRF token for the signed-in browser.
All authenticated mutations require `X-CSRF-Token`; the React client supplies it.
`POST /api/auth/logout` invalidates the current session and clears its cookie.
Browser origins are checked, including during login; arbitrary CORS is not enabled.
Throttling persists in the database: eight failed attempts per username and fifty
per direct client IP in a five-minute window. Proxy forwarding headers are not used.

Create the initial administrator using `ota admin-create USERNAME`. Passwords are
prompted privately; reset with `ota admin-password-reset USERNAME`, which invalidates
that administrator's sessions. There is no seeded or default account.

## Resource endpoints

GETs require any authenticated user, except users/audit logs (administrator only).
Operators and administrators can mutate firmware/modules/distributions/deployments.
Target, credential and user mutations require administrator permission. These are
server-wide management roles; device credentials remain scoped to one tenant/target.

| Method | Path | Behavior |
|---|---|---|
| GET, POST | `/api/targets` | List; enroll and return the new token once |
| GET, PATCH | `/api/targets/{id}` | Inspect; update name/description/enabled/poll override |
| DELETE | `/api/targets/{id}` | Admin only; archive and revoke tokens; 409 for active deployment |
| POST | `/api/targets/{id}/restore` | Admin only; restore disabled, previous tokens remain revoked |
| POST | `/api/targets/{id}/rotate-token` | Revoke prior credential and return replacement once |
| POST | `/api/targets/{id}/revoke-token` | Revoke active credential |
| GET | `/api/targets/{id}/history` | Action history for a target |
| GET | `/api/firmware` | List metadata and checksums, no storage paths |
| GET | `/api/firmware/{id}` | Inspect firmware metadata |
| POST | `/api/firmware/upload` | Multipart file plus metadata; authenticate before parsing |
| DELETE | `/api/firmware/{id}` | Withdraw from future assignments; active references block it |
| GET, POST | `/api/software-modules` | List/create a single-bundle OS module |
| GET, POST | `/api/distributions` | List/create a single-module release |
| PATCH | `/api/distributions/{id}` | Edit description; contents/version remain stable |
| GET, POST | `/api/deployments` | List/create explicitly approved assignments |
| GET | `/api/deployments/{id}` | Immutable snapshot and current installation evidence |
| GET | `/api/deployments/{id}/events` | Ordered raw feedback and server events |
| POST | `/api/deployments/{id}/cancel` | Only before the first deployment link discovery |
| POST | `/api/deployments/{id}/retry` | New linked action for a failed/rejected attempt |
| GET | `/api/dashboard/summary` | Fleet and action counts |
| GET | `/api/settings` | Effective non-secret configuration (read-only) |
| GET, POST | `/api/users` | List/create accounts with admin/operator/viewer roles |
| PATCH | `/api/users/{id}` | Enable/disable account; self-disable is blocked |
| GET | `/api/audit-logs?limit=100&before=ID` | Recent audit rows; max 500, cursor pagination |

Upload form fields: `file`, `name`, `version`, `compatible`, `vendor`, `description`.
The first four are required. File size is configurable; metadata is bounded.
Filenames must use letters/numbers/dots/underscores/hyphens and end in `.raucb`.
Empty files and unsafe filenames return 400; oversized payloads return 413;
identical contents return 409 with the existing firmware ID. Disk errors return
507. The browser reports transfer progress and then checksum/publication processing.
Signature status remains `NOT_VERIFIED`. Withdrawal is a tombstone: content is not
physically deleted, so historic references and already-open streams stay valid.

## Assignment contract

```json
{
  "request_key": "UNIQUE_REQUEST_KEY_AT_LEAST_16_CHARS",
  "target_id": 1,
  "distribution_id": 1,
  "mode": "download_only",
  "expected_compatible": "phyboard-segin-imx6ul-7",
  "expected_version": "1.1",
  "operator_confirmed": true,
  "approval_note": "Record target, signature/compatibility checks and available recovery path."
}
```

This is an example, not permission to assign the existing lab target. Forced and
Download Only are supported. A request key makes repeated submissions return the
same action; do not generate a new key merely because a response was lost. Conflicting
concurrent assignments are blocked by target locking and an active-action unique index.
The version confirmation refers to the **distribution version**. Bundle compatibility
is matched to the artifact metadata; the operator must verify actual hardware and
signature trust. No server-side `.raucb` signature or manifest verification is claimed.

Explicit retry requires a fresh `request_key`, `operator_confirmed: true` and an
approval note. It creates a new action with `retry_of` and incremented attempt_count;
ordinary HTTP retries/resume keep their original action ID. Discovered/in-progress
cancel and automatic reinstallation are intentionally unsupported.

## Operations and local CLI

`GET /health` returns `{ "status": "ok", "stage": "management" }`.
`GET /ready` checks database, migration revision and a temporary storage write.
`GET /` serves the built React app; `/assets/` serves only its static assets,
never firmware. Missing dashboard builds return 503 with build instructions.
All normal responses include request IDs and no-store policy.

The original `target-create`, `target-show`, `target-list`, `target-enable`,
`target-disable`, `token-rotate`, `token-revoke` and `request-config` local CLI
commands remain supported with `--tenant`. Run them from `backend/` with trusted
local database access. Generated device tokens go to a new private `--token-file`.

## Target deletion and recovery

`DELETE /api/targets/{id}` is idempotent for an already-deleted record (204). It
locks the same target row used by assignment, rejects any active action (409),
sets deleted_at, disables the target, revokes active credentials and records the
administrator audit event. No physical device operation occurs. DDI authentication
fails for deleted records. Normal target list/get/edit/token operations exclude
or reject them; `GET /api/targets?include_deleted=true` includes tombstones for
historical inspection and the recovery UI. Target history remains readable.

Restore keeps the target disabled and leaves old credentials revoked. An admin
must subsequently enable it, rotate and privately provision a new token. Restored
records retain the same ID/history; re-enrollment with the same tenant/controller
identity is rejected while a tombstone exists. Fleet summary counts exclude deleted
targets, while completed deployment/audit history remains intact.
