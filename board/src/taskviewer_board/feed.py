"""Background thread: subscribe to the App's state stream; start the App if it's down."""

import json
import socket
import threading
import time

import taskviewer_protocol as p
from taskviewer_client import start_app, state_dir

RETRY = 2.0


def stream(on_snapshot, on_down, stop: threading.Event):
    """Blocking loop: on_snapshot(SnapshotView) per push, on_down() when the App is unreachable."""
    started = False
    while not stop.is_set():
        try:
            port = int((state_dir() / "port").read_text())
            with socket.create_connection(("127.0.0.1", port), timeout=1.0) as sock:
                sock.settimeout(None)
                sock.sendall(json.dumps({"id": 1, "op": "subscribe", "topics": ["state"]}).encode() + b"\n")
                started = False
                for line in sock.makefile("rb"):
                    if b'"event"' not in line:
                        continue  # the subscribe reply
                    ev = p.decode_event(line)
                    if isinstance(ev, p.StateEvent):
                        on_snapshot(ev.snapshot)
        except (OSError, ValueError):
            pass
        on_down()
        if not started:
            start_app()  # App guards against double start
            started = True
        stop.wait(RETRY)


def run_in_thread(on_snapshot, on_down) -> threading.Event:
    stop = threading.Event()
    threading.Thread(target=stream, args=(on_snapshot, on_down, stop), daemon=True).start()
    return stop
