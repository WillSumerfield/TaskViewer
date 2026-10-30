import json
import os
from pathlib import Path
import re

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
    assert "t1 [hidden] Ship it" in note and "ask the user" in note
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
    assert tools.reset_tree(goal="Ship TaskViewer") == ("tree t1 [live] Sessions: 1\n"
                                                       "t1 [active] Ship TaskViewer")
    assert tools.reset_tree(new_tree=True, goal="Next").startswith("tree t4 [live]")


def test_mcp_follows_clear(app, tools):
    hook("session-start")
    tools.create_tree("first")
    hook("end")
    hook("session-start", session_id="s2", source="clear")
    assert "no tree" in pytest.raises(RuntimeError, tools.get_tree).value.args[0]
    assert tools.list_candidates() == "t1 [hidden] first"


def test_codex_sessions_route_tools_independently(app, tools):
    note = _context(hook("session-start", provider="codex", session_id="codex-a", transcript_path=None))
    assert 'session_id is "codex-a"' in note
    hook("session-start", provider="codex", session_id="codex-b")
    first = tools.create_tree("First goal", session_id="codex-a")
    second = tools.create_tree("Second goal", session_id="codex-b")
    assert first != second
    assert "First goal" in tools.get_tree(session_id="codex-a")
    assert "Second goal" in tools.get_tree(session_id="codex-b")
    with pytest.raises(RuntimeError, match="give session_id explicitly"):
        tools.create_tree("Ambiguous goal")
    tools.set_awaiting(session_id="codex-a")
    assert hook("stop", provider="codex", session_id="codex-a").strip() == "{}"
    assert _session("codex-a")["activity"] == "awaiting"
    assert _session("codex-b")["activity"] == "idle"
    hook("end", provider="codex", session_id="codex-a")
    assert "Second goal" in tools.get_tree(session_id="codex-b")


def test_codex_resume_and_first_prompt_title(app, tools):
    hook("session-start", provider="codex", session_id="codex")
    tools.create_tree("Continue goal", session_id="codex")
    hook("end", provider="codex", session_id="codex")
    note = _context(hook("session-start", provider="codex", session_id="codex", source="resume"))
    assert "attached to tree t1 (resumed)" in note
    note = _context(hook("prompt", provider="codex", session_id="codex", prompt="Help me ship this"))
    assert 'session_id: "codex"' in note
    assert _session("codex")["title"] == "Help me ship this"
    hook("prompt", provider="codex", session_id="codex", prompt="Another request")
    assert _session("codex")["title"] == "Help me ship this"


def test_codex_and_claude_coexist(app, tools):
    hook("session-start")
    tools.create_tree("Claude goal")
    hook("session-start", provider="codex", session_id="codex")
    tools.create_tree("Codex goal", session_id="codex")
    assert "Claude goal" in tools.get_tree(session_id="s1")
    assert "Codex goal" in tools.get_tree(session_id="codex")


def test_codex_stop_is_valid_json_without_app(state_dir):
    assert json.loads(hook("stop", provider="codex")) == {}


def _codex_event(event, **payload):
    """Dispatch the shipped hook configuration, including matcher selection."""
    config = Path(__file__).parents[1] / "claude-plugin/hooks/codex.json"
    for group in json.loads(config.read_text())["hooks"].get(event, []):
        matcher = group.get("matcher", "*")
        if matcher not in ("", "*") and not re.search(matcher, payload.get("tool_name", "")):
            continue
        for command in group["hooks"]:
            hook(command["command"].split()[1], provider="codex",
                 hook_event_name=event, **payload)


def test_codex_approval_checks_and_async_questions_do_not_show_warning(app):
    hook("session-start", provider="codex")
    hook("prompt", provider="codex")
    _codex_event("PermissionRequest", tool_name="Bash")
    # Automatic approval and subsequent long-running tools need no user input.
    assert _session()["activity"] == "working"
    _codex_event("PreToolUse", tool_name="request_user_input_async")
    assert _session()["activity"] == "working"


@pytest.mark.parametrize("tool_name", ["request_user_input", "functions.request_user_input"])
def test_codex_blocking_question_clears_when_work_resumes(app, tool_name):
    hook("session-start", provider="codex")
    hook("prompt", provider="codex")
    _codex_event("PreToolUse", tool_name=tool_name)
    assert _session()["activity"] == "awaiting"
    # Starting another tool clears a stale warning before that tool finishes.
    _codex_event("PreToolUse", tool_name="Bash")
    assert _session()["activity"] == "working"


def test_codex_cached_hooks_ignore_approval_checks_and_async_questions(app):
    hook("session-start", provider="codex")
    hook("prompt", provider="codex")
    hook("ask", provider="codex", hook_event_name="PermissionRequest", tool_name="Bash")
    assert _session()["activity"] == "working"
    hook("ask", provider="codex", hook_event_name="PreToolUse", tool_name="request_user_input_async")
    assert _session()["activity"] == "working"


def test_codex_session_end_hides_tree_while_shared_host_stays_alive(app, tools):
    hook("session-start", provider="codex", session_id="closed")
    hook("session-start", provider="codex", session_id="open")
    tools.create_tree("Closed terminal goal", session_id="closed")
    tools.create_tree("Open terminal goal", session_id="open")
    _codex_event("SessionEnd", session_id="closed", reason="other")
    snapshot = client.call({"op": "snapshot"})["result"]
    assert [s["id"] for s in snapshot["sessions"]] == ["open"]
    assert [t["root"]["goal"] for t in snapshot["trees"]] == ["Open terminal goal"]
    assert "[hidden] Closed terminal goal" in tools.list_candidates(session_id="open")


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


def test_session_title_tool_before_tree_and_shared_host_isolation(app, tools):
    hook("session-start", provider="codex", session_id="a")
    hook("session-start", provider="codex", session_id="b")
    assert tools.set_session_title("Fix no-tree wrapping", session_id="a") == "title: Fix no-tree wrapping"
    assert tools.set_session_title("Another current goal", session_id="a") == "title: Another current goal"
    assert _session("a")["tree_id"] is None
    assert _session("b")["title"] == ""
    with pytest.raises(RuntimeError, match="give session_id explicitly"):
        tools.set_session_title("Ambiguous current goal")
    for title in ("", "Verbose", "one two three four five six", "huge " + "x" * 60):
        with pytest.raises(RuntimeError):
            tools.set_session_title(title, session_id="a")
    client.call({"op": "set_title", "session_id": "a", "title": "My custom title"})
    assert "explicit title preserved" in tools.set_session_title("New current goal", session_id="a")
    assert _session("a")["title"] == "My custom title"


def test_codex_prompt_fallback_is_short_and_requests_title(app):
    hook("session-start", provider="codex", session_id="codex")
    note = _context(hook("prompt", provider="codex", session_id="codex",
                         prompt="$grill-with-docs TaskViewer has a bug with very long names"))
    assert _session("codex")["title"] == "TaskViewer has a bug with"
    assert "set_session_title" in note
