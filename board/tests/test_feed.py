import threading
from pathlib import Path

from taskviewer_board import feed


def utf16(s):
    return s.encode("utf-16-le")


def test_wsl_distro():
    assert feed.wsl_distro(r"\\wsl.localhost\Ubuntu-22.04\home\me\.local\state\taskviewer") == "Ubuntu-22.04"
    assert feed.wsl_distro(r"\\wsl$\Ubuntu\home") == "Ubuntu"
    assert feed.wsl_distro("//WSL.localhost/Ubuntu/home") == "Ubuntu"
    assert feed.wsl_distro(r"C:\Users\me\state") is None


def test_parse_running():
    assert feed.parse_running(utf16("Ubuntu-22.04\r\nUbuntu\r\n")) == {"ubuntu-22.04", "ubuntu"}
    assert feed.parse_running(b"") == set()


def test_distro_running(monkeypatch):
    class R:
        stdout = utf16("Ubuntu-22.04\r\n")
    monkeypatch.setattr(feed.subprocess, "run", lambda *a, **k: R)
    assert feed.distro_running("ubuntu-22.04")
    assert not feed.distro_running("Ubuntu")


def test_distro_running_no_wsl(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError
    monkeypatch.setattr(feed.subprocess, "run", boom)
    assert not feed.distro_running("Ubuntu")


def test_events_skips_stopped_distro(monkeypatch):
    """A stopped distro's port file is never read (reading it would boot the distro)."""
    stop, reads, downs = threading.Event(), [], []
    monkeypatch.setattr(feed, "distro_running", lambda d: False)
    monkeypatch.setattr(Path, "read_text", lambda self, *a, **k: reads.append(self) or "0")

    def on_down():
        downs.append(1)
        stop.set()
    feed.events(["state"], None, on_down, stop, start=False, sdir=Path("//wsl.localhost/Ubuntu/state"))
    assert downs and not reads
