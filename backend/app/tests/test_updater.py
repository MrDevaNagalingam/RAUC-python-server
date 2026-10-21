"""Optional real C client test. No device or RAUC simulator, bundle, installation or reboot."""

import os
import socket
import subprocess
import threading
import time

import pytest
import uvicorn

from app.database.models import Target
from app.main import create_app
from app.services.targets import describe


@pytest.mark.updater
def test_actual_v13_updater_poll_and_config(configured, app, device, tmp_path):
    binary = os.environ.get("UPDATER_V13_BIN")
    if not binary:
        pytest.skip("Set UPDATER_V13_BIN to an actual unmodified v1.3 executable")
    assert subprocess.check_output([binary, "--version"], text=True).strip() == "Version 1.3"
    # Bind before starting the thread so the port cannot be claimed by another process.
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    settings = configured[0].model_copy(update={"public_base_url": f"http://127.0.0.1:{port}"})
    server = uvicorn.Server(
        uvicorn.Config(
            create_app(settings), log_level="error", access_log=False, proxy_headers=False
        )
    )
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert server.started
        config = tmp_path / "updater.conf"
        config.touch(mode=0o600)
        config.write_text(f"""[client]
hawkbit_server = 127.0.0.1:{port}
ssl = false
ssl_verify = false
tenant_id = DEFAULT
target_name = test-target
auth_token = {device["token"]}
bundle_download_location = {tmp_path}/never-downloaded.raucb
post_update_reboot = false
connect_timeout = 2
timeout = 5
retry_wait = 1
log_level = message
[device]
model = T1
hw_revision = 2
mac_address = ff:ff:ff:ff:ff:ff
""")
        for _ in range(2):
            process = subprocess.run(
                [binary, "-r", "-c", str(config)], capture_output=True, text=True, timeout=15
            )
            assert process.returncode == 0, process.stderr
            assert "No new software." in process.stdout
            assert device["token"] not in process.stdout + process.stderr
        with app.state.sessions() as session:
            target = session.get(Target, device["id"])
            assert target.last_poll_at is not None
            assert target.config_requested is False
            assert describe(session, target, 180)["attributes"] == {
                "model": "T1",
                "hw_revision": "2",
                "mac_address": "ff:ff:ff:ff:ff:ff",
            }
        assert not (tmp_path / "never-downloaded.raucb").exists()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        assert not thread.is_alive()
