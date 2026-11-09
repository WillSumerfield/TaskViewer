"""Subscribe to the App's push stream; start the App if it's down. Stdlib-only (the Glance imports it)."""

import json
import re
import socket
import subprocess
import threading

from taskviewer_client import start_app, state_dir

RETRY = 2.0


def wsl_distro(path: str) -> str | None:
    """Distro name for a \\\\wsl.localhost\\<distro>\\... (or \\\\wsl$\\) path, else None."""
    m = re.match(r"^[\\/]{2}wsl(?:\.localhost|\$)[\\/]([^\\/]+)", path, re.IGNORECASE)
    return m.group(1) if m else None


def parse_running(out: bytes) -> set[str]:
    """Lowercased names from `wsl.exe --list --running --quiet` (UTF-16 output)."""
    return {n.strip().lower() for n in out.decode("utf-16-le", "ignore").replace("\0", "").splitlines() if n.strip()}


def distro_running(distro: str) -> bool:
    """Touching \\\\wsl.localhost\\<distro> boots a stopped distro (and the WSL VM), so ask wsl.exe first."""
    try:
        out = subprocess.run(["wsl.exe", "--list", "--running", "--quiet"], capture_output=True, timeout=5,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False
    return distro.lower() in parse_running(out)


def events(topics: list[str], on_event, on_down, stop: threading.Event, start: bool = True, sdir=None):
    """Blocking loop: on_event(raw line) per push, on_down() when the App is unreachable.

    start=False never launches an App (it runs elsewhere, e.g. in WSL). sdir: that App's state dir.
    """
    started = False
    distro = sdir and wsl_distro(str(sdir))
    while not stop.is_set():
        try:
            if distro and not distro_running(distro):
                raise OSError(f"{distro} not running")  # don't read its port file: that would boot it
            port = int(((sdir or state_dir()) / "port").read_text())
            with socket.create_connection(("127.0.0.1", port), timeout=1.0) as sock:
                sock.settimeout(None)
                sock.sendall(json.dumps({"id": 1, "op": "subscribe", "topics": topics}).encode() + b"\n")
                started = False
                for line in sock.makefile("rb"):
                    if b'"event"' in line:  # skip the subscribe reply
                        on_event(line)
        except (OSError, ValueError):
            pass
        if stop.is_set():
            return
        on_down()
        if start and not started:
            start_app()  # App guards against double start
            started = True
        stop.wait(RETRY)


def stream(on_snapshot, on_down, stop: threading.Event, on_glance=None, start: bool = True, sdir=None):
    """events() on the state topic (+ glance if on_glance), decoded; on_glance gets a {live, awaiting, blocked} dict."""
    import msgspec

    import taskviewer_protocol as p

    def on_event(line):
        ev = p.decode_event(line)
        if isinstance(ev, p.StateEvent):
            on_snapshot(ev.snapshot)
        elif isinstance(ev, p.GlanceEvent) and on_glance:
            on_glance(msgspec.structs.asdict(ev.glance))

    events(["state", "glance"] if on_glance else ["state"], on_event, on_down, stop, start, sdir)


def run_in_thread(on_snapshot, on_down, on_glance=None, start: bool = True, sdir=None) -> threading.Event:
    stop = threading.Event()
    threading.Thread(target=stream, args=(on_snapshot, on_down, stop, on_glance, start, sdir), daemon=True).start()
    return stop
