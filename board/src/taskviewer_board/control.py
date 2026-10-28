"""Board control channel: `taskviewer-board toggle|collapse|reload` -> running Board.

A Unix socket, or a named pipe on Windows. The sender is stdlib-only so commands start fast (no Qt import).
"""

import hashlib
import os
import socket
import sys
import tempfile

from taskviewer_client import state_dir

COMMANDS = ("toggle", "collapse", "reload", "ping")


WIN = sys.platform == "win32"
PIPE = "\\\\.\\pipe\\"  # \\.\pipe\


def sock_path() -> str:
    """One per state dir. Windows: a pipe name (Qt adds the pipe prefix). Else a short path (cap ~108 chars)."""
    name = "taskviewer-board-" + hashlib.sha1(str(state_dir()).encode()).hexdigest()[:10]
    if WIN:
        return name
    return os.path.join(os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir(), name + ".sock")


def send(cmd: str) -> bool:
    """Send one command; False if no Board is listening."""
    try:
        if WIN:
            with open(PIPE + sock_path(), "wb", buffering=0) as f:
                f.write(cmd.encode() + b"\n")
            return True
        with socket.socket(socket.AF_UNIX) as s:
            s.settimeout(1.0)
            s.connect(sock_path())
            s.sendall(cmd.encode() + b"\n")
        return True
    except OSError:
        return False


def make_server(on_command):
    """QLocalServer calling on_command(cmd) per line. None if a Board already runs."""
    from PySide6.QtNetwork import QLocalServer

    if send("ping"):
        return None
    path = sock_path()
    QLocalServer.removeServer(path)
    server = QLocalServer()
    if not server.listen(path):
        raise RuntimeError(server.errorString())

    def accept():
        while (conn := server.nextPendingConnection()) is not None:
            def read(c=conn):
                while c.canReadLine():
                    cmd = bytes(c.readLine()).decode().strip()
                    if cmd in COMMANDS and cmd != "ping":
                        on_command(cmd)
            conn.readyRead.connect(read)
            conn.disconnected.connect(conn.deleteLater)

    server.newConnection.connect(accept)
    return server
