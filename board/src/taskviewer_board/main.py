"""`taskviewer-board` runs the Board; `taskviewer-board toggle|collapse|reload` controls the running one."""

import argparse
import sys

from .control import send


def run():
    import signal

    from PySide6.QtWidgets import QApplication

    from . import config, control, feed
    from .window import Board, Bridge

    app = QApplication(sys.argv)
    app.setApplicationName("TaskViewer")
    app.setDesktopFileName("TaskViewer")
    board = Board(config.load())
    server = control.make_server(board.command)
    if server is None:
        print("taskviewer-board already running")
        return
    bridge = Bridge()
    bridge.snapshot.connect(board.on_snapshot)
    bridge.down.connect(board.on_down)
    feed.run_in_thread(bridge.snapshot.emit, bridge.down.emit)
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    app.exec()


def main():
    ap = argparse.ArgumentParser(prog="taskviewer-board")
    ap.add_argument("command", nargs="?", choices=["toggle", "collapse", "reload"])
    args = ap.parse_args()
    if args.command is None:
        run()
    elif not send(args.command):
        sys.exit("taskviewer-board is not running")
