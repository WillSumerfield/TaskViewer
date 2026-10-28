"""Subscribe to the App's push stream; start the App if it's down. Stdlib-only (the Glance imports it)."""

import json
import socket
import threading

from taskviewer_client import start_app, state_dir

RETRY = 2.0


def events(topics: list[str], on_event, on_down, stop: threading.Event):
    """Blocking loop: on_event(raw line) per push, on_down() when the App is unreachable."""
    started = False
    while not stop.is_set():
        try:
            port = int((state_dir() / "port").read_text())
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
        if not started:
            start_app()  # App guards against double start
            started = True
        stop.wait(RETRY)


def stream(on_snapshot, on_down, stop: threading.Event):
    """events() on the state topic, decoded to SnapshotView."""
    import taskviewer_protocol as p

    def on_event(line):
        ev = p.decode_event(line)
        if isinstance(ev, p.StateEvent):
            on_snapshot(ev.snapshot)

    events(["state"], on_event, on_down, stop)


def run_in_thread(on_snapshot, on_down) -> threading.Event:
    stop = threading.Event()
    threading.Thread(target=stream, args=(on_snapshot, on_down, stop), daemon=True).start()
    return stop
