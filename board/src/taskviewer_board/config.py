"""Board user config (`board.toml`) and Qt-free placement."""

import os
import sys
import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

CORNERS = {"top-left", "top-right", "bottom-left", "bottom-right", "center"}


@dataclass(frozen=True)
class Config:
    monitor: str = "focused"
    corner: str = "top-right"
    offset: tuple[int, int] = (8, 8)
    width: int = 360
    max_height: float = 0.8
    opacity: float = 0.95
    font_size: int = 14
    wrap: bool = True  # long goals/titles wrap; false = cut off with …
    # Windows only (i3 binds keys on Linux)
    hotkey_toggle: str = "ctrl+alt+t"
    hotkey_collapse: str = "ctrl+alt+shift+t"
    hotkey_reload: str = "ctrl+alt+r"
    # use an App running elsewhere (e.g. WSL: \\wsl.localhost\Ubuntu\home\me\.local\state\taskviewer)
    app_state_dir: str = ""


MODS = {"alt": 0x1, "ctrl": 0x2, "shift": 0x4, "win": 0x8}  # Win32 MOD_*


def parse_hotkey(s: str) -> tuple[int, int] | None:
    """"ctrl+alt+t" -> (Win32 modifiers, virtual-key code); None if malformed.

    Needs at least one modifier and one key: a letter, digit or F1-F24.
    """
    *mods, key = [p.strip() for p in s.lower().split("+")]
    if not mods or any(m not in MODS for m in mods) or len(set(mods)) != len(mods):
        return None
    if len(key) == 1 and (key.isascii() and key.isalnum()):
        vk = ord(key.upper())
    elif key[:1] == "f" and key[1:].isdigit() and 1 <= int(key[1:]) <= 24:
        vk = 0x6F + int(key[1:])
    else:
        return None
    m = 0
    for x in mods:
        m |= MODS[x]
    return m, vk


def path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "taskviewer" / "board.toml"


def _valid(key: str, v) -> bool:
    match key:
        case "wrap":
            return type(v) is bool
        case "app_state_dir":
            return isinstance(v, str)
        case "monitor":
            return isinstance(v, str) and bool(v)
        case "corner":
            return v in CORNERS
        case "offset":
            return isinstance(v, list) and len(v) == 2 and all(type(i) is int for i in v)
        case "width" | "font_size":
            return type(v) is int and v > 0
        case "max_height" | "opacity":
            return type(v) in (int, float) and 0 < v <= 1
        case "hotkey_toggle" | "hotkey_collapse" | "hotkey_reload":
            return isinstance(v, str) and parse_hotkey(v) is not None
    return False


def load(p: Path | None = None) -> Config:
    """Missing file/key → default; unknown key or bad value → warning + default."""
    p = p or path()
    try:
        raw = tomllib.loads(p.read_text())
    except FileNotFoundError:
        return Config()
    except (OSError, tomllib.TOMLDecodeError) as e:
        print(f"taskviewer-board: {p}: {e}; using defaults", file=sys.stderr)
        return Config()
    known = {f.name for f in fields(Config)}
    kw = {}
    for k, v in raw.items():
        if k not in known:
            print(f"taskviewer-board: {p}: unknown key {k!r}", file=sys.stderr)
        elif not _valid(k, v):
            print(f"taskviewer-board: {p}: bad {k} = {v!r}; using default", file=sys.stderr)
        else:
            kw[k] = tuple(v) if k == "offset" else float(v) if k in ("max_height", "opacity") else v
    return Config(**kw)


Rect = tuple[int, int, int, int]  # x, y, w, h


def pick_output(monitor: str, outputs: dict[str, Rect], focused: str) -> str:
    """The configured output if plugged in, else the focused one."""
    return monitor if monitor in outputs else focused


def place(rect: Rect, size: tuple[int, int], cfg: Config) -> tuple[int, int]:
    """Top-left point for a window of `size` at cfg.corner of `rect`, cfg.offset in."""
    x, y, w, h = rect
    bw, bh = size
    if cfg.corner == "center":
        return x + (w - bw) // 2, y + (h - bh) // 2
    ox, oy = cfg.offset
    v, hz = cfg.corner.split("-")
    px = x + ox if hz == "left" else x + w - bw - ox
    py = y + oy if v == "top" else y + h - bh - oy
    return px, py
