import os
import subprocess
import sys
import time

import psutil
import pytest

APP = [sys.executable, "-c", "from taskviewer_app.main import main; main()"]


def wait_port(d, secs=5.0):
    deadline = time.monotonic() + secs
    while not (d / "port").exists():
        assert time.monotonic() < deadline, "App did not start"
        time.sleep(0.02)


def kill_apps(d):
    for proc in psutil.process_iter(["cmdline"]):
        if str(d) in " ".join(proc.info["cmdline"] or []):
            proc.kill()


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    d = tmp_path / "state"
    monkeypatch.setenv("TASKVIEWER_STATE_DIR", str(d))
    yield d
    kill_apps(d)


@pytest.fixture
def app(state_dir):
    """A running App on the temp state dir."""
    subprocess.Popen([*APP, "--state-dir", str(state_dir)], stdout=subprocess.DEVNULL)
    wait_port(state_dir)
    return state_dir
