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
