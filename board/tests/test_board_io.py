"""Control socket and App feed, against real sockets/processes (no window)."""

import os
import subprocess
import sys
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.mark.parametrize("cmd", ["toggle", "reload"])
def test_control_commands_reach_running_board(state_dir, cmd):
    from PySide6.QtCore import QCoreApplication, QTimer

    from taskviewer_board import control

    app = QCoreApplication.instance() or QCoreApplication(sys.argv)
    got = []
    server = control.make_server(got.append)
    assert control.make_server(got.append) is None  # a second Board refuses to start
    sender = subprocess.Popen([sys.executable, "-c",
                               "from taskviewer_board.main import main; import sys; sys.argv=['x',sys.argv[1]]; main()", cmd])
    QTimer.singleShot(3000, app.quit)
    timer = QTimer(interval=20, timeout=lambda: got and sender.poll() is not None and app.quit())
    timer.start()
    app.exec()
    assert got == [cmd] and sender.returncode == 0
    server.close()


def test_toggle_without_board_fails(state_dir):
    out = subprocess.run([sys.executable, "-c", "from taskviewer_board.main import main; import sys; sys.argv=['x','collapse']; main()"],
                         capture_output=True, text=True)
    assert out.returncode == 1 and "not running" in out.stderr


def test_feed_starts_app_and_streams(state_dir):
    from taskviewer_board import feed

    snaps, downs = [], []
    got = threading.Event()
    stop = feed.run_in_thread(lambda s: (snaps.append(s), got.set()), lambda: downs.append(1))
    assert got.wait(10), "no snapshot: App not started"
    stop.set()
    assert downs and snaps[0].trees == []  # was down first, then started the App
