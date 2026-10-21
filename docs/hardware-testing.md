# PHYTEC hardware validation

The user supplied successful initial communication evidence on 2026-10-21:
`test-target` Online, authenticated activity timestamps and expected model T1,
hw_revision 2 and configured MAC attribute. That evidence is retained as the initial
poll/config milestone. No raw gateway capture, signed-bundle installation, slot
inspection or reboot was performed by this implementation turn.

The host now contains real firmware assignment endpoints. Startup/upload still
never assigns firmware, but a deliberate Forced assignment can trigger installation
on the next poll. Keep firmware operations separate from a communication-only test.

## Preserve and recheck communication

1. Keep a secure backup of the existing target updater configuration and its prior
   hawkBit address. Do not replace the updater executable, RAUC, D-Bus, Barebox,
   partition layout, handlers, keyring or slot-marking service.
2. Stop the host's old server, back up its DB, migrate and create an administrator
   using README. Keep the same reachable public origin, tenant, controller ID
   and working token. Start the upgraded host server and confirm health/readiness.
3. Before restarting the updater for a communication-only test, verify in the
   dashboard that this lab target has no active deployment. Existing metadata or
   firmware uploads alone should not create one. Retain post_update_reboot=false.
4. Confirm the target continues polling, reported attributes remain and the
   dashboard displays Online. Observe at least three actual polling cycles; inspect
   target service logs and request IDs. Trigger `ota request-config test-target`
   locally if the ConfigData exchange needs to be repeated.
5. Optionally stop the updater beyond OFFLINE_THRESHOLD_SECONDS, confirm inferred
   Offline and restart it. This is a polling estimate, not a persistent connection.

Operator-run target log commands:

```bash
systemctl status rauc-hawkbit-updater
journalctl -u rauc-hawkbit-updater --since '5 minutes ago'
```

Only run the updater one-shot after verifying both the configured server and absence
of unintended assignments. Reconnecting to the previous hawkBit server can encounter
that server's queued actions; this platform cannot clear or manage them.

## Firmware preparation and Download Only

Use a dedicated lab device with a documented recovery path. Obtain a signed RAUC
bundle intended for the exact hardware and version. Independently verify signature
trust, manifest compatibility (`phyboard-segin-imx6ul-7` for the described board),
intended version and recovery access. The server checks only supplied metadata and
checksums; its upload signature status remains NOT_VERIFIED.

Upload the unchanged bundle, create one OS module and a distribution, then inspect
the hashes, size and contents. Verify upload/release creation did not advertise an
action to the target. With explicit operator approval for the transfer, select
Download Only in the assignment review. Confirm the exact target, distribution
version and compatible string and record the approval/recovery note.

The unchanged v1.3 client should fetch metadata, download exact bytes, verify SHA-1
and skip installation because update=skip. The action should become
DOWNLOAD_SUCCEEDED, not INSTALL_SUCCEEDED. Inspect raw feedback and target logs.
The host tests verified this path with a synthetic payload; real bundle transfer
and target-specific disk/resume behavior still need lab evidence.

## Forced installation — explicit operator approval required

1. Record the exact lab target/controller, bundle/distribution version, independently
   checked compatible string/signature trust, current RAUC slot status and recovery
   access. Review the target's post_update_reboot setting and keep it false.
2. Obtain approval for the actual installation. Choose Forced only after all checks.
   Re-enter version and compatibility in the dashboard, record evidence in the
   approval note and explicitly confirm. The target may install at its next poll.
3. Follow raw download/hash and RAUC installation progress feedback. Preserve error
   details and timestamps. A terminal failure must not cause automatic reinstallation.
   An intentional retry requires a separate reviewed approval and creates a linked
   new action. Cancel is available only before the target discovers its action.
4. Inspect target RAUC logs and `rauc status`. RAUC selects the inactive slots;
   never assume every update installs rootfs.1 or boot.1. The server does not write
   eMMC, force slot choice or bypass signature checks.
5. Confirm installation evidence. INSTALL_SUCCEEDED reflects the client's report;
   boot confirmation and current running version remain unknown.

## Controlled reboot and recovery

Obtain **separate explicit approval before reboot**. After the controlled reboot,
inspect the actual booted slot, expected firmware and mark-good behavior on the
target. Compare with the recorded pre-install state. Investigate fallback/rollback
through target/bootloader evidence. Do not infer a good boot or absence of rollback
from a prior successful installation response. No optional health reporter is
fabricated or required for ordinary DDI operation.

To return to the existing hawkBit server, stop the updater, review that server's
queued assignments, restore the private original configuration and start the updater.
Protect captures/config backups as secrets; HTTP traces contain raw TargetTokens.
Sanitize before sharing and rotate any exposed token. Never commit raw traces.
