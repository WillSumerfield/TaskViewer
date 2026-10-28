"""Qt-free Board rules: snapshot -> rows to paint."""

import sys
from dataclasses import dataclass
from pathlib import Path

import taskviewer_protocol as p

STATUS_ICON = {"planned": "○", "active": "●", "done": "✓", "blocked": "⧖", "dropped": "✗"}
# Windows draws ▶ as a colour emoji; ▸ has no emoji form
ACTIVITY_ICON = {"working": "▸" if sys.platform == "win32" else "▶", "idle": "◦", "awaiting": "⚠"}
AWAIT = ACTIVITY_ICON["awaiting"]


@dataclass(frozen=True)
class Row:
    kind: str  # project | task | session | note
    text: str
    icon: str = ""
    indent: int = 0
    tag: str = ""  # right-aligned
    style: str = ""  # status or activity name; "" = plain


def project_names(projects: set[str], home: str | None = None) -> dict[str, str]:
    """Basename, or ~-shortened path when two Projects share a basename."""
    home = home if home is not None else str(Path.home())
    base = {pr: Path(pr).name or pr for pr in projects}
    clash = {b for b in base.values() if list(base.values()).count(b) > 1}

    def short(pr: str) -> str:
        return "~" + pr[len(home):] if pr == home or pr.startswith(home + "/") else pr

    return {pr: short(pr) if b in clash else b for pr, b in base.items()}


def _tasks(t: p.TaskView, depth: int) -> list[Row]:
    rows = [Row("task", t.goal, STATUS_ICON[t.status], depth, style=t.status)]
    for c in t.children:
        rows += _tasks(c, depth + 1)
    return rows


def _session(s: p.SessionView, indent: int, tag: str = "") -> Row:
    return Row("session", s.title or "untitled", ACTIVITY_ICON[s.activity], indent, tag, s.activity)


def layout(snap: p.SnapshotView, collapsed: bool, home: str | None = None) -> list[Row]:
    by_tree: dict[str, list[p.SessionView]] = {}
    for s in snap.sessions:
        by_tree.setdefault(s.tree_id or "", []).append(s)
    loose = by_tree.pop("", [])
    names = project_names({t.project for t in snap.trees} | {s.project for s in loose}, home)

    rows: list[Row] = []
    projects = sorted({t.project for t in snap.trees}, key=lambda pr: names[pr].lower())
    for pr in projects:
        rows.append(Row("project", names[pr]))
        trees = sorted((t for t in snap.trees if t.project == pr), key=lambda t: int(t.id.lstrip("t")))
        for t in trees:
            ss = by_tree.get(t.id, [])
            if any(s.activity == "awaiting" for s in ss):  # ⚠ replaces the status icon, line goes yellow
                rows.append(Row("task", t.root.goal, AWAIT, 0, style="awaiting"))
            else:
                rows.append(Row("task", t.root.goal, STATUS_ICON[t.root.status], 0, style=t.root.status))
            if collapsed:
                continue
            for c in t.root.children:
                rows += _tasks(c, 1)

    if loose:
        rows.append(Row("project", "No tree"))
        if collapsed:
            n = len(loose)
            tag = AWAIT if any(s.activity == "awaiting" for s in loose) else ""
            rows.append(Row("note", f"{n} Session{'s' * (n != 1)}", indent=1, tag=tag))
        else:
            rows += [_session(s, 1, names[s.project]) for s in loose]
    return rows
