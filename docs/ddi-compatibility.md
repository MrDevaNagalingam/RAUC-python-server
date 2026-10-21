# DDI compatibility · v0.2

The device continues using hawkBit DDI v1 and `Authorization: TargetToken <secret>`.
No target-side Python agent, MQTT, WebSocket, partition code or firmware modification
is required. Preserve the installed updater configuration except the server origin
and securely provisioned device credential.

## Protocol evidence

Pinned official sources inspected before implementation:

- [rauc-hawkbit-updater v1.3 protocol implementation](https://github.com/rauc/rauc-hawkbit-updater/blob/e19bc259a615ea31584c4056f365db46237d70f9/src/hawkbit-client.c): polling/status builder, deployment parser, download/checksum and feedback.
- [v1.3 action states](https://github.com/rauc/rauc-hawkbit-updater/blob/e19bc259a615ea31584c4056f365db46237d70f9/include/hawkbit-client.h).
- [hawkBit official DDI resource implementation](https://github.com/eclipse-hawkbit/hawkbit/blob/bf5812735d729b463aad45f9ec9c0089a42daefa/hawkbit-ddi/hawkbit-ddi-resource/src/main/java/org/eclipse/hawkbit/ddi/rest/resource/DdiRootController.java).
- [hawkBit API models](https://github.com/eclipse-hawkbit/hawkbit/tree/bf5812735d729b463aad45f9ec9c0089a42daefa/hawkbit-ddi/hawkbit-ddi-api/src/main/java/org/eclipse/hawkbit/ddi/json/model): DdiControllerBase, ConfigData, DeploymentBase, Deployment, Chunk, ArtifactHash, Status and Result.

The Eclipse documentation URLs redirected to the project landing page, so the
official Java API/model documentation was inspected directly. The hawkBit reference
revision is modern; the exact version of the previous lab server is unknown.
There was no standalone capture file: ConfigData/progress fixtures were transcribed
from the master prompt. The user subsequently supplied CLI evidence of the real
lab target being Online with the expected three attributes on 2026-10-21. No new
raw hardware capture was collected by this implementation turn.

## Endpoint matrix

All paths below begin `/{tenant}/controller/v1/{controller_id}`. Wrong/missing,
disabled or revoked credentials receive generic 401 with `WWW-Authenticate:
TargetToken`. Action and artifact authorization additionally check tenant and target.

| Method / suffix | Success contract | Implementation and verification |
|---|---|---|
| GET empty suffix | 200 JSON config.polling.sleep and HAL actions | Unit/API tests, actual v1.3 host test; user-supplied hardware polling evidence |
| PUT `/configData` | 200 empty body, not 204 | Fixture, concurrency and real C-client tests; user-supplied hardware attributes |
| GET `/deploymentBase/{action_id}` | 200 JSON id and deployment chunks; 410 if terminal | Official model/parser checks; actual C-client test in Download Only mode |
| GET `/softwaremodules/{module_id}/artifacts/{filename}` | 200 binary or 206 single byte range | ACL/boundary/range tests; actual v1.3 complete download and SHA-1 verification |
| HEAD same artifact URL | Same headers, no body | Automated tests; updater HEAD usage not independently observed |
| POST `/deploymentBase/{action_id}/feedback` | 200 empty body | Prompt lowercase fixtures, terminal protection tests; actual C-client checksum feedback |
| cancelAction / installedBase / confirmationBase | Not exposed or advertised | Not implemented; safe server cancellation only before discovery |

CBOR, ETags/304 for controller resources, multipart byte ranges, scheduled maintenance
windows and exact hawkBit error-body equivalence are not claimed. Unsupported modes
are rejected; they never silently become Forced.

## Controller polling and configuration

The observed client's `Accept: application/json;charset=UTF-8` is accepted. Responses
use `application/json`. Poll intervals are formatted `HH:MM:SS`, bounded to 1–86399
seconds for the v1.3 `%T` parser. Optional per-target overrides use the same bound.
Successful polling refreshes last_seen_at, last_poll_at and last_request_at.

```json
{
  "config": {"polling": {"sleep": "00:01:00"}},
  "_links": {"configData": {"href": "http://REACHABLE_ORIGIN/DEFAULT/controller/v1/test-target/configData"}}
}
```

ConfigData is requested initially or by the local `request-config` command, and
again after successful installation. Its link disappears after a successful PUT.
With no assigned action, `_links` is empty; the client reports `No new software.`.
This service never assigns an update simply because firmware or test data exists.

ConfigData accepts the unchanged body from the prompt:

```json
{
  "time": "20261016T104324",
  "status": {"result": {"finished": "success"}, "execution": "closed"},
  "data": {"model": "T1", "mac_address": "ff:ff:ff:ff:ff:ff", "hw_revision": "2"}
}
```

The unknown time/status fields are ignored for attribute updates, following the
official ConfigData model. They are not installation evidence. Optional lowercase
`mode` supports merge (default), replace and remove by supplied keys. Values must
be strings. At most 100 attributes, keys 1–128 chars and values up to 2048 chars;
JSON is bounded at 64 KiB by default. Empty maps are rejected per the official
NotEmpty contract; empty `[device]` compatibility has not been tested.

## Deployment and download

An active assignment adds a `deploymentBase` HAL link with its stable action ID.
Every generated origin comes from `PUBLIC_BASE_URL`, never untrusted forwarding
headers. The initial poll marks discovery before exposing the link, preventing a
server cancellation from racing with the device following that link.

```json
{
  "id": "7",
  "deployment": {
    "download": "forced",
    "update": "forced",
    "chunks": [{
      "part": "os", "version": "1.1", "name": "OS",
      "artifacts": [{
        "filename": "firmware.raucb", "size": 12345,
        "hashes": {"sha1": "...", "md5": "...", "sha256": "..."},
        "_links": {"download-http": {"href": "http://REACHABLE_ORIGIN/DEFAULT/controller/v1/test-target/softwaremodules/1/artifacts/firmware.raucb"}}
      }]
    }]
  }
}
```

The hash/size values above are illustrative; real responses use computed values
from the immutable action snapshot. v1.3 requires **SHA-1** for its checksum check.
SHA-256 is also calculated/stored, and the official ArtifactHash model supports it.
For HTTPS use the `download` relation; HTTP uses `download-http`. The C client builds
the feedback URL itself; no invented feedback-link requirement was introduced.
Exactly one chunk/artifact is emitted because v1.3 rejects multiple entries.

Download Only changes `deployment.update` to `skip`, retaining `download: forced`.
The actual v1.3 host test verified it downloaded exact bytes, sent checksum OK,
and did not invoke RAUC. Completion is `DOWNLOAD_SUCCEEDED`, not installation success.
Soft/Time Forced and maintenance windows remain disabled until separately verified.

Downloads require this target's active assignment for that module/filename. No
public storage directory exists. Content-Length, octet-stream type, Accept-Ranges,
SHA-256 ETag and Content-Range are provided. Single closed/open/suffix byte ranges
are supported. Invalid, empty, unsatisfiable or multiple ranges return 416 with
`Content-Range: bytes */SIZE`. If-Range mismatch serves the full representation.
Serving or closing a stream does not establish successful device checksum/install.

## Feedback and state

Feedback uses string action IDs, optional raw device timestamp, lowercase execution,
result.finished and detail strings. Closed execution requires success or failure.
URL/body ID mismatch is 400. Raw JSON/detail/device time and receipt time persist.
Details without percentages retain unknown progress. Identical bodies are
fingerprinted/deduplicated; late differing bodies remain in history without
changing terminal states. Stages and derived percentages do not regress.

Forced `closed/success` maps to `INSTALL_SUCCEEDED`; `closed/failure` records a
failure and its original detail. Neither creates a reboot or BOOT_CONFIRMED result.
A Download Only checksum-OK report maps to `DOWNLOAD_SUCCEEDED`. Absence of feedback
never implies success. No automatic retry or time-based reinstallation occurs.

Network retries and resumed downloads use the original action. An operator's
explicit reattempt creates a new action linked by retry_of, because unmodified
DDI feedback has no attempt generation to distinguish delayed old results safely.
Server cancellation is supported only before the target first sees the deployment
link; in-progress cancellation is explicitly rejected rather than simulated.

## Reproduce actual-client verification

Build the unchanged release outside this repo with Meson/Ninja, pkg-config, GLib/GIO,
json-glib and libcurl development prerequisites:

```bash
git clone --depth 1 --branch v1.3 https://github.com/rauc/rauc-hawkbit-updater.git /tmp/updater-v1.3
meson setup /tmp/updater-v1.3/build /tmp/updater-v1.3 -Dsystemd=disabled -Dapidoc=disabled
ninja -C /tmp/updater-v1.3/build
cd backend
UPDATER_V13_BIN=/tmp/updater-v1.3/build/rauc-hawkbit-updater ../.venv/bin/pytest -q -m updater
```

These tests use ephemeral targets/databases, a loopback HTTP server and a synthetic
payload. They test protocol/download/checksum behavior without a RAUC simulator,
physical installation or reboot. They do not verify signature trust, real signed
bundle installation, forced hardware behavior or target TLS.
