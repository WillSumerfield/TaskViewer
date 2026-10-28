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
    width: int = 300
    max_height: float = 0.8
    opacity: float = 0.9
    font_size: int = 10


def path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / "taskviewer" / "board.toml"


def _valid(key: str, v) -> bool:
    match key:
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
