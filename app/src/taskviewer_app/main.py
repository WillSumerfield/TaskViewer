"""Entry point: run the App headless (Board/Glance attach in later phases)."""

import argparse
import asyncio
import socket
from pathlib import Path

from .server import Server
from .state import State
from .storage import Storage, default_dir


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
    if already_running(storage):
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
