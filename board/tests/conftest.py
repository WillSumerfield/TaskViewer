import psutil
import pytest


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    d = tmp_path / "state"
    monkeypatch.setenv("TASKVIEWER_STATE_DIR", str(d))
    yield d
    for proc in psutil.process_iter(["cmdline"]):
        if str(d) in " ".join(proc.info["cmdline"] or []):
            proc.kill()

