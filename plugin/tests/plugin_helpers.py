import json
import os
import subprocess
import sys


def hook(event: str, provider="claude", **h) -> str:
    """Run a host hook; this test process stands in for Claude or Codex."""
    payload = {"session_id": "s1", "cwd": os.getcwd(), "transcript_path": "", **h}
    env = {**os.environ, "CLAUDE_PID": str(os.getpid()), "CODEX_PID": str(os.getpid())}
    options = ["--provider", "codex"] if provider == "codex" else []
    out = subprocess.run([sys.executable, "-c", "from taskviewer_plugin.hook import main; main()", event, *options],
                         input=json.dumps(payload), capture_output=True, text=True, env=env, timeout=10)
    assert out.returncode == 0, out.stderr
    return out.stdout
