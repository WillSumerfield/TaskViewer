"""`taskviewer-glance`: stream the Glance line for a polybar `custom/script` module (tail = true).

Stdlib-only so it starts fast and stays small; one copy runs per bar.
"""

import json
import sys
import threading

from .feed import events

AWAITING, BLOCKED, DIM, LIVE = "#f0d040", "#e5b55c", "#7a8090", "#6fa8dc"
GAP = "%{O3}"  # 3px between icon and count
DOWN = f"%{{F{DIM}}}Tasks: App down%{{F-}}"


def _fg(colour: str | None, text: str) -> str:
    return f"%{{F{colour}}}{text}%{{F-}}" if colour else text


def colour(g: dict) -> str | None:
    """Alert colour: yellow if anything awaits, amber if only blocked, else none."""
    return AWAITING if g["awaiting"] else BLOCKED if g["blocked"] else None


def plain(g: dict) -> str:
    """Untagged Glance text (tray tooltip); zero alerts hidden."""
    parts = [f"●{g['live']} live"]
    if g["awaiting"]:
        parts.append(f"⚠{g['awaiting']} awaiting")
    if g["blocked"]:
        parts.append(f"⧖{g['blocked']} blocked")
    return "Tasks: " + "  ".join(parts)


def line(g: dict) -> str:
    """Polybar-formatted Glance; empty (module hidden) with no Sessions.

    The ● is always blue; the rest is yellow if anything awaits, amber if only blocked.
    """
    if not g["live"]:
        return ""
    c = colour(g)
    parts = [_fg(LIVE, "●") + GAP + _fg(c, f"{g['live']} live")]
    if g["awaiting"]:
        parts.append(_fg(c, "⚠") + GAP + _fg(c, f"{g['awaiting']} awaiting"))
    if g["blocked"]:
        parts.append(_fg(c, "⧖") + GAP + _fg(c, f"{g['blocked']} blocked"))
    return _fg(c, "Tasks: ") + _fg(c, "  ").join(parts)


def main():
    last = None

    def emit(text: str):
        nonlocal last
        if text != last:
            last = text
            print(text, flush=True)

    def on_event(raw: bytes):
        ev = json.loads(raw)
        if ev.get("event") == "glance":
            emit(line(ev["glance"]))

    try:
        events(["glance"], on_event, lambda: emit(DOWN), threading.Event())
    except (BrokenPipeError, KeyboardInterrupt):  # the bar went away
        sys.exit(0)
