import msgspec
import pytest

import taskviewer_protocol as p

REQUESTS = [
    p.RegisterSession(id=1, session_id="s", pid=2, pid_start=3.0, project="/x", title="t"),
    p.EndSession(session_id="s"),
    p.SetAwaiting(session_id="s", awaiting=True),
    p.SetTitle(session_id="s", title="new"),
    p.CreateTree(session_id="s", goal="g"),
    p.Attach(session_id="s", tree_id="t1"),
    p.Detach(session_id="s"),
    p.ListCandidates(project="/x"),
    p.GetTree(session_id="s"),
    p.AddTask(parent_id="t1", goal="g", status="blocked"),
    p.SetStatus(task_id="t1", status="done"),
    p.RenameTask(task_id="t1", goal="h"),
    p.MoveTask(task_id="t2", new_parent_id="t1", index=0),
    p.DeleteTask(task_id="t2"),
    p.Snapshot(),
    p.Subscribe(topics=["glance"]),
]


@pytest.mark.parametrize("req", REQUESTS, ids=lambda r: type(r).__name__)
def test_request_roundtrip(req):
    line = p.encode(req)
    assert line.endswith(b"\n") and line.count(b"\n") == 1
    assert p.decode_request(line) == req


def test_op_tag_on_wire():
    assert b'"op":"set_status"' in p.encode(p.SetStatus(task_id="t1", status="done"))


def test_bad_status_rejected():
    with pytest.raises(msgspec.ValidationError):
        p.decode_request(b'{"op":"set_status","task_id":"t1","status":"finished"}')


def test_unknown_op_rejected():
    with pytest.raises(msgspec.ValidationError):
        p.decode_request(b'{"op":"nope"}')


def test_event_roundtrip():
    ev = p.GlanceEvent(glance=p.Glance(live=1, awaiting=0, blocked=2))
    assert p.decode_event(p.encode(ev)) == ev


def test_reply_omits_defaults():
    line = p.encode(p.Reply(id=3, ok=True))
    assert line == b'{"id":3,"ok":true}\n'
