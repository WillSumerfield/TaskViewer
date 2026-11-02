"""Merge several Apps (e.g. one per WSL distro) into one Board feed. Qt-free."""

import re
import threading

import msgspec

import taskviewer_protocol as p


def label(state_dir: str) -> str:
    """Distro name for a \\\\wsl.localhost\\<distro>\\... (or \\\\wsl$\\) path, else the path itself."""
    m = re.match(r"^[\\/]{2}wsl(?:\.localhost|\$)[\\/]([^\\/]+)", state_dir, re.IGNORECASE)
    return m.group(1) if m else state_dir


def tag(snap: p.SnapshotView, lab: str) -> p.SnapshotView:
    """Prefix ids with the App's label and add it to Project names, so Apps never mix."""
    r = msgspec.structs.replace
    pre = lambda i: f"{lab}/{i}"
    proj = lambda pr: f"{pr} · {lab}"
    return p.SnapshotView(
        trees=[r(t, id=pre(t.id), project=proj(t.project), sessions=[pre(s) for s in t.sessions])
               for t in snap.trees],
        sessions=[r(s, id=pre(s.id), project=proj(s.project), tree_id=s.tree_id and pre(s.tree_id))
                  for s in snap.sessions],
    )


class Merger:
    """Latest snapshot and Glance per App, passed on merged; on_down only once every App is down.

    One App passes through untouched. Callbacks run under the lock so merged views stay in order.
    """

    def __init__(self, labels: list[str], on_snapshot, on_down, on_glance=None):
        self.labels = labels
        self.on_snapshot, self.on_down, self.on_glance = on_snapshot, on_down, on_glance
        n = len(labels)
        self.snaps: list[p.SnapshotView | None] = [None] * n
        self.glances: list[dict | None] = [None] * n
        self.up = [False] * n
        self.lock = threading.Lock()

    def snapshot(self, i: int, snap: p.SnapshotView):
        with self.lock:
            self.snaps[i], self.up[i] = snap, True
            self.on_snapshot(self._snap())

    def glance(self, i: int, g: dict):
        with self.lock:
            self.glances[i], self.up[i] = g, True
            if self.on_glance:
                self.on_glance(self._glance())

    def down(self, i: int):
        with self.lock:
            was = self.up[i]
            self.up[i], self.snaps[i], self.glances[i] = False, None, None
            if not any(self.up):
                self.on_down()
            elif was:
                self.on_snapshot(self._snap())
                if self.on_glance:
                    self.on_glance(self._glance())

    def _snap(self) -> p.SnapshotView:
        if len(self.labels) == 1:
            return self.snaps[0] or p.SnapshotView(trees=[], sessions=[])
        parts = [tag(s, lab) for s, lab in zip(self.snaps, self.labels) if s is not None]
        return p.SnapshotView(trees=[t for s in parts for t in s.trees],
                              sessions=[x for s in parts for x in s.sessions])

    def _glance(self) -> dict:
        gs = [g for g in self.glances if g is not None]
        out = {k: sum(g[k] for g in gs) for k in ("live", "awaiting", "blocked")}
        out["down"] = [lab for lab, u in zip(self.labels, self.up) if not u]
        return out
