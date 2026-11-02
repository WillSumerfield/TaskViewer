import taskviewer_protocol as p
from taskviewer_board.layout import layout
from taskviewer_board.merge import Merger, label, tag


def task(goal, id):
    return p.TaskView(id=id, goal=goal, status="active", children=[])


def snap(tree_id="t1", project="/home/u/app", sid="s1"):
    return p.SnapshotView(
        trees=[p.TreeView(id=tree_id, project=project, lifecycle="live", sessions=[sid], root=task("g", tree_id))],
        sessions=[p.SessionView(id=sid, project=project, title="x", activity="idle", tree_id=tree_id)])


def G(live, awaiting=0, blocked=0):
    return {"live": live, "awaiting": awaiting, "blocked": blocked}


class Rec:
    def __init__(self):
        self.snaps, self.downs, self.glances = [], 0, []

    def merger(self, labels):
        return Merger(labels, self.snaps.append, self.down, self.glances.append)

    def down(self):
        self.downs += 1


def test_label_from_wsl_paths():
    assert label(r"\\wsl.localhost\Ubuntu-22.04\home\me\.local\state\taskviewer") == "Ubuntu-22.04"
    assert label(r"\\wsl$\Ubuntu\home\me") == "Ubuntu"
    assert label("//wsl.localhost/Debian/home") == "Debian"
    assert label(r"C:\state") == r"C:\state"


def test_tag_prefixes_ids_and_projects():
    t = tag(snap(), "U22")
    assert t.trees[0].id == "U22/t1" and t.trees[0].sessions == ["U22/s1"]
    assert t.trees[0].project == "/home/u/app · U22"
    assert (t.sessions[0].id, t.sessions[0].tree_id) == ("U22/s1", "U22/t1")
    loose = p.SnapshotView(trees=[], sessions=[p.SessionView(id="s", project="/p", title="", activity="idle",
                                                             tree_id=None)])
    assert tag(loose, "U").sessions[0].tree_id is None


def test_single_app_passes_through():
    r = Rec()
    m = r.merger([""])
    s = snap()
    m.snapshot(0, s)
    m.glance(0, G(1))
    m.down(0)
    assert r.snaps == [s] and r.downs == 1 and r.glances[0]["live"] == 1


def test_two_apps_merge_and_stay_apart():
    r = Rec()
    m = r.merger(["A", "B"])
    m.snapshot(0, snap())
    m.snapshot(1, snap())  # same ids and Project in both Apps
    merged = r.snaps[-1]
    assert sorted(t.id for t in merged.trees) == ["A/t1", "B/t1"]
    heads = [row.text for row in layout(merged, False, "/home/u") if row.kind == "project"]
    assert heads == ["app · A", "app · B"]


def test_glance_sums_and_lists_down():
    r = Rec()
    m = r.merger(["A", "B"])
    m.glance(0, G(2, 1))
    m.glance(1, G(3, 0, 1))
    assert r.glances[-1] == {"live": 5, "awaiting": 1, "blocked": 1, "down": []}
    m.down(1)
    assert r.glances[-1] == {"live": 2, "awaiting": 1, "blocked": 0, "down": ["B"]}


def test_down_only_when_all_down():
    r = Rec()
    m = r.merger(["A", "B"])
    m.snapshot(0, snap())
    m.snapshot(1, snap())
    m.down(1)
    assert r.downs == 0 and [t.id for t in r.snaps[-1].trees] == ["A/t1"]
    n = len(r.snaps)
    m.down(1)  # retries while still down change nothing
    assert len(r.snaps) == n
    m.down(0)
    assert r.downs == 1
