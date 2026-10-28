"""`taskviewer-board` runs the Board; `taskviewer-board toggle|collapse|reload` controls the running one."""

import argparse
import os
import sys

from . import config
from .control import send


def use_app_state_dir(cfg: config.Config):
    """board.toml app_state_dir points the Board (and its control channel name) at an App elsewhere."""
    if cfg.app_state_dir:
        os.environ["TASKVIEWER_STATE_DIR"] = cfg.app_state_dir


def run(cfg: config.Config):
    import signal

    from PySide6.QtWidgets import QApplication

    from . import control, feed
    from .window import Board, Bridge

    app = QApplication(sys.argv)
    app.setApplicationName("TaskViewer")
    app.setDesktopFileName("TaskViewer")
    board = Board(cfg)
    server = control.make_server(board.command)
    if server is None:
        print("taskviewer-board already running")
        return
    bridge = Bridge()
    bridge.snapshot.connect(board.on_snapshot)
    bridge.down.connect(board.on_down)
    on_glance = None
    if sys.platform == "win32":
        win = windows(app, board, bridge)  # keep references alive
        on_glance = bridge.glance.emit
    feed.run_in_thread(bridge.snapshot.emit, bridge.down.emit, on_glance, start=not cfg.app_state_dir)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app.exec()


def windows(app, board, bridge):
    """Tray Glance + global hotkeys (Windows has no i3 or polybar)."""
    from .tray import Tray
    from .winapi import Hotkeys

    app.setQuitOnLastWindowClosed(False)
    tray = Tray(board, app.quit)
    bridge.glance.connect(tray.on_glance)
    bridge.down.connect(tray.on_down)
    keys = Hotkeys(int(board.winId()), board.command)
    app.installNativeEventFilter(keys)

    def register(cfg):
        keys.register({"toggle": cfg.hotkey_toggle, "collapse": cfg.hotkey_collapse, "reload": cfg.hotkey_reload})

    register(board.cfg)
    board.on_reload = register
    return tray, keys


def _log_if_windowless():
    """pythonw (taskviewer-boardw) has no stdout/stderr; send prints to a log instead of crashing."""
    if sys.stdout is None or sys.stderr is None:
        from taskviewer_client import state_dir

        state_dir().mkdir(parents=True, exist_ok=True)
        sys.stdout = sys.stderr = open(state_dir() / "board.log", "a", buffering=1, encoding="utf-8")


def main():
    _log_if_windowless()
    ap = argparse.ArgumentParser(prog="taskviewer-board")
    ap.add_argument("command", nargs="?", choices=["toggle", "collapse", "reload"])
    args = ap.parse_args()
    cfg = config.load()
    use_app_state_dir(cfg)
    if args.command is None:
        run(cfg)
    elif not send(args.command):
        sys.exit("taskviewer-board is not running")
