"""Phase 2 Session rules: pid lookup, /clear, resume, activity, stale reminder, candidates."""

import pytest

import taskviewer_protocol as p
from taskviewer_app.state import MAX_CANDIDATES, STALE_TURNS, OpError, State

from app_helpers import add, make_tree, register


def test_pid_lookup_walks_ancestors(clock):
    # MCP server (pid 3) is a child of a wrapper (2) under claude (1)
    state = State(clock, ancestors=lambda pid: {3: [2, 1], 2: [1]}.get(pid, []))
    register(state, "s1", pid=1)
    result, _ = state.apply(p.CreateTree(pid=3, goal="g"))
    assert state.sessions["s1"].tree_id == result["tree_id"]
    with pytest.raises(OpError):
        state.apply(p.CreateTree(pid=99, goal="g"))


def test_clear_starts_fresh_session_on_same_pid(state):
    register(state, "s1", pid=1)
    r = make_tree(state, "s1")
    result = register(state, "s2", pid=1)  # /clear: new Session id, same claude process
    assert "s1" not in state.sessions
    assert result["tree_id"] is None
    assert [c.tree_id for c in result["candidates"]] == [r]
    state.apply(p.CreateTree(pid=1, goal="other"))  # MCP calls now reach the new Session
    assert state.sessions["s2"].tree_id is not None
    assert state.lifecycle(state.trees[r]) == "hidden"


def test_resume_reattaches_last_tree(state):
    register(state, "s1", pid=1)
    r = make_tree(state, "s1")
    state.end_session("s1")
    result = register(state, "s1", pid=2)  # claude --resume: same id, new process
    assert result["tree_id"] == r
    assert state.trees[r].sessions == ["s1"]


def test_resume_after_tree_deleted_is_fresh(state):
    register(state, "s1", pid=1)
    r = make_tree(state, "s1")
    state.end_session("s1")
    state.apply(p.DeleteTask(task_id=r))
    assert register(state, "s1", pid=2)["tree_id"] is None


def test_resume_after_explicit_detach_is_fresh(state):
    register(state, "s1", pid=1)
    make_tree(state, "s1")
    state.apply(p.Detach(session_id="s1"))
    state.end_session("s1")
    assert register(state, "s1", pid=2)["tree_id"] is None


def test_activity_transitions(state):
    register(state, "s1")
    act = lambda: state.sessions["s1"].activity
    assert act() == "idle"  # new Session waits for its first prompt
    state.apply(p.PromptSubmitted(session_id="s1"))
    assert act() == "working"
    state.apply(p.SetActivity(session_id="s1", activity="awaiting"))  # permission prompt
    assert state.glance().awaiting == 1
    state.apply(p.ToolUsed(session_id="s1"))  # permission granted, tool ran
    assert act() == "working"
    state.apply(p.TurnEnded(session_id="s1"))
    assert act() == "idle" and state.glance().awaiting == 0


def test_set_awaiting_holds_until_turn_ends(state):
    register(state, "s1", pid=1)
    state.apply(p.PromptSubmitted(session_id="s1"))
    state.apply(p.SetAwaiting(pid=1))
    state.apply(p.ToolUsed(session_id="s1"))  # PostToolUse for the set_awaiting call itself
    assert state.sessions["s1"].activity == "working"
    state.apply(p.TurnEnded(session_id="s1"))
    assert state.sessions["s1"].activity == "awaiting"
    state.apply(p.PromptSubmitted(session_id="s1"))  # user answered
    state.apply(p.TurnEnded(session_id="s1"))
    assert state.sessions["s1"].activity == "idle"


def _turn(state, tools=True, touch=None):
    state.apply(p.PromptSubmitted(session_id="s1"))
    if tools:
        state.apply(p.ToolUsed(session_id="s1"))
    if touch:
        state.apply(p.SetStatus(task_id=touch, status="active"))
    state.apply(p.TurnEnded(session_id="s1"))


def test_stale_reminder_counts_and_resets(state):
    register(state, "s1")
    r = make_tree(state, "s1")
    _turn(state, touch=r)  # creating/attaching the tree counted as a change
    for _ in range(STALE_TURNS - 1):
        _turn(state)
    _turn(state, tools=False)  # turns without tools don't count
    assert not state.apply(p.PromptSubmitted(session_id="s1"))[0]["remind"]
    state.apply(p.ToolUsed(session_id="s1"))
    state.apply(p.TurnEnded(session_id="s1"))
    result, _ = state.apply(p.PromptSubmitted(session_id="s1"))
    assert result == {"remind": True, "tree_id": r}
    state.apply(p.TurnEnded(session_id="s1"))
    assert not state.apply(p.PromptSubmitted(session_id="s1"))[0]["remind"]  # reset after reminding


def test_tree_change_by_another_session_resets(state):
    register(state, "s1")
    register(state, "s2")
    r = make_tree(state, "s1")
    state.apply(p.Attach(session_id="s2", tree_id=r))
    for _ in range(STALE_TURNS - 1):
        _turn(state)
    state.apply(p.PromptSubmitted(session_id="s1"))
    state.apply(p.ToolUsed(session_id="s1"))
    add(state, r)  # s2 changes the shared tree mid-turn
    state.apply(p.TurnEnded(session_id="s1"))
    assert state.sessions["s1"].stale_turns == 0


def test_candidates_capped_and_ordered(state, clock):
    register(state, "s1")
    trees = [make_tree(state, "s1", f"g{i}") for i in range(MAX_CANDIDATES + 2)]
    clock.advance(10)
    state.apply(p.Detach(session_id="s1"))
    register(state, "s2")
    state.apply(p.Attach(session_id="s2", tree_id=trees[0]))
    cands = state.apply(p.ListCandidates(project="/proj"))[0]
    assert len(cands) == MAX_CANDIDATES
    assert cands[0].tree_id == trees[0] and cands[0].lifecycle == "live"
    assert cands[1].tree_id == trees[-1]  # most recently left first
    own = state.apply(p.ListCandidates(session_id="s2"))[0]
    assert trees[0] not in [c.tree_id for c in own]


def test_claude_ancestor_skips_launchers():
    from taskviewer_app.liveness import claude_ancestor

    names = {9: "taskviewer-hook.exe", 8: "bash.exe", 7: "claude.exe", 6: "explorer.exe", 5: "python", 4: "uv"}
    up = {9: [8, 7, 6], 5: [4, 7], 8: [6]}
    find = lambda pid: claude_ancestor(pid, names.__getitem__, lambda q: up.get(q, []))
    assert find(9) == 7  # launcher -> shell -> claude
    assert find(7) == 7  # already claude
    assert find(5) == 5  # not a launcher: kept
    assert find(8) == 8  # launchers lead to non-claude: kept


def test_register_resolves_claude_pid(clock):
    state = State(clock, proc_start=lambda pid: 1.0, claude_pid=lambda pid: {9: 7}.get(pid, pid))
    state.apply(p.RegisterSession(session_id="s1", pid=9, project="/proj"))
    assert state.sessions["s1"].pid == 7
