"""Subscribe to the App's push stream; start the App if it's down. Stdlib-only (the Glance imports it)."""

import json
import socket
import threading

from taskviewer_client import start_app, state_dir

RETRY = 2.0


def events(topics: list[str], on_event, on_down, stop: threading.Event, start: bool = True):
    """Blocking loop: on_event(raw line) per push, on_down() when the App is unreachable.

    start=False never launches an App (it runs elsewhere, e.g. in WSL).
    """
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
        if start and not started:
            start_app()  # App guards against double start
            started = True
        stop.wait(RETRY)


def stream(on_snapshot, on_down, stop: threading.Event, on_glance=None, start: bool = True):
    """events() on the state topic (+ glance if on_glance), decoded; on_glance gets a {live, awaiting, blocked} dict."""
    import msgspec

    import taskviewer_protocol as p

    def on_event(line):
        ev = p.decode_event(line)
        if isinstance(ev, p.StateEvent):
            on_snapshot(ev.snapshot)
        elif isinstance(ev, p.GlanceEvent) and on_glance:
            on_glance(msgspec.structs.asdict(ev.glance))

    events(["state", "glance"] if on_glance else ["state"], on_event, on_down, stop, start)


def run_in_thread(on_snapshot, on_down, on_glance=None, start: bool = True) -> threading.Event:
    stop = threading.Event()
    threading.Thread(target=stream, args=(on_snapshot, on_down, stop, on_glance, start), daemon=True).start()
    return stop
