import json

import taskviewer_protocol as p
from taskviewer_app.titles import Titles


def _append(path, *entries, partial=""):
    with open(path, "a") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
        f.write(partial)


def test_titles_custom_over_ai_incremental(state, tmp_path):
    tp = tmp_path / "t.jsonl"
    tp.write_text("")
    state.apply(p.RegisterSession(session_id="s1", pid=1, pid_start=1.0, project="/p", transcript_path=str(tp)))
    titles = Titles()
    assert not titles.poll(state)

    _append(tp, {"type": "user", "message": "hi"}, {"type": "ai-title", "aiTitle": "First"})
    assert titles.poll(state) and state.sessions["s1"].title == "First"

    half = json.dumps({"type": "custom-title", "customTitle": "Mine"})
    _append(tp, partial=half[:10])  # incomplete line not consumed yet
    assert not titles.poll(state)
    _append(tp, partial=half[10:] + "\n")
    assert titles.poll(state) and state.sessions["s1"].title == "Mine"

    _append(tp, {"type": "ai-title", "aiTitle": "Later AI"})  # /rename title wins
    assert not titles.poll(state) and state.sessions["s1"].title == "Mine"


def test_assistant_titles_update_but_explicit_titles_win(state, tmp_path):
    from taskviewer_app.state import State
    from taskviewer_app.storage import Storage

    tp = tmp_path / "titles.jsonl"
    _append(tp, {"type": "ai-title", "aiTitle": "Host generated title"})
    request = p.RegisterSession(session_id="s1", pid=1, pid_start=1.0, project="/p", transcript_path=str(tp))
    state.apply(request)
    titles = Titles()
    titles.poll(state)
    state.apply(p.SetTitle(session_id="s1", title="Fix no-tree wrapping", automatic=True))
    assert not titles.poll(state)  # host AI title cannot overwrite assistant title
    assert state.sessions["s1"].title == "Fix no-tree wrapping"
    state.apply(p.SetTitle(session_id="s1", title="Shorten Session titles", automatic=True))
    assert state.sessions["s1"].title == "Shorten Session titles"
    _append(tp, {"type": "custom-title", "customTitle": "My explicit title"})
    assert titles.poll(state)
    state.apply(p.SetTitle(session_id="s1", title="Another current goal", automatic=True))
    assert state.sessions["s1"].title == "My explicit title"
    state.apply(request)  # repeated registration preserves title provenance
    store = Storage(tmp_path / "state")
    store.flush(state)
    fresh = State()
    store.load(fresh)
    fresh.apply(p.SetTitle(session_id="s1", title="Goal after restart", automatic=True))
    assert fresh.sessions["s1"].title == "My explicit title"


def test_explicit_title_operation_is_preserved(state):
    state.apply(p.RegisterSession(session_id="s1", pid=1, pid_start=1.0, project="/p"))
    state.apply(p.SetTitle(session_id="s1", title="Chosen by user"))
    state.apply(p.SetTitle(session_id="s1", title="Assistant current goal", automatic=True))
    assert state.sessions["s1"].title == "Chosen by user"


def test_old_transcript_title_cannot_undo_new_explicit_title(state, tmp_path):
    from taskviewer_app.state import State
    from taskviewer_app.storage import Storage

    tp = tmp_path / "titles.jsonl"
    _append(tp, {"type": "custom-title", "customTitle": "Old title"})
    request = p.RegisterSession(session_id="s1", pid=1, pid_start=1.0,
                                project="/p", transcript_path=str(tp))
    state.apply(request)
    titles = Titles()
    assert titles.poll(state)
    state.apply(p.SetTitle(session_id="s1", title="New title"))
    assert not titles.poll(state)
    assert state.sessions["s1"].title == "New title"

    state.apply(request)  # registering again must not replay consumed /rename entries
    store = Storage(tmp_path / "state")
    store.flush(state)
    fresh = State()
    store.load(fresh)
    titles = Titles()
    assert not titles.poll(fresh)
    assert fresh.sessions["s1"].title == "New title"

    # A fresh /rename still wins, even when it repeats an older title.
    _append(tp, {"type": "custom-title", "customTitle": "Old title"})
    assert titles.poll(fresh)
    assert fresh.sessions["s1"].title == "Old title"
