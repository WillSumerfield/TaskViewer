"""Test CLI: send one op to the App and print the reply.

  tvc <op> key=value ...     values parsed as JSON when possible (e.g. index=0)
  tvc subscribe [topic ...]  print pushed events until Ctrl-C
  tvc fake-session <id> [project]   register a Session using this shell's pid

Examples:
  tvc fake-session s1 /tmp/proj
  tvc create_tree session_id=s1 goal="Create task app"
  tvc add_task parent_id=t1 goal="App display"
  tvc set_status task_id=t2 status=done
  tvc snapshot
"""

import argparse
import json
import os
import socket
import sys
from pathlib import Path

import psutil

from .storage import Storage, default_dir


def _value(v: str):
    try:
        return json.loads(v)
    except json.JSONDecodeError:
        return v


def connect(root: Path) -> socket.socket:
    port = Storage(root).read_port()
    if port is None:
        sys.exit("App not running (no port file)")
    return socket.create_connection(("127.0.0.1", port))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state-dir", type=Path, default=default_dir())
    ap.add_argument("op")
    ap.add_argument("args", nargs="*")
    a = ap.parse_args()

    if a.op == "fake-session":
        # the calling shell (skipping `uv run`), so the Session lives as long as it does
        proc = psutil.Process().parent()
        while proc.name() in ("uv", "uvx"):
            proc = proc.parent()
        pid = proc.pid
        msg = {"op": "register_session", "session_id": a.args[0], "pid": pid,
               "project": a.args[1] if len(a.args) > 1 else os.getcwd(), "title": f"fake {a.args[0]}"}
    elif a.op == "subscribe":
        msg = {"op": "subscribe", "topics": a.args or ["glance", "state"]}
    else:
        msg = {"op": a.op, **{k: _value(v) for k, v in (x.split("=", 1) for x in a.args)}}
    msg["id"] = 1

    sock = connect(a.state_dir)
    sock.sendall(json.dumps(msg).encode() + b"\n")
    f = sock.makefile("rb")
    try:
        for line in f:
            print(json.dumps(json.loads(line), indent=2), flush=True)
            if a.op != "subscribe":
                break
    except KeyboardInterrupt:
        pass
