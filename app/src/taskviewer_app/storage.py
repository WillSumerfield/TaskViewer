"""Saves State to disk: trees/<id>.json, sessions.json (+ next id). Atomic writes."""

import os
import sys
from pathlib import Path

import msgspec

from .state import Session, State, Tree


class SessionsFile(msgspec.Struct):
    next_id: int
    sessions: list[Session]


def default_dir() -> Path:
    if sys.platform == "win32":
        return Path(os.environ["LOCALAPPDATA"]) / "taskviewer"
    return Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "taskviewer"


def _write(path: Path, data: bytes):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


class Storage:
    def __init__(self, root: Path):
        self.root = root
        self.trees_dir = root / "trees"
        self.trees_dir.mkdir(parents=True, exist_ok=True)

    def load(self, state: State):
        trees = [msgspec.json.decode(f.read_bytes(), type=Tree) for f in self.trees_dir.glob("*.json")]
        sf = self.root / "sessions.json"
        s = msgspec.json.decode(sf.read_bytes(), type=SessionsFile) if sf.exists() else SessionsFile(1, [])
        state.load(trees, s.sessions, s.next_id)

    def flush(self, state: State):
        for tid in state.dirty_trees:
            _write(self.trees_dir / f"{tid}.json", msgspec.json.encode(state.trees[tid]))
        for tid in state.deleted_trees:
            (self.trees_dir / f"{tid}.json").unlink(missing_ok=True)
        if state.sessions_dirty:
            _write(self.root / "sessions.json",
                   msgspec.json.encode(SessionsFile(state.next_id, list(state.sessions.values()))))
        state.dirty_trees.clear()
        state.deleted_trees.clear()
        state.sessions_dirty = False

    def write_port(self, port: int):
        _write(self.root / "port", str(port).encode())

    def read_port(self) -> int | None:
        f = self.root / "port"
        return int(f.read_text()) if f.exists() else None
