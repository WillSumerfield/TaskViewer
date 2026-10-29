import pytest

import taskviewer_protocol as p
from taskviewer_app.state import OpError

from app_helpers import add, make_tree, register


def ids(view: p.TaskView) -> list[str]:
    return [c.id for c in view.children]


def test_create_tree_attaches_session(state):
    register(state)
    tid = make_tree(state)
    assert state.sessions["s1"].tree_id == tid
    assert state.trees[tid].sessions == ["s1"]
    assert state.trees[tid].tasks[tid].status == "active"


def test_create_tree_requires_session(state):
    with pytest.raises(OpError):
        state.apply(p.CreateTree(session_id="nobody", goal="g"))


def test_ids_unique_across_trees(state):
    register(state, "s1")
    register(state, "s2")
    a = make_tree(state, "s1")
    a1 = add(state, a)
    b = make_tree(state, "s2")
    b1 = add(state, b)
    assert len({a, a1, b, b1}) == 4


def test_add_rename_nested(state):
    register(state)
    r = make_tree(state)
    c = add(state, r, "child")
    g = add(state, c, "grandchild")
    state.apply(p.RenameTask(task_id=g, goal="renamed"))
    view, _ = state.apply(p.GetTree(session_id="s1"))
    assert ids(view.root) == [c]
    assert view.root.children[0].children[0].goal == "renamed"


def test_move_and_index(state):
    register(state)
    r = make_tree(state)
    a, b, c = add(state, r), add(state, r), add(state, r)
    state.apply(p.MoveTask(task_id=c, new_parent_id=a))
    state.apply(p.MoveTask(task_id=b, new_parent_id=a, index=0))
    view, _ = state.apply(p.GetTree(tree_id=r))
    assert ids(view.root) == [a]
    assert ids(view.root.children[0]) == [b, c]


def test_move_rejections(state):
    register(state, "s1")
    register(state, "s2")
    r = make_tree(state, "s1")
    a = add(state, r)
    a1 = add(state, a)
    other = make_tree(state, "s2")
    with pytest.raises(OpError, match="under itself"):
        state.apply(p.MoveTask(task_id=a, new_parent_id=a1))
    with pytest.raises(OpError, match="under itself"):
        state.apply(p.MoveTask(task_id=a, new_parent_id=a))
    with pytest.raises(OpError, match="root"):
        state.apply(p.MoveTask(task_id=r, new_parent_id=a))
    with pytest.raises(OpError, match="another tree"):
        state.apply(p.MoveTask(task_id=a, new_parent_id=other))


def test_delete_subtree(state):
    register(state)
    r = make_tree(state)
    a = add(state, r)
    a1 = add(state, a)
    b = add(state, r)
    state.apply(p.DeleteTask(task_id=a))
    assert set(state.trees[r].tasks) == {r, b}
    assert a1 not in state.task_tree
    with pytest.raises(OpError):
        state.apply(p.SetStatus(task_id=a1, status="done"))


def test_delete_root_removes_tree(state):
    register(state)
    r = make_tree(state)
    add(state, r)
    state.apply(p.DeleteTask(task_id=r))
    assert r not in state.trees
    assert state.sessions["s1"].tree_id is None
    assert r in state.deleted_trees


def test_status_warnings(state):
    register(state)
    r = make_tree(state)
    a = add(state, r)
    b = add(state, r)
    _, w = state.apply(p.SetStatus(task_id=a, status="done"))
    assert w == []
    _, w = state.apply(p.SetStatus(task_id=b, status="dropped"))
    assert any(f"all Subtasks of {r}" in x for x in w)
    state.apply(p.SetStatus(task_id=b, status="active"))
    _, w = state.apply(p.SetStatus(task_id=r, status="done"))
    assert any("Subtasks still open" in x and b in x for x in w)
    _, w = state.apply(p.AddTask(parent_id=r, goal="late"))
    assert any("parent" in x for x in w)


def test_one_tree_per_session(state, clock):
    register(state)
    r1 = make_tree(state, goal="one")
    r2 = make_tree(state, goal="two")
    assert state.sessions["s1"].tree_id == r2
    assert state.trees[r1].sessions == []
    assert state.lifecycle(state.trees[r1]) == "hidden"


def test_multi_session_tree(state):
    register(state, "s1")
    register(state, "s2")
    r = make_tree(state, "s1")
    state.apply(p.Attach(session_id="s2", tree_id=r))
    assert state.trees[r].sessions == ["s1", "s2"]
    state.apply(p.EndSession(session_id="s1"))
    assert state.lifecycle(state.trees[r]) == "live"
    # any attached Session can edit any Task
    state.apply(p.SetStatus(task_id=r, status="blocked"))


def test_attach_wrong_project_rejected(state):
    register(state, "s1", project="/a")
    register(state, "s2", project="/b")
    r = make_tree(state, "s1")
    with pytest.raises(OpError, match="project"):
        state.apply(p.Attach(session_id="s2", tree_id=r))


def test_list_candidates_by_project(state):
    register(state, "s1", project="/a")
    register(state, "s2", project="/b")
    r = make_tree(state, "s1", goal="A goal")
    make_tree(state, "s2")
    result, _ = state.apply(p.ListCandidates(project="/a"))
    assert result == [p.Candidate(tree_id=r, goal="A goal", lifecycle="live")]


def test_get_tree_without_tree_errors(state):
    register(state)
    with pytest.raises(OpError, match="no tree"):
        state.apply(p.GetTree(session_id="s1"))


def test_reregister_keeps_tree(state):
    register(state)
    r = make_tree(state)
    register(state, pid=200)
    assert state.sessions["s1"].tree_id == r
    assert state.sessions["s1"].pid == 200


def test_glance_counts(state):
    register(state, "s1")
    register(state, "s2")
    r = make_tree(state, "s1")
    add(state, r, status="blocked")
    state.apply(p.SetActivity(session_id="s2", activity="awaiting"))
    assert state.glance() == p.Glance(live=2, awaiting=1, blocked=1)
    add(state, add(state, r), status="blocked")  # any depth counts
    assert state.glance().blocked == 2
    make_tree(state, "s1")  # r goes Hidden: its Blocked Tasks stop counting
    assert state.glance() == p.Glance(live=2, awaiting=1, blocked=0)


def test_reset_keeps_root_drops_subtasks(state):
    register(state, "s1")
    register(state, "s2")
    r = make_tree(state, "s1", "old")
    c = add(state, r)
    g = add(state, c)
    state.apply(p.Attach(session_id="s2", tree_id=r))
    state.apply(p.SetStatus(task_id=r, status="done"))
    result, w = state.apply(p.ResetTree(session_id="s1", goal="new"))
    assert result == {"tree_id": r}
    tree = state.trees[r]
    assert list(tree.tasks) == [r] and tree.tasks[r].children == []
    assert tree.tasks[r].goal == "new" and tree.tasks[r].status == "done"
    assert c not in state.task_tree and g not in state.task_tree
    assert tree.sessions == ["s1", "s2"]
    assert w == ["1 other Sessions on this tree"]


def test_reset_keep_root_needs_tree(state):
    register(state)
    with pytest.raises(OpError):
        state.apply(p.ResetTree(session_id="s1"))


def test_reset_new_tree_hides_old(state):
    register(state)
    old = make_tree(state)
    add(state, old)
    with pytest.raises(OpError):
        state.apply(p.ResetTree(session_id="s1", new_tree=True))
    result, _ = state.apply(p.ResetTree(session_id="s1", new_tree=True, goal="fresh"))
    new = result["tree_id"]
    assert new != old and state.sessions["s1"].tree_id == new
    assert state.lifecycle(state.trees[old]) == "hidden"
    assert len(state.trees[old].tasks) == 2
    assert state.trees[new].tasks[new].goal == "fresh"
