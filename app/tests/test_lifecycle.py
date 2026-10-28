import taskviewer_protocol as p
from taskviewer_app.state import DORMANT_SECS, HIDDEN_SECS

from app_helpers import make_tree, register

HOUR = 3600


def always_alive(pid, start):
    return True


def setup_dormant(state):
    register(state)
    r = make_tree(state)
    state.apply(p.EndSession(session_id="s1"))
    return r


def test_live_dormant_hidden_deleted(state, clock):
    r = setup_dormant(state)
    tree = state.trees[r]
    assert state.lifecycle(tree) == "dormant"
    clock.advance(DORMANT_SECS - 1)
    assert state.lifecycle(tree) == "dormant"
    clock.advance(1)
    assert state.lifecycle(tree) == "hidden"
    assert state.sweep(always_alive)  # dormant -> hidden is a visible change
    assert r not in [t.id for t in state.snapshot().trees]
    clock.advance(HIDDEN_SECS - 1)
    assert not state.sweep(always_alive)
    assert r in state.trees
    clock.advance(1)
    assert state.sweep(always_alive)
    assert r not in state.trees and r in state.deleted_trees


def test_hidden_still_candidate(state, clock):
    r = setup_dormant(state)
    clock.advance(DORMANT_SECS + HOUR)
    result, _ = state.apply(p.ListCandidates(project="/proj"))
    assert result == [p.Candidate(tree_id=r, goal="root", lifecycle="hidden")]


def test_reattach_revives(state, clock):
    r = setup_dormant(state)
    clock.advance(DORMANT_SECS + HOUR)
    register(state, "s2")
    state.apply(p.Attach(session_id="s2", tree_id=r))
    assert state.lifecycle(state.trees[r]) == "live"
    # timer restarts from the new last leave
    state.apply(p.Detach(session_id="s2"))
    clock.advance(DORMANT_SECS - 1)
    assert state.lifecycle(state.trees[r]) == "dormant"


def test_timer_starts_when_last_session_leaves(state, clock):
    register(state, "s1")
    register(state, "s2")
    r = make_tree(state, "s1")
    state.apply(p.Attach(session_id="s2", tree_id=r))
    state.apply(p.EndSession(session_id="s1"))
    clock.advance(DORMANT_SECS * 2)
    assert state.lifecycle(state.trees[r]) == "live"
    state.apply(p.EndSession(session_id="s2"))
    clock.advance(DORMANT_SECS - 1)
    assert state.lifecycle(state.trees[r]) == "dormant"


def test_dead_pid_ends_session(state):
    register(state, "s1", pid=1)
    register(state, "s2", pid=2)
    r = make_tree(state, "s1")
    assert state.sweep(lambda pid, start: pid != 1)
    assert "s1" not in state.sessions and "s2" in state.sessions
    assert state.lifecycle(state.trees[r]) == "dormant"


def test_pid_reuse_ends_session(state):
    from taskviewer_app import liveness
    import os
    me = os.getpid()
    real_start = liveness.process_start(me)
    assert liveness.is_alive(me, real_start)
    assert not liveness.is_alive(me, real_start - 100)  # same pid, different process start
    register(state, "s1", pid=me, pid_start=real_start - 100)
    state.sweep(liveness.is_alive)
    assert "s1" not in state.sessions


def test_nothing_changed_sweep(state):
    register(state)
    make_tree(state)
    state.sweep(always_alive)
    assert not state.sweep(always_alive)
