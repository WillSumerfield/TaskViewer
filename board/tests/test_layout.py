import taskviewer_protocol as p
from taskviewer_board.layout import AWAIT, layout, project_names

HOME = "/home/u"


def task(goal, status="planned", *children, id="x"):
    return p.TaskView(id=id, goal=goal, status=status, children=list(children))


def tree(id, project, root, lifecycle="live"):
    return p.TreeView(id=id, project=project, lifecycle=lifecycle, sessions=[], root=root)


def sess(id, project, tree_id=None, activity="idle", title=""):
    return p.SessionView(id=id, project=project, title=title or id, activity=activity, tree_id=tree_id)


def texts(rows):
    return [(r.kind, r.text, r.indent, r.tag) for r in rows]


def test_project_names_basename_unless_clash():
    names = project_names({"/home/u/a/app", "/home/u/b/app", "/srv/x/app", "/home/u/tv"}, HOME)
    assert names == {"/home/u/a/app": "~/a/app", "/home/u/b/app": "~/b/app", "/srv/x/app": "/srv/x/app",
                     "/home/u/tv": "tv"}


def test_expanded_order_and_tags():
    snap = p.SnapshotView(
        trees=[tree("t10", "/home/u/zed", task("Z")),
               tree("t9", "/home/u/abc", task("Later", "active", task("sub", "done", task("deep")))),
               tree("t2", "/home/u/abc", task("Old"))],
        sessions=[sess("s1", "/home/u/abc", "t9", "awaiting"), sess("s2", "/home/u/abc", "t9", "working")],
    )
    rows = layout(snap, False, HOME)
    assert (rows[2].icon, rows[2].style) == (AWAIT, "awaiting")  # ⚠ replaces the status icon
    assert texts(rows) == [
        ("project", "abc", 0, ""),
        ("task", "Old", 0, ""),  # by creation: t2 before t9 (numeric)
        ("task", "Later", 0, ""),
        ("task", "sub", 1, ""),
        ("task", "deep", 2, ""),
        ("project", "zed", 0, ""),
        ("task", "Z", 0, ""),
    ]


def test_collapsed_headers_only_with_await_flag():
    snap = p.SnapshotView(
        trees=[tree("t1", "/home/u/abc", task("A", "active", task("sub"))),
               tree("t2", "/home/u/abc", task("B"))],
        sessions=[sess("s1", "/home/u/abc", "t1", "awaiting"), sess("s2", "/home/u/abc", "t2")],
    )
    assert texts(layout(snap, True, HOME)) == [
        ("project", "abc", 0, ""), ("task", "A", 0, ""), ("task", "B", 0, "")]
    assert [(r.icon, r.style) for r in layout(snap, True, HOME)[1:]] == [(AWAIT, "awaiting"), ("○", "planned")]


def test_no_tree_section():
    snap = p.SnapshotView(trees=[], sessions=[sess("s1", "/home/u/abc"), sess("s2", "/home/u/q", activity="awaiting")])
    assert texts(layout(snap, False, HOME)) == [
        ("project", "No tree", 0, ""), ("session", "s1", 1, "abc"), ("session", "s2", 1, "q")]
    assert texts(layout(snap, True, HOME)) == [("project", "No tree", 0, ""), ("note", "2 Sessions", 1, AWAIT)]


def test_empty():
    assert layout(p.SnapshotView(trees=[], sessions=[]), False) == []


def test_wrap_words_and_long_words():
    from taskviewer_board.layout import wrap
    assert wrap("one two three", 7, len) == ["one two", "three"]
    assert wrap("short", 10, len) == ["short"]
    assert wrap("abcdefghij xy", 4, len) == ["abcd", "efgh", "ij", "xy"]
    assert wrap("", 5, len) == [""]
