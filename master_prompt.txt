PROJECT TITLE:
Python-Based OTA Firmware Management Platform
Compatible with hawkBit DDI v1, RAUC, and PHYTEC Embedded Linux Gateways

====================================================================
1. PROJECT OBJECTIVE
====================================================================

Develop a complete, production-oriented OTA (Over-the-Air) firmware
management application using Python.

The application must replace the existing Eclipse hawkBit SERVER.

IMPORTANT:
We are NOT replacing the existing target-side updater.

The embedded device already contains:

1. rauc-hawkbit-updater v1.3
2. RAUC v1.11.3
3. Barebox bootloader
4. A/B root filesystem partitions
5. A/B boot partitions
6. RAUC signed bundle verification
7. RAUC D-Bus service
8. RAUC boot slot marking service

All these components must remain unchanged.

The Python OTA server must implement the necessary hawkBit Direct
Device Integration API (DDI v1), so the existing embedded target
can communicate with it without firmware-side modifications.

The system must support:

- HTTP for local development and testing.
- HTTPS for secure production deployment.
- Multiple embedded targets.
- TargetToken authentication.
- Firmware upload and management.
- Software module management.
- Distribution/release management.
- Firmware deployment assignments.
- Target polling.
- Firmware metadata retrieval.
- Artifact downloads.
- Download integrity verification.
- HTTP Range support.
- OTA installation progress reporting.
- RAUC installation feedback.
- Deployment success/failure tracking.
- Target online/offline monitoring.
- Retry handling.
- Firmware history.
- A/B update status tracking.
- Rollback-related status and recovery monitoring.
- A responsive web dashboard.
- REST management APIs.
- Deployment logs and audit history.

The software must be modular, maintainable, extensible,
documented, and suitable for further industrial development.

Do not create a dummy simulator as the primary implementation.

Develop real FastAPI endpoints and backend functionality that can
communicate with the existing rauc-hawkbit-updater binary.

The first operational milestone is successful DDI communication
with the unchanged target.

The second operational milestone is successful end-to-end
firmware deployment using a signed RAUC bundle.

====================================================================
2. EXISTING HARDWARE AND SOFTWARE ENVIRONMENT
====================================================================

Embedded hardware:

PHYTEC phyBOARD-Segin i.MX6UL

Operating system:

Yocto Embedded Linux

RAUC version:

1.11.3

rauc-hawkbit-updater version:

1.3

Bootloader:

Barebox

RAUC compatible string:

phyboard-segin-imx6ul-7

Existing hawkBit server:

192.168.11.161:8080

Tenant:

DEFAULT

Example target/controller ID:

test-target

Existing target configuration:

[client]

hawkbit_server = 192.168.11.161:8080

ssl = false

ssl_verify = false

tenant_id = DEFAULT

target_name = test-target

auth_token = <TARGET_SECURITY_TOKEN>

bundle_download_location = /tmp/bundle.raucb

retry_wait = 60

connect_timeout = 20

timeout = 60

low_speed_time = 0

low_speed_rate = 0

post_update_reboot = false

log_level = message

[device]

mac_address = ff:ff:ff:ff:ff:ff

hw_revision = 2

model = T1


SECURITY REQUIREMENT:

Never hardcode actual target tokens in source code.

The real token must be provisioned securely.

The token previously used in testing must be considered exposed
and rotated before production deployment.

====================================================================
3. EXISTING TARGET SERVICES
====================================================================

The target already contains the following systemd services.

SERVICE 1:

rauc-hawkbit-updater.service

ExecStart:

/usr/bin/rauc-hawkbit-updater -s \
-c /etc/rauc-hawkbit-updater/config.conf

Purpose:

- Connect to OTA server.
- Authenticate.
- Poll for deployments.
- Retrieve deployment metadata.
- Download firmware.
- Verify the artifact checksum.
- Request RAUC installation.
- Receive RAUC installation progress.
- Send feedback to server.

SERVICE 2:

rauc.service

RAUC D-Bus name:

de.pengutronix.rauc

ExecStart:

/usr/bin/rauc --mount=/run/rauc service

Purpose:

- Verify signed RAUC bundles.
- Validate compatibility.
- Identify update target slots.
- Install firmware into inactive slots.
- Update bootloader activation information.
- Manage A/B update state.

SERVICE 3:

rauc-mark-good.service

ExecStart:

/usr/bin/rauc status mark-good

Purpose:

Mark the currently booted slot good after the configured
boot-completion conditions are satisfied.

IMPORTANT:

The Python OTA SERVER must not write eMMC partitions directly.

The Python server only distributes firmware and manages the
OTA process.

All physical installation operations must remain under RAUC.

====================================================================
4. EXISTING RAUC PARTITION ARCHITECTURE
====================================================================

Existing RAUC configuration:

[system]

compatible=phyboard-segin-imx6ul-7

bootloader=barebox

mountprefix=/mnt/rauc

data-directory=/mnt/config/rauc/

[handlers]

pre-install=/usr/lib/rauc/rauc-pre-install.sh

post-install=/usr/lib/rauc/rauc-post-install.sh

[keyring]

path=mainca-rsa.crt.pem

[slot.bootloader.0]

device=/dev/mmcblk1

type=boot-emmc

[slot.rootfs.0]

device=/dev/mmcblk1p5

type=ext4

bootname=system0

resize=true

[slot.boot.0]

device=/dev/mmcblk1p1

type=vfat

parent=rootfs.0

[slot.rootfs.1]

device=/dev/mmcblk1p6

type=ext4

bootname=system1

resize=true

[slot.boot.1]

device=/dev/mmcblk1p2

type=vfat

parent=rootfs.1


OTA INSTALLATION FLOW:

Current active system:

rootfs.0 + boot.0

Inactive update target:

rootfs.1 + boot.1

RAUC installs the new firmware into the inactive slots.

After installation, the bootloader can be configured to boot
the updated system.

After successful reboot and validation, RAUC marks the
newly booted slot good.

The reverse direction must also work:

rootfs.1 -> rootfs.0

IMPORTANT:

RAUC decides which partition is inactive.

The OTA server must not hardcode an assumption that every
update targets rootfs.1.

The target must retain responsibility for slot selection.

The server should maintain separate concepts for:

- Deployment completed.
- RAUC installation completed.
- Reboot pending.
- Updated firmware boot confirmed.
- Rollback detected.

Do not consider installation success equivalent to confirmed
successful boot.

The existing updater may report installation completion
before reboot.

If confirmed post-reboot status is unavailable through the
existing DDI client, expose it as UNKNOWN rather than SUCCESS.

A future optional device-health reporter may be added,
but do not make it a requirement for basic DDI compatibility.

====================================================================
5. REQUIRED SYSTEM ARCHITECTURE
====================================================================

Implement the following architecture:

                    WEB DASHBOARD
                          |
                          |
                          v
                   FASTAPI SERVER
                          |
          +---------------+---------------+
          |               |               |
          v               v               v
     Management API    DDI API       Auth Service
          |               |               |
          +---------------+---------------+
                          |
                          v
                  Deployment Engine
                          |
             +------------+------------+
             |                         |
             v                         v
          Database               Artifact Storage
             |                         |
             +------------+------------+
                          |
                          |
                   HTTP / HTTPS
                          |
                          v
                PHYTEC Embedded Target
                          |
                          v
                rauc-hawkbit-updater
                          |
                          v
                     RAUC D-Bus
                          |
                          v
                    RAUC Installer
                          |
                          v
                   A/B eMMC Storage


TECHNOLOGY STACK:

Backend:

Python 3.11+ where supported by the selected dependencies.

FastAPI

Uvicorn

SQLAlchemy

Alembic

Pydantic

Database:

SQLite for local development.

PostgreSQL for production.

Artifact storage:

Local filesystem initially.

Design an abstraction supporting future S3-compatible storage.

Frontend:

React with TypeScript.

Use a clean, responsive, professional UI.

Build API clients and reusable components.

Communication:

REST API over HTTP/HTTPS.

hawkBit-compatible DDI v1 for targets.

Do not require MQTT or RabbitMQ for the DDI communication path.

Authentication:

Separate management-user authentication and device authentication.

Transport security:

Nginx/Caddy reverse proxy or equivalent TLS termination
for production HTTPS.

Deployment:

Docker Compose for local/production-like testing.

Also provide a non-Docker development procedure.

====================================================================
6. IMPORTANT: EXACT HAWKBIT DDI COMPATIBILITY
====================================================================

This is the most critical requirement.

The existing target uses:

rauc-hawkbit-updater v1.3

Its HTTP User-Agent observed in the capture is:

rauc-hawkbit-c-agent/1.0

Its authentication scheme is:

Authorization: TargetToken <TOKEN>

Its HTTP Accept header includes:

application/json;charset=UTF-8

The Python server must reproduce the relevant hawkBit DDI v1
API behavior expected by this target.

DO NOT invent a new device protocol.

DO NOT force the target to use a custom Python-specific API.

DO NOT assume that an approximate JSON response is compatible.

The implementation must match the required DDI:

- Endpoint paths.
- Request methods.
- Request bodies.
- Response bodies.
- JSON field names.
- JSON value casing.
- Required and optional fields.
- HAL links.
- HTTP status codes.
- Response headers.
- Polling configuration.
- Deployment metadata.
- Artifact metadata.
- Artifact URLs.
- Feedback semantics.
- Authentication behavior.

Use the available communication captures as protocol fixtures.

Reference protocol:

Eclipse hawkBit Direct Device Integration API v1.

Before implementing each endpoint, verify its schema against
the relevant hawkBit API documentation and, where necessary,
the updater v1.3 source code.

IMPORTANT:

The supplied capture contains confirmed requests for:

GET /DEFAULT/controller/v1/test-target

PUT /DEFAULT/controller/v1/test-target/configData

POST /DEFAULT/controller/v1/test-target/deploymentBase/7/feedback

The capture does not provide sufficient evidence to reconstruct
every deployment GET response and artifact-download exchange.

Verify these missing contracts instead of fabricating their
contents.

Document all assumptions and unresolved compatibility details.

====================================================================
7. DDI CONTROLLER POLLING API
====================================================================

Implement:

GET /{tenant}/controller/v1/{controller_id}

Example:

GET /DEFAULT/controller/v1/test-target

Request authentication:

Authorization: TargetToken <TOKEN>

Responsibilities:

1. Validate tenant.
2. Validate controller ID.
3. Authenticate device token.
4. Update target last-seen timestamp.
5. Identify pending deployments.
6. Return correct polling configuration.
7. Return available DDI actions through HAL links.
8. Return deployment links when an update is assigned.
9. Return valid no-deployment responses otherwise.

Required behavior:

When no deployment is available:

- Return a valid DDI response.
- Do not incorrectly report an error.
- Provide a supported polling interval.
- Do not repeatedly assign completed deployments.

When deployment is available:

- Return the exact DDI deployment link.
- Preserve deployment/action ID.
- Ensure URLs are reachable by the embedded target.
- Do not expose localhost-only URLs to remote targets.

Make polling configurable at server level.

Support per-target polling configurations if compatible with DDI.

Example server settings:

polling_interval_seconds = 60

connection_timeout_seconds = 20

request_timeout_seconds = 60

Actual response formatting must follow the verified DDI schema.

====================================================================
8. DEVICE AUTHENTICATION
====================================================================

Implement TargetToken authentication.

Incoming header:

Authorization: TargetToken <token>

Database:

Each target has a unique controller ID.

Each target belongs to a tenant.

Each target has a securely stored authentication credential.

Validation must confirm:

- Tenant exists.
- Target exists.
- Target is enabled.
- Token is valid.
- Token belongs to the requested target.
- Target is authorized for the requested deployment/artifact.

Use secure credential storage.

Do not log raw tokens.

Use constant-time verification for appropriate token comparisons.

Support:

- Token generation.
- Token rotation.
- Token revocation.
- Disabled targets.
- Unauthorized request handling.
- Authentication audit events.

Do not allow one target to use its token to access another
target's deployment or private artifact.

Use separate authentication for dashboard administrators.

Do not expose device TargetTokens in normal frontend API responses.

====================================================================
9. DEVICE CONFIGURATION API
====================================================================

Implement:

PUT /{tenant}/controller/v1/{controller_id}/configData

Confirmed real target request format:

{
  "time": "20261016T104324",
  "status": {
    "result": {
      "finished": "success"
    },
    "execution": "closed"
  },
  "data": {
    "model": "T1",
    "mac_address": "ff:ff:ff:ff:ff:ff",
    "hw_revision": "2"
  }
}

This format is observed in the supplied traffic capture.

The server must:

- Authenticate the target.
- Parse the request.
- Validate acceptable attributes.
- Store attributes in the database.
- Update device metadata.
- Support changes in device attributes.
- Return the correct DDI response.

Store attributes such as:

model
mac_address
hw_revision

Do not assume these are the only supported attributes.

The [device] configuration section can contain additional
key-value pairs.

The backend should support arbitrary permitted attributes.

Expose these fields in the dashboard.

Example dashboard:

Target Name: GATEWAY

Controller ID: test-target

Model: T1

Hardware Revision: 2

MAC Address: ff:ff:ff:ff:ff:ff

Last Seen: <timestamp>

Connection Status: Online/Offline

====================================================================
10. FIRMWARE UPLOAD MANAGEMENT
====================================================================

Implement a firmware upload management API.

Supported initial artifact format:

.raucb

The server must allow an administrator to upload RAUC bundles
through the web dashboard.

Requirements:

- Multipart file upload.
- Large firmware upload support.
- Streaming upload to disk.
- Temporary file handling.
- Maximum file size configuration.
- File extension validation.
- Content handling without loading the entire file into RAM.
- SHA-256 checksum calculation.
- Artifact size calculation.
- Duplicate detection.
- Secure storage filenames.
- Atomic artifact publication.
- Artifact metadata persistence.
- Upload progress reporting.
- Upload failure recovery.
- Controlled artifact deletion.

Do not assume all bundles are exactly 200 MB.

Support larger firmware images through streaming.

Store:

Firmware ID
Firmware Name
Firmware Version
Description
Vendor
Compatible Device
Artifact Filename
Artifact Size
SHA-256
Upload Timestamp
Uploaded By
Storage Path
Availability Status

Example:

Firmware Name: RB-DCU

Version: 1.1

Vendor: PHYTEC

Compatible: phyboard-segin-imx6ul-7

Artifact: phytec-qt5demo-bundle.raucb

Status: Available

Optional:

If the RAUC host tooling is available, inspect the bundle
using RAUC-compatible tools and extract available metadata.

Do not claim a bundle is cryptographically valid merely
because it has a .raucb extension.

RAUC signature verification remains mandatory on the target.

The upload workflow may additionally verify bundles using
configured trusted certificates and appropriate tooling.

====================================================================
11. SOFTWARE MODULE MANAGEMENT
====================================================================

Implement a software module abstraction compatible with
hawkBit deployment semantics.

Software modules contain:

- Module ID.
- Module name.
- Version.
- Type.
- Vendor.
- Description.
- One or more associated artifacts where supported.

Example:

Type: OS

Name: RB-DCU

Version: 1.1

Vendor: PHYTEC

Artifact: firmware.raucb

The initial RAUC use case should support a complete OS update
delivered as one signed RAUC bundle.

Do not split a signed RAUC bundle into independently installable
files unless the device-side updater explicitly supports it.

Software modules must be selectable in the dashboard.

====================================================================
12. DISTRIBUTION / RELEASE MANAGEMENT
====================================================================

Implement distribution management similar to hawkBit.

A distribution represents deployable software.

Example:

Distribution Name: DEVA

Version: 1.1

Description: RB-DCU OTA Update

Type: OS with app(s)

Associated Software Module:

RB-DCU 1.1

Required functionality:

- Create distribution.
- Assign software modules.
- Edit metadata.
- List distributions.
- Track versions.
- Validate associations.
- Prevent deletion of artifacts required by active deployments.
- Display release contents.
- Create deployment from a distribution.

The database must maintain the relationship:

Distribution
     |
     v
Software Module
     |
     v
Artifact (.raucb)

Preserve stable artifact references for existing deployment
actions.

Do not break in-progress updates when an administrator edits
release metadata.

====================================================================
13. TARGET MANAGEMENT
====================================================================

Implement multiple target management.

Each embedded target must have:

Target ID
Controller ID
Tenant ID
Display Name
Description
Authentication Credential
Hardware Model
Hardware Revision
MAC Address
Last Seen
Connection Status
Current Known Firmware
Assigned Distribution
Deployment Status
Created Timestamp
Updated Timestamp

Required functions:

- Create target.
- View target.
- Edit target metadata.
- Disable target.
- Generate TargetToken.
- Rotate TargetToken.
- View target attributes.
- View assigned firmware.
- View deployment history.
- View update progress.
- View last error.
- View recent communication activity.

Targets must be distinguished by controller ID and tenant.

Example targets:

gateway-001
gateway-002
gateway-003

All targets can use the same DDI endpoints with their own
controller IDs and tokens.

Example:

GET /DEFAULT/controller/v1/gateway-001

GET /DEFAULT/controller/v1/gateway-002

GET /DEFAULT/controller/v1/gateway-003

The server must authenticate each independently.

Do not use IP address as the primary device identity.

Targets may change networks or obtain different DHCP addresses.

====================================================================
14. DEPLOYMENT ASSIGNMENT
====================================================================

Implement deployment assignment management.

An administrator must be able to:

1. Select a target.
2. Select a distribution.
3. Select the update mode.
4. Confirm assignment.
5. Monitor execution.

Support the hawkBit deployment modes that the updater
actually supports.

Requested modes:

- Forced.
- Soft.
- Download Only.
- Time Forced.

IMPORTANT:

Verify compatibility of each mode with
rauc-hawkbit-updater v1.3.

Do not assume the updater implements every possible hawkBit
deployment mode.

For the first working milestone, prioritize the forced
deployment flow demonstrated in the current system.

Unsupported modes must be clearly disabled or marked
unsupported rather than silently behaving as Forced.

Deployment records must contain:

Deployment ID
Tenant ID
Target ID
Distribution ID
Firmware/Artifact Reference
Assignment Type
Deployment State
Created Time
Started Time
Completed Time
Error Details
Attempt Count
Last Updated Time

Prevent conflicting deployments to the same target.

Avoid duplicate installation caused by repeated polling.

Preserve action IDs across retries.

Do not automatically initiate another installation after
the server has accepted final successful feedback.

====================================================================
15. DEPLOYMENT DETAILS API
====================================================================

Implement:

GET /{tenant}/controller/v1/{controller_id}/deploymentBase/{action_id}

The response must follow the real hawkBit DDI v1 deployment
schema compatible with the installed updater.

Required information includes, as applicable:

- Deployment/action ID.
- Deployment instructions.
- Download mode.
- Update mode.
- Software module/chunk metadata.
- Artifact filename.
- Artifact size.
- SHA-256 checksum.
- Correct artifact download links.
- Feedback link.
- Supported maintenance-window information.

IMPORTANT:

Verify the complete response structure against:

1. hawkBit DDI v1 specification.
2. rauc-hawkbit-updater v1.3 behavior.
3. Actual hawkBit responses, if available.

Do not invent field names.

Do not use approximate placeholder JSON as the production
implementation.

Artifact URLs must be resolvable from the embedded target.

If running inside Docker, never generate container-only URLs
such as:

http://172.18.0.2:8080

unless the device can actually reach that address.

Never generate:

http://localhost:8080

for remote target artifact downloads.

Use an explicitly configured public/reachable base URL,
with safe reverse-proxy forwarding rules.

====================================================================
16. ARTIFACT DOWNLOAD API
====================================================================

Implement hawkBit-compatible artifact download endpoints.

Expected endpoint family:

GET /{tenant}/controller/v1/{controller_id}/softwaremodules/
    {module_id}/artifacts/{filename}

Use the exact verified DDI URL pattern.

Required functionality:

- Authenticate target.
- Verify artifact authorization.
- Confirm the artifact belongs to an authorized deployment.
- Validate filename/path.
- Prevent path traversal.
- Stream binary firmware data.
- Provide correct Content-Length.
- Provide appropriate Content-Type.
- Support HEAD if required.
- Support HTTP Range requests.
- Support HTTP 206 Partial Content.
- Return correct Content-Range.
- Support interrupted-download recovery where compatible.
- Avoid reading the complete firmware into RAM.
- Handle disconnected clients.
- Preserve artifact integrity.
- Track download activity.
- Handle concurrent downloads from multiple targets.

The target may download to:

/tmp/bundle.raucb

This path is controlled by the existing target configuration.

The Python server does not control the local installation
directory directly.

The firmware bundle should be delivered exactly as stored.

Do not modify the binary during download.

Do not repackage the RAUC bundle.

Do not bypass signature verification.

Verify compatibility with the actual updater's download
and checksum behavior.

====================================================================
17. DEPLOYMENT FEEDBACK API
====================================================================

Implement:

POST /{tenant}/controller/v1/{controller_id}/deploymentBase/
     {action_id}/feedback

This endpoint is critical.

The existing target sends installation progress through
this endpoint.

A confirmed target feedback example is:

{
  "id": "7",
  "time": "20261016T104216",
  "status": {
    "result": {
      "finished": "none"
    },
    "execution": "proceeding",
    "details": [
      "60% Copying image to rootfs.1 done."
    ]
  }
}

Another observed example:

{
  "id": "7",
  "time": "20261016T104216",
  "status": {
    "result": {
      "finished": "none"
    },
    "execution": "proceeding",
    "details": [
      "62% Checking slot boot.1 done."
    ]
  }
}

Final installation feedback observed in the capture:

{
  "id": "7",
  "time": "20261016T104222",
  "status": {
    "result": {
      "finished": "success"
    },
    "execution": "closed",
    "details": [
      "Software bundle installed successfully."
    ]
  }
}

The server must:

1. Authenticate the reporting target.
2. Verify deployment ID.
3. Validate feedback structure.
4. Store feedback timestamps.
5. Store execution state.
6. Store completion result.
7. Store details.
8. Track installation progress.
9. Update deployment state.
10. Make feedback visible to the dashboard.
11. Return the DDI-compatible HTTP response.

IMPORTANT:

The observed updater uses lowercase values such as:

"proceeding"
"closed"
"none"
"success"

Do not incorrectly require uppercase values.

Follow the actual client/API contract.

Progress messages should be preserved as received.

The server may additionally extract percentages for display,
but must not discard the original details.

Example:

"62% Copying image to boot.1"

Store:

Raw Detail: "62% Copying image to boot.1"

Parsed Percentage: 62

Parsed Stage: RAUC installation

If a detail does not contain a percentage, preserve the text
and keep progress unknown.

Avoid assuming every detail is progress-formatted.

Make feedback processing idempotent where appropriate.

Repeated network requests must not corrupt the deployment
state or duplicate final execution side effects.

====================================================================
18. DEPLOYMENT STATE MACHINE
====================================================================

Design a robust deployment state machine.

Internal states may include:

CREATED

ASSIGNED

WAITING_FOR_TARGET

DISCOVERED

DOWNLOADING

DOWNLOADED

INSTALLING

INSTALL_SUCCEEDED

INSTALL_FAILED

REBOOT_PENDING

BOOT_CONFIRMED

ROLLBACK_DETECTED

CANCELED

REJECTED

TIMED_OUT

UNKNOWN

These are internal application states.

Do not assume these are all hawkBit DDI execution values.

Implement a mapping between:

Raw DDI feedback
        |
        v
Internal Deployment State
        |
        v
Dashboard Status

The raw DDI result must always be retained.

Support:

- Valid state transitions.
- Invalid-transition protection.
- Retry handling.
- Timeout detection.
- Event history.
- Final-state protection.
- Concurrent-request safety.
- State persistence across server restarts.

IMPORTANT:

The existing updater reports successful RAUC installation,
which does not independently prove the new firmware booted.

The server must not automatically mark BOOT_CONFIRMED
from a successful installation feedback message.

For boot confirmation, use a separate verified signal
if available.

If no verified post-reboot signal exists:

Show:

Installation Successful

Boot Confirmation: Unknown

Do not misrepresent installation completion as a
fully validated OTA lifecycle.

====================================================================
19. ONLINE / OFFLINE MONITORING
====================================================================

Implement target connectivity monitoring using DDI activity.

When the target successfully polls:

Update last_seen.

Store:

last_seen_at
last_poll_at
last_request_at

The server should calculate an estimated online status
using a configurable threshold.

Example:

Polling interval: 60 seconds

Offline threshold: 180 seconds

If no communication occurs beyond the threshold:

Display Offline.

IMPORTANT:

This is an inferred connectivity status based on polling.

It is not a continuous transport connection.

Do not implement a false persistent-connection model.

The device initiates HTTP connections when required.

The server should handle temporary network failure,
delayed polling, and disconnected devices.

Support:

- Online.
- Offline.
- Never Connected.
- Disabled.
- Last Seen timestamp.

Optional:

Expose connectivity events on the dashboard.

====================================================================
20. FIRMWARE VERSION TRACKING
====================================================================

Implement distinct fields for:

- Assigned firmware version.
- Last successfully installed version.
- Last reported running version.
- Confirmed running version, when independently verified.

Do not assume the latest assigned firmware is running.

Do not assume a completed RAUC installation means
the updated slot is currently booted.

If the DDI updater does not report the active firmware version,
display it as unknown.

A future optional target-side health-reporting component
may be implemented separately.

Do not make this optional extension necessary for the
existing updater's normal operation.

====================================================================
21. RETRY AND ERROR HANDLING
====================================================================

Implement fault-tolerant communication.

Handle:

- Target authentication failure.
- Unknown target.
- Invalid tenant.
- Invalid deployment.
- Missing artifact.
- Firmware not found.
- Network timeout.
- Disconnected download.
- Invalid Range request.
- Checksum mismatch feedback.
- RAUC installation failure.
- Invalid device compatibility.
- Server restart during deployment.
- Repeated polling.
- Duplicate feedback.
- Incomplete upload.
- Database connection errors.
- Storage exhaustion.
- Concurrent deployment conflicts.
- Interrupted firmware download.

Retries must follow an intentional policy.

Do not indefinitely reinstall a firmware version after
a terminal failure without an explicit retry policy.

Do not accidentally assign the same update repeatedly.

Preserve deployment state across server restarts.

Ensure all operations produce useful structured logs.

====================================================================
22. ADMINISTRATION API
====================================================================

Create management APIs separately from DDI APIs.

Example API families:

Authentication:

POST /api/auth/login
POST /api/auth/logout
GET  /api/auth/me

Targets:

POST /api/targets
GET  /api/targets
GET  /api/targets/{id}
PATCH /api/targets/{id}
POST /api/targets/{id}/rotate-token
GET  /api/targets/{id}/history

Firmware:

POST /api/firmware/upload
GET  /api/firmware
GET  /api/firmware/{id}
DELETE /api/firmware/{id}

Software Modules:

POST /api/software-modules
GET  /api/software-modules
GET  /api/software-modules/{id}

Distributions:

POST /api/distributions
GET  /api/distributions
GET  /api/distributions/{id}

Deployments:

POST /api/deployments
GET  /api/deployments
GET  /api/deployments/{id}
GET  /api/deployments/{id}/events
POST /api/deployments/{id}/cancel
POST /api/deployments/{id}/retry

Dashboard:

GET /api/dashboard/summary

These are management API design requirements, not
existing hawkBit DDI endpoints.

Implement sensible REST response formats.

Use Pydantic models.

Provide API validation and consistent error responses.

Generate OpenAPI documentation automatically.

Protect all management endpoints with appropriate
administrator authentication and authorization.

====================================================================
23. DATABASE DESIGN
====================================================================

Create a normalized SQLAlchemy database schema.

Required entities:

users

tenants

targets

target_attributes

target_credentials

firmware_artifacts

software_modules

software_module_artifacts

distributions

distribution_modules

deployments

deployment_events

audit_logs

application_settings


USERS:

id
username
password_hash
role
is_active
created_at

TENANTS:

id
tenant_code
name
created_at

TARGETS:

id
tenant_id
controller_id
name
description
enabled
last_seen_at
created_at
updated_at

TARGET_ATTRIBUTES:

id
target_id
attribute_key
attribute_value
updated_at

TARGET_CREDENTIALS:

id
target_id
token_hash
created_at
revoked_at
is_active

FIRMWARE_ARTIFACTS:

id
filename
storage_path
size
sha256
compatible
created_at

SOFTWARE_MODULES:

id
name
version
type
vendor
description

DISTRIBUTIONS:

id
name
version
type
description
created_at

DEPLOYMENTS:

id
tenant_id
target_id
distribution_id
action_type
internal_status
created_at
started_at
completed_at
last_updated_at
attempt_count
error_message

DEPLOYMENT_EVENTS:

id
deployment_id
raw_execution
raw_finished
raw_message
parsed_progress
event_timestamp
received_at

AUDIT_LOGS:

id
user_id
operation
resource_type
resource_id
timestamp
details


Add required:

- Primary keys.
- Foreign keys.
- Unique constraints.
- Appropriate indexes.
- Transaction handling.
- Database migrations.

Enforce uniqueness of controller IDs within a tenant.

Prevent race conditions when multiple requests interact
with the same deployment.

Use Alembic for database migrations.

Do not use database create_all() as the only production
schema-management mechanism.

====================================================================
24. WEB DASHBOARD
====================================================================

Develop a complete responsive dashboard.

The design can take inspiration from Eclipse hawkBit,
but should use original implementation and styling.

Required pages:

1. Dashboard Overview
2. Target Management
3. Firmware Upload
4. Software Modules
5. Distributions
6. Deployment Management
7. Deployment Details
8. Update History
9. System Configuration
10. User Management
11. Audit Logs

DASHBOARD OVERVIEW:

Display:

Total Targets
Online Targets
Offline Targets
Total Firmware Versions
Active Deployments
Successful Installations
Failed Installations
Pending Deployments

TARGET MANAGEMENT PAGE:

Display:

Controller ID
Display Name
Hardware Model
Hardware Revision
Last Seen
Online Status
Assigned Firmware
Installation Status
Available Actions

FIRMWARE UPLOAD PAGE:

Allow:

- Selecting .raucb.
- Uploading firmware.
- Showing upload progress.
- Entering version metadata.
- Viewing checksum.
- Viewing artifact size.
- Creating software modules.

DISTRIBUTIONS PAGE:

Allow:

- Creating releases.
- Assigning modules.
- Viewing artifact associations.
- Editing distribution metadata.
- Managing distribution versions.

DEPLOYMENT PAGE:

Allow:

- Selecting a target.
- Selecting a distribution.
- Selecting deployment mode.
- Assigning firmware.
- Viewing deployment status.

DEPLOYMENT DETAILS PAGE:

Display:

Target
Distribution
Firmware Version
Assignment Time
Download Status
Installation Status
Progress Percentage
Latest RAUC Detail
Last Feedback
Error Details
Deployment Timeline

Use a live progress interface.

Use WebSocket or Server-Sent Events between the
Python backend and the browser if useful.

IMPORTANT:

Dashboard push updates are separate from target DDI polling.

The embedded target does not need WebSocket support.

The target must continue using its existing HTTP DDI API.

====================================================================
25. HTTP AND HTTPS
====================================================================

Support both communication protocols.

LOCAL DEVELOPMENT:

http://192.168.11.161:8080

PRODUCTION:

https://ota.example.com

The hostname is only an example.

Do not hardcode it.

Provide configurable settings such as:

PUBLIC_BASE_URL
HTTP_PORT
HTTPS_ENABLED
DATABASE_URL
ARTIFACT_STORAGE_PATH
POLLING_INTERVAL_SECONDS
OFFLINE_THRESHOLD_SECONDS

For production:

Use TLS termination through Nginx, Caddy,
or an equivalent reverse proxy.

Require trusted certificates.

Ensure the generated DDI artifact URLs use HTTPS
when the target connects over HTTPS.

Support reverse-proxy deployments.

Validate forwarded host/protocol headers against
trusted proxy configuration.

Do not blindly trust arbitrary X-Forwarded-* headers.

Do not expose authentication tokens over unencrypted HTTP
in production.

Preserve HTTP support for controlled local testing.

Provide instructions for switching target configuration:

HTTP:

ssl = false

HTTPS:

ssl = true

ssl_verify = true

Production HTTPS must support valid certificate verification.

Do not require ssl_verify=false in production.

====================================================================
26. APPLICATION CONFIGURATION
====================================================================

Implement centralized configuration.

Example environment variables:

APP_NAME=Python OTA Server

APP_ENV=development

DATABASE_URL=sqlite:///./ota.db

ARTIFACT_STORAGE_PATH=./storage/artifacts

PUBLIC_BASE_URL=http://192.168.11.161:8080

POLLING_INTERVAL_SECONDS=60

OFFLINE_THRESHOLD_SECONDS=180

MAX_UPLOAD_SIZE_MB=2048

LOG_LEVEL=INFO

DEFAULT_TENANT=DEFAULT

Separate secrets from normal settings.

Use .env.example.

Do not commit actual secrets.

Support configuration validation during application startup.

Fail clearly when required production settings are missing.

====================================================================
27. LOGGING AND MONITORING
====================================================================

Implement structured backend logging.

Log:

- Application startup.
- Target polling.
- Authentication failures.
- ConfigData requests.
- Deployment assignment.
- Deployment discovery.
- Artifact download start.
- Artifact download completion.
- Installation progress feedback.
- Installation success.
- Installation failure.
- Retry operations.
- Administrative actions.

Never log:

- Raw TargetTokens.
- Admin passwords.
- Session secrets.
- Private keys.

Maintain an audit trail for security-sensitive actions.

Provide basic operational endpoints such as:

GET /health

GET /ready

Use appropriate health checks for database and storage.

Add request IDs or correlation IDs for troubleshooting.

====================================================================
28. TESTING REQUIREMENTS
====================================================================

Create automated tests.

Use pytest.

Test categories:

POSITIVE TESTS:

- Valid target authentication.
- Successful target polling.
- Valid ConfigData upload.
- Successful firmware upload.
- Successful deployment assignment.
- Valid deployment metadata.
- Successful artifact download.
- Correct checksum metadata.
- Successful installation feedback.
- Final installation success state.

NEGATIVE TESTS:

- Invalid token.
- Missing token.
- Unknown controller ID.
- Invalid tenant.
- Wrong target accessing deployment.
- Wrong target accessing artifact.
- Missing firmware.
- Invalid JSON.
- Invalid action ID.
- Malformed feedback.
- Invalid Range header.
- Interrupted download.
- Unsupported deployment mode.
- Conflicting assignments.
- Duplicate final feedback.

BOUNDARY TESTS:

- Small firmware file.
- Large firmware file.
- Empty upload.
- Duplicate upload.
- Maximum file size.
- Maximum target count for configured test environment.
- Multiple concurrent downloads.
- Polling while server is restarting.

SECURITY TESTS:

- Authentication bypass attempts.
- Path traversal.
- Cross-target access.
- Cross-tenant access.
- Token revocation.
- Unauthorized firmware upload.
- Invalid administrator permissions.
- Malicious filenames.

STATE MACHINE TESTS:

- Pending to proceeding.
- Proceeding to success.
- Proceeding to failure.
- Duplicate feedback.
- Out-of-order feedback.
- Repeated polling.
- Server restart during update.
- Cancel/retry race conditions.

COMPATIBILITY TESTS:

Validate the Python server against the actual
rauc-hawkbit-updater v1.3 client.

Capture requests and verify expected responses.

Do not mark compatibility tests as passed unless they have
actually been executed.

====================================================================
29. REAL PHYTEC HARDWARE VALIDATION
====================================================================

Test against the existing PHYTEC gateway.

Initial testing must be non-destructive.

TEST 1:

Configure target to reach the Python server.

TEST 2:

Start the Python backend.

TEST 3:

Start/restart rauc-hawkbit-updater.

TEST 4:

Verify target authentication.

TEST 5:

Verify periodic polling.

TEST 6:

Verify ConfigData upload.

TEST 7:

Verify target appears online in dashboard.

TEST 8:

Verify a no-deployment response does not trigger installation.

TEST 9:

Upload a valid signed .raucb bundle.

TEST 10:

Create a deployment assignment.

TEST 11:

Verify the target receives deployment metadata.

TEST 12:

Verify artifact download.

TEST 13:

Verify checksum validation.

TEST 14:

Verify installation progress feedback.

TEST 15:

Verify RAUC installation success.

TEST 16:

Inspect RAUC slot status.

TEST 17:

Reboot only after explicit operator approval.

TEST 18:

Verify expected boot slot and mark-good behavior.

TEST 19:

Verify dashboard status accurately reflects the evidence.

IMPORTANT SAFETY REQUIREMENT:

Do not automatically deploy firmware during application startup.

Do not trigger hardware updates simply because test data exists.

Do not reboot hardware automatically during early testing.

Use a dedicated lab target.

Before any firmware installation, confirm:

- Bundle compatibility.
- Bundle signature.
- Correct target identity.
- Intended firmware version.
- Available recovery path.
- Operator approval.

Preserve the ability to revert to the existing hawkBit server
during compatibility testing.

====================================================================
30. PROJECT DIRECTORY STRUCTURE
====================================================================

Create a clean repository.

Suggested structure:

python-ota-server/
|
+-- backend/
|   |
|   +-- app/
|   |   |
|   |   +-- main.py
|   |   +-- core/
|   |   |   +-- config.py
|   |   |   +-- security.py
|   |   |   +-- logging.py
|   |   |
|   |   +-- database/
|   |   |   +-- session.py
|   |   |   +-- models/
|   |   |   +-- migrations/
|   |   |
|   |   +-- ddi/
|   |   |   +-- controller.py
|   |   |   +-- config_data.py
|   |   |   +-- deployment.py
|   |   |   +-- artifact.py
|   |   |   +-- feedback.py
|   |   |   +-- schemas.py
|   |   |
|   |   +-- management/
|   |   |   +-- auth.py
|   |   |   +-- targets.py
|   |   |   +-- firmware.py
|   |   |   +-- modules.py
|   |   |   +-- distributions.py
|   |   |   +-- deployments.py
|   |   |   +-- dashboard.py
|   |   |
|   |   +-- services/
|   |   |   +-- target_auth.py
|   |   |   +-- deployment_engine.py
|   |   |   +-- artifact_storage.py
|   |   |   +-- checksum.py
|   |   |   +-- feedback_processor.py
|   |   |   +-- status_monitor.py
|   |   |
|   |   +-- schemas/
|   |   |
|   |   +-- tests/
|   |
|   +-- alembic.ini
|   +-- pyproject.toml
|   +-- .env.example
|
+-- frontend/
|   |
|   +-- src/
|   |   +-- components/
|   |   +-- pages/
|   |   +-- services/
|   |   +-- hooks/
|   |   +-- types/
|   |
|   +-- package.json
|
+-- storage/
|   +-- artifacts/
|   +-- temporary/
|
+-- deployment/
|   +-- nginx/
|   +-- docker/
|
+-- docs/
|   +-- architecture.md
|   +-- ddi-compatibility.md
|   +-- api-reference.md
|   +-- database-schema.md
|   +-- deployment-guide.md
|   +-- hardware-testing.md
|   +-- security.md
|
+-- docker-compose.yml
+-- README.md


You may improve this structure if a different organization
provides better maintainability.

Keep device protocol code isolated from management APIs.

Do not mix dashboard-specific logic with DDI handlers.

====================================================================
31. DOCUMENTATION REQUIREMENTS
====================================================================

Generate complete documentation.

README.md:

- Project overview.
- Dependencies.
- Development setup.
- Running backend.
- Running frontend.
- Database migration.
- Creating admin account.
- Initial configuration.
- Testing endpoints.

ARCHITECTURE:

Explain:

- Python server.
- Target updater.
- REST communication.
- DDI polling.
- Target authentication.
- Firmware download.
- Feedback.
- RAUC installation.
- A/B update.
- Boot validation.

DDI COMPATIBILITY DOCUMENT:

For each DDI endpoint document:

- HTTP method.
- URL.
- Request headers.
- Request body.
- Response body.
- HTTP status codes.
- Authentication.
- Implementation status.
- Compatibility verification status.

HARDWARE TEST GUIDE:

Provide safe procedures for testing on the PHYTEC gateway.

SECURITY GUIDE:

Explain:

- HTTP vs HTTPS.
- TargetToken handling.
- Administrator authentication.
- Artifact authorization.
- RAUC signature validation.
- Certificate provisioning.
- Token rotation.

====================================================================
32. IMPLEMENTATION PHASES
====================================================================

Do not attempt to build the entire application as one
unverified code generation step.

Implement it in phases.

PHASE 1: PROJECT FOUNDATION

- Initialize backend.
- Configure FastAPI.
- Configure database.
- Add migrations.
- Add settings.
- Add logging.
- Add health endpoints.
- Add basic tests.

PHASE 2: DEVICE DDI COMPATIBILITY

- TargetToken authentication.
- Controller polling.
- ConfigData handling.
- DDI response schemas.
- Compatibility tests.
- Real target polling validation.

PHASE 3: FIRMWARE AND DEPLOYMENTS

- Artifact upload.
- SHA-256 calculation.
- Software modules.
- Distributions.
- Deployment assignments.
- DeploymentBase endpoint.
- Artifact download.
- DDI feedback.
- State machine.

PHASE 4: DASHBOARD

- Authentication UI.
- Target management.
- Firmware upload.
- Distribution management.
- Deployment management.
- Progress monitoring.
- History.

PHASE 5: PRODUCTION HARDENING

- HTTPS.
- PostgreSQL.
- Reverse proxy.
- Security tests.
- Concurrent downloads.
- Retry recovery.
- Audit logs.
- Database migrations.
- Deployment packaging.

PHASE 6: HARDWARE VALIDATION

- Real updater polling.
- Real deployment.
- Real bundle download.
- Real RAUC installation.
- A/B slot inspection.
- Controlled reboot.
- Status verification.

At the end of every phase:

1. Summarize completed work.
2. Show modified files.
3. Run available tests.
4. Report failures honestly.
5. Identify missing dependencies.
6. Explain manual verification steps.
7. Identify any unverified DDI behavior.
8. Do not claim a phase is complete if its tests failed.

====================================================================
33. IMPORTANT DEVELOPMENT RULES
====================================================================

RULE 1:

Never replace the existing RAUC target updater.

RULE 2:

Never modify target-side RAUC partitions from the server.

RULE 3:

Use the existing hawkBit DDI v1 protocol.

RULE 4:

Do not create fake protocol responses to bypass compatibility
requirements.

RULE 5:

Keep HTTP and HTTPS support configurable.

RULE 6:

Do not hardcode local IP addresses or credentials.

RULE 7:

Keep target authentication and administrator authentication
separate.

RULE 8:

Do not consider installation success the same as confirmed
successful reboot.

RULE 9:

Protect firmware artifacts against unauthorized access.

RULE 10:

Make large file handling memory efficient.

RULE 11:

Preserve all meaningful feedback and deployment events.

RULE 12:

Support multiple targets and concurrent operations safely.

RULE 13:

Use clean modular Python code.

RULE 14:

Add database migrations and automated tests.

RULE 15:

Use the attached real communication logs as protocol evidence.

RULE 16:

Never expose real TargetTokens in source code, examples, or logs.

RULE 17:

Never initiate a real firmware installation or reboot without
explicit approval during development.

RULE 18:

Document unsupported features instead of silently simulating them.

RULE 19:

Preserve backward compatibility with the existing updater.

RULE 20:

Keep the code suitable for future production deployment.

====================================================================
34. REQUIRED ACCEPTANCE CRITERIA
====================================================================

The project can be considered operationally successful when:

1. The Python OTA server starts successfully.

2. The dashboard is accessible.

3. Targets can be created with unique credentials.

4. The real rauc-hawkbit-updater v1.3 authenticates.

5. The real target polls the Python server successfully.

6. The target sends configuration attributes successfully.

7. The dashboard displays the target and its last-seen status.

8. A valid signed RAUC bundle can be uploaded.

9. Firmware metadata and SHA-256 are stored correctly.

10. A distribution can be created.

11. A distribution can be assigned to a target.

12. The target retrieves a compatible DDI deployment response.

13. The target downloads the assigned RAUC bundle successfully.

14. Artifact checksum verification succeeds.

15. The target passes the bundle to RAUC.

16. RAUC installs the bundle successfully.

17. RAUC progress is reported to the Python server.

18. Final DDI installation feedback is recorded correctly.

19. The dashboard displays actual installation results.

20. A controlled reboot can be performed and separately
    validated using RAUC status.

21. Multiple targets can be managed independently.

22. Authentication and authorization tests pass.

23. The server supports both HTTP and HTTPS deployment modes.

24. The project includes documentation and reproducible tests.

Do not mark hardware-dependent acceptance criteria as passed
unless verified on actual hardware.

====================================================================
35. FIRST TASK FOR CODEX
====================================================================

Start by inspecting the existing repository and any supplied
protocol-capture files.

If no application exists, initialize the project.

First create:

1. Architecture overview.
2. Database entity design.
3. DDI endpoint compatibility matrix.
4. Implementation plan.
5. Phase 1 backend foundation.

After Phase 1, implement the smallest functional DDI server.

The first target-side test must only perform:

- Authentication.
- Controller polling.
- ConfigData handling.

Do not assign firmware yet.

Demonstrate that the existing rauc-hawkbit-updater v1.3 can
communicate with the Python server.

Once verified, proceed to deployment and artifact download.

Generate actual working code, tests, configuration, and
documentation.

Do not stop after providing pseudocode or design descriptions.

The final objective is a real Python OTA management platform
that can replace hawkBit while preserving the existing
PHYTEC + rauc-hawkbit-updater + RAUC A/B architecture.

BEGIN IMPLEMENTATION.
