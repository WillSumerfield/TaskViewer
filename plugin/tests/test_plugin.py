import json
import os

import pytest

from taskviewer_app.state import STALE_TURNS
import taskviewer_client as client
from taskviewer_plugin import mcp_server as m

from plugin_helpers import hook


def _context(out: str) -> str:
    return json.loads(out)["hookSpecificOutput"]["additionalContext"]


def _session(sid="s1") -> dict:
    snap = client.call({"op": "snapshot"})["result"]
    return next(s for s in snap["sessions"] if s["id"] == sid)


@pytest.fixture
def tools(monkeypatch):
    monkeypatch.setattr(m, "PID", os.getpid())
    return m


def test_session_start_autostarts_app_and_notes(state_dir):
    note = _context(hook("session-start"))
    assert "TaskViewer is on" in note and "candidates" not in note
    assert "silently" in note
    assert (state_dir / "port").exists()
    assert _session()["project"]  # registered


def test_session_start_lists_candidates_and_resume(app, tools):
    hook("session-start")
    tools.create_tree("Ship it")
    hook("end")
    note = _context(hook("session-start", session_id="s2"))
    assert "t1 [dormant] Ship it" in note and "ask the user" in note
    hook("end", session_id="s2")
    note = _context(hook("session-start", source="resume"))  # s1 resumed
    assert "attached to tree t1 (resumed)" in note


def test_activity_hooks(app):
    hook("session-start")
    hook("prompt")
    assert _session()["activity"] == "working"
    hook("notify", notification_type="permission_prompt")
    assert _session()["activity"] == "awaiting"
    hook("tool")
    hook("notify", notification_type="idle_prompt")  # ignored
    assert _session()["activity"] == "working"
    hook("ask")  # AskUserQuestion shown
    assert _session()["activity"] == "awaiting"
    hook("stop")
    assert _session()["activity"] == "idle"


def test_stale_reminder_on_prompt(app):
    hook("session-start")
    for _ in range(STALE_TURNS):
        assert hook("prompt") == ""
        hook("tool")
        hook("stop")
    assert "no Task tree yet" in _context(hook("prompt"))


def test_prompt_registers_unknown_session(app):
    hook("prompt")  # plugin installed mid-Session: no SessionStart seen
    assert _session()["activity"] == "working"


def test_hook_silent_without_app(state_dir):
    assert hook("stop") == ""


def test_mcp_tools(app, tools):
    hook("session-start")
    assert tools.create_tree("Build TaskViewer") == "created tree t1"
    assert tools.add_task("t1", "Protocol") == "added t2"
    tools.add_task("t1", "Board")
    out = tools.set_status("t2", "done")
    assert out == "ok"
    out = tools.set_status("t3", "done")
    assert "warning: all Subtasks of t1 finished; t1 still active" in out
    assert tools.get_tree() == ("tree t1 [live] Sessions: 1\n"
                                "t1 [active] Build TaskViewer\n"
                                "  t2 [done] Protocol\n"
                                "  t3 [done] Board")
    tools.set_awaiting()
    hook("stop")
    assert _session()["activity"] == "awaiting"
    with pytest.raises(RuntimeError, match="unknown task"):
        tools.set_status("t99", "done")


def test_mcp_follows_clear(app, tools):
    hook("session-start")
    tools.create_tree("first")
    hook("end")
    hook("session-start", session_id="s2", source="clear")
    assert "no tree" in pytest.raises(RuntimeError, tools.get_tree).value.args[0]
    assert tools.list_candidates() == "t1 [dormant] first"


@pytest.mark.parametrize("running", [True, False])
def test_ensure_board_starts_only_when_silent(monkeypatch, running):
    import subprocess

    import taskviewer_board.control as control
    from taskviewer_plugin import hook as h

    launched = []
    monkeypatch.setattr(control, "send", lambda cmd: running)
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: launched.append(cmd))
    monkeypatch.setattr(subprocess, "DETACHED_PROCESS", 8, raising=False)
    monkeypatch.setattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 512, raising=False)
    h.ensure_board()
    assert launched == ([] if running else [["taskviewer-boardw"]])


@pytest.mark.parametrize("exe", ["/mnt/c/Users/me/.local/bin/taskviewer-boardw.exe", None])
def test_wsl_launches_windows_board_if_on_path(monkeypatch, exe):
    import shutil
    import subprocess

    from taskviewer_plugin import hook as h

    launched = []
    monkeypatch.setattr(shutil, "which", lambda name: exe)
    monkeypatch.setattr(subprocess, "Popen", lambda cmd, **kw: launched.append(cmd))
    h.ensure_windows_board()
    assert launched == ([[exe]] if exe else [])
