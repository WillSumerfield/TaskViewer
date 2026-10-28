"""Entry point: run the App headless (Board/Glance attach in later phases)."""

import argparse
import asyncio
import os
import socket
import sys
from pathlib import Path

from .server import Server
from .state import State
from .storage import Storage, default_dir


def lock(root: Path):
    """Exclusive lock on <root>/app.lock, held for the App's life; None if another App holds it.

    Login starts the Board, Glances and hooks at once; each may launch an App before any binds a port.
    """
    root.mkdir(parents=True, exist_ok=True)
    f = open(root / "app.lock", "a+b")
    try:
        if sys.platform == "win32":
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


def already_running(storage: Storage) -> bool:
    port = storage.read_port()
    if port is None:
        return False
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.5).close()
        return True
    except OSError:
        return False


async def run(root: Path):
    storage = Storage(root)
    held = lock(root)
    if held is None or already_running(storage):
        print("taskviewer-app already running")
        return
    state = State()
    storage.load(state)
    server = Server(state, storage)
    if state.sweep(server.alive):
        storage.flush(state)
    port = await server.start()
    print(f"taskviewer-app listening on 127.0.0.1:{port}, state in {root}", flush=True)
    await asyncio.Event().wait()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--state-dir", type=Path, default=default_dir())
    args = ap.parse_args()
    try:
        asyncio.run(run(args.state_dir))
    except KeyboardInterrupt:
        pass
