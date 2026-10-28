import taskviewer_protocol as p
from taskviewer_app.state import State
from taskviewer_app.storage import Storage

from app_helpers import add, make_tree, register


def test_roundtrip(tmp_path, state, clock):
    st = Storage(tmp_path)
    register(state, "s1")
    register(state, "s2")
    r = make_tree(state, "s1")
    a = add(state, r, "a", "blocked")
    state.apply(p.SetActivity(session_id="s1", activity="awaiting"))
    other = make_tree(state, "s2")
    state.apply(p.EndSession(session_id="s2"))
    st.flush(state)

    fresh = State(clock)
    st.load(fresh)
    assert fresh.snapshot() == state.snapshot()
    assert fresh.lifecycle(fresh.trees[other]) == "dormant"
    assert fresh.task_tree[a] == r
    # id counter survives, so new ids don't collide
    assert add(fresh, r) not in state.task_tree


def test_flush_deletes_tree_file(tmp_path, state):
    st = Storage(tmp_path)
    register(state)
    r = make_tree(state)
    st.flush(state)
    assert (tmp_path / "trees" / f"{r}.json").exists()
    state.apply(p.DeleteTask(task_id=r))
    st.flush(state)
    assert not (tmp_path / "trees" / f"{r}.json").exists()


def test_no_tmp_files_left(tmp_path, state):
    st = Storage(tmp_path)
    register(state)
    make_tree(state)
    st.flush(state)
    assert not list(tmp_path.rglob("*.tmp"))


def test_port_file(tmp_path):
    st = Storage(tmp_path)
    assert st.read_port() is None
    st.write_port(4321)
    assert st.read_port() == 4321


def test_resume_memory_survives_restart(state, clock, tmp_path):
    st = Storage(tmp_path)
    register(state, "s1", pid=1)
    r = make_tree(state, "s1")
    state.end_session("s1")
    st.flush(state)
    fresh = State(clock)
    st.load(fresh)
    assert register(fresh, "s1", pid=2)["tree_id"] == r
