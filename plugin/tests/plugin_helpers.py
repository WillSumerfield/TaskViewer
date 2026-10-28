import json
import os
import subprocess
import sys


def hook(event: str, **h) -> str:
    """Run taskviewer-hook as Claude would; this test process stands in for claude."""
    payload = {"session_id": "s1", "cwd": os.getcwd(), "transcript_path": "", **h}
    env = {**os.environ, "CLAUDE_PID": str(os.getpid())}
    out = subprocess.run([sys.executable, "-c", "from taskviewer_plugin.hook import main; main()", event],
                         input=json.dumps(payload), capture_output=True, text=True, env=env, timeout=10)
    assert out.returncode == 0, out.stderr
    return out.stdout
