# Security · v0.2

## Separate identities

Device TargetTokens have 256 bits of server-generated randomness, SHA-256 digest
storage, constant-time verification and strict tenant/controller scope. Enabled
state and active credential are checked for every DDI request. Artifacts/actions
also require ownership through that target's active deployment. There is no gateway
token support, unauthenticated auto-enrollment or public artifact directory.

Management accounts use Argon2id passwords, random server-side session tokens
stored as digests, expiry, HttpOnly/SameSite=Strict cookies and CSRF tokens checked
on every mutation. Cookies become Secure in production. The browser keeps CSRF
state in memory; no session token is stored in localStorage. Login checks supplied
Origin and limits failed attempts per username/direct IP. User disable and local
password reset revoke sessions. A user cannot disable their own account.

Viewers inspect fleet/releases/history, operators also upload and assign, and
administrators manage device credentials, accounts and audit logs. Management roles
are instance-wide; per-user tenant grants are not implemented. Device isolation
remains tenant-specific. No device credential confers management access.

Create administrators locally with `ota admin-create USERNAME`; choose a unique
password of at least 12 characters at the private prompt. There is no default
password or seeded administrator. Use `ota admin-password-reset USERNAME` for local
recovery. Provisioned device secrets appear only once in creation/rotation responses
or private CLI files, not normal list/inspect responses. Rotation/revocation affects
subsequent requests, not already-authorized in-flight streams.

## Uploads and bundle trust

Authenticate before parsing multipart bodies. Actual incoming bytes, metadata and
part counts are bounded, including chunked transfers. File parts spool to disk;
publication hashes in fixed-size chunks and uses private generated content keys.
Unsafe filenames, empty files and oversize uploads are rejected. Unique hashes
prevent duplicate catalog records; atomic publication never overwrites objects.
The local storage path is not a user-controlled path, symlink alias or static URL.

SHA-1/MD5 are wire compatibility/checksum fields, not signature trust mechanisms.
A SHA-256 checksum, `.raucb` extension, filename and operator-supplied compatible
string do not establish a cryptographically valid bundle or a truthful manifest.
The server exposes `NOT_VERIFIED`. Verify trusted bundle metadata/signatures through
your approved process and keep RAUC target verification mandatory.

An assignment requires exact version/compatibility confirmation, an approval note,
a fresh request identity and explicit operator confirmation. Uploading or creating
a release never assigns it. Forced mode lets the unchanged updater install on its
next poll; Download Only does not invoke RAUC. Do not approve a Forced assignment
before identifying the target and checking bundle trust/version/recovery access.
The server cannot physically validate that an operator's approval note is truthful.

Artifacts are withdrawn, not physically deleted; active references block withdrawal.
Objects retain historical identity and avoid unlink/open races. Normal upload
failures remove temporary publication files. If the process dies between object
publication and metadata commit, an unreferenced object may remain; retrying the
upload can recover it. Crash leftovers require operator-reviewed storage maintenance,
not an automatic cleanup job that could remove a live upload. No S3 adapter exists yet.

## HTTP, TLS and proxy trust

HTTP is for the controlled lab; production settings require PostgreSQL and an
externally reachable HTTPS origin. Terminate TLS with a trusted certificate,
provision the issuing CA on the target, set `ssl=true`, `ssl_verify=true` and never
disable verification as a production workaround. Generated URLs use configured
PUBLIC_BASE_URL only. Allowed hosts are explicit and arbitrary forwarded headers
are ignored. Run Uvicorn with `--no-proxy-headers` and expose only a private backend
behind the TLS proxy. Production settings cannot independently prove network TLS.

The Nginx example has a dedicated bounded upload location with buffering disabled;
match proxy/app upload limits. Do not expose storage through an unauthenticated
alias. The example has no HTTP fallback production listener. Apply network controls,
rate limiting and monitoring appropriate to the deployment before public exposure.

## Logs, backups and evidence

Structured request logs use route templates and generated correlation IDs; no
raw Authorization, passwords, session tokens, request bodies or private keys are
logged. Audit events preserve security-sensitive operations and actor IDs without
credential material. Device attributes, event detail, DB backups and raw captures
may contain private operational data; store them with restricted access. Avoid
committing raw captures. Rotate any credential disclosed in a shared HTTP trace.

The SQLite backup helper uses the online backup API and mode 0600 files; use normal
PostgreSQL backup procedures and test recovery. Database writes and migration tests
are covered on development engines; this does not certify production restoration,
large fleet operation or certificate deployment. Instance-wide quotas, long-term
audit retention, external identity, per-tenant management roles and in-progress
cancellation remain future hardening work.

Installation success is not boot validation. Slot selection, eMMC writes, signature
verification, Barebox activation, controlled reboot and mark-good remain under
existing target/operator control. Boot confirmation, reported running version and
rollback evidence stay unknown when no separate verified signal is available.

## Deleted targets

Administrator-only deletion is a reversible fleet archive, not a physical device
wipe. It revokes credentials and excludes the target from authentication, assignment
and ordinary management lists. Active deployments block deletion; target row locking
serializes deletion against new assignments. Audit/deployment/attribute records and
the tenant/controller identity remain retained. The restore endpoint never revives
old credentials or enables communication implicitly. No actual target is deleted
as part of migration or application startup.
