"""Stdlib-only App client: find the port, send one request, read the reply."""

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path


def state_dir() -> Path:
    if d := os.environ.get("TASKVIEWER_STATE_DIR"):
        return Path(d)
    if sys.platform == "win32":
        return Path(os.environ["LOCALAPPDATA"]) / "taskviewer"
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "taskviewer"


class AppDown(Exception):
    pass


def call(msg: dict, timeout: float = 2.0) -> dict:
    """Send one request; returns the reply dict. Raises AppDown if no App answers."""
    try:
        port = int((state_dir() / "port").read_text())
        with socket.create_connection(("127.0.0.1", port), timeout=timeout) as sock:
            sock.sendall(json.dumps({"id": 1, **msg}).encode() + b"\n")
            line = sock.makefile("rb").readline()
    except (OSError, ValueError) as e:
        raise AppDown(str(e))
    if not line:
        raise AppDown("no reply")
    return json.loads(line)


def start_app():
    """Launch taskviewer-app fully detached from this process."""
    cmd = ["taskviewer-app", "--state-dir", str(state_dir())]
    kw: dict = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if sys.platform == "win32":
        kw["creationflags"] = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    subprocess.Popen(cmd, **kw)


def call_or_start(msg: dict, wait: float = 3.0) -> dict:
    """call(), starting the App first if it isn't running."""
    try:
        return call(msg)
    except AppDown:
        pass
    start_app()
    deadline = time.monotonic() + wait
    while True:
        time.sleep(0.05)
        try:
            return call(msg)
        except AppDown:
            if time.monotonic() > deadline:
                raise
