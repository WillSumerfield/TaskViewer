"""In-memory Task trees + Sessions, and the rules for changing them."""

import time
from collections.abc import Callable

import msgspec

import taskviewer_protocol as p

DORMANT_SECS = 8 * 3600
HIDDEN_SECS = 30 * 24 * 3600
FINISHED = ("done", "dropped")


class OpError(Exception):
    pass


class Task(msgspec.Struct, kw_only=True):
    id: str
    goal: str
    status: p.Status
    parent: str | None
    children: list[str] = []


class Tree(msgspec.Struct, kw_only=True):
    id: str  # = root task id
    project: str
    tasks: dict[str, Task]
    sessions: list[str] = []
    last_left_at: float | None = None


class Session(msgspec.Struct, kw_only=True):
    id: str
    pid: int
    pid_start: float
    project: str
    title: str = ""
    awaiting: bool = False
    tree_id: str | None = None


class State:
    def __init__(self, clock: Callable[[], float] = time.time):
        self.clock = clock
        self.trees: dict[str, Tree] = {}
        self.sessions: dict[str, Session] = {}
        self.task_tree: dict[str, str] = {}  # task id -> tree id
        self.next_id = 1
        # Change tracking for storage
        self.dirty_trees: set[str] = set()
        self.deleted_trees: set[str] = set()
        self.sessions_dirty = False
        self._last_lifecycle: dict[str, p.Lifecycle] = {}

    # ---- loading ----

    def load(self, trees: list[Tree], sessions: list[Session], next_id: int):
        self.trees = {t.id: t for t in sorted(trees, key=lambda t: int(t.id[1:]))}
        self.sessions = {s.id: s for s in sessions}
        self.task_tree = {tid: t.id for t in trees for tid in t.tasks}
        self.next_id = next_id
        self._last_lifecycle = {t.id: self.lifecycle(t) for t in trees}

    # ---- lookups ----

    def _session(self, sid: str) -> Session:
        if sid not in self.sessions:
            raise OpError(f"unknown session {sid}")
        return self.sessions[sid]

    def _tree(self, tree_id: str) -> Tree:
        if tree_id not in self.trees:
            raise OpError(f"unknown tree {tree_id}")
        return self.trees[tree_id]

    def _task(self, task_id: str) -> tuple[Tree, Task]:
        if task_id not in self.task_tree:
            raise OpError(f"unknown task {task_id}")
        tree = self.trees[self.task_tree[task_id]]
        return tree, tree.tasks[task_id]

    def _new_id(self) -> str:
        i = self.next_id
        self.next_id += 1
        self.sessions_dirty = True  # ids saved alongside sessions
        return f"t{i}"

    def lifecycle(self, tree: Tree) -> p.Lifecycle:
        if tree.sessions or tree.last_left_at is None:
            return "live"
        age = self.clock() - tree.last_left_at
        return "dormant" if age < DORMANT_SECS else "hidden"

    def _expired(self, tree: Tree) -> bool:
        return not tree.sessions and tree.last_left_at is not None and \
            self.clock() - tree.last_left_at >= DORMANT_SECS + HIDDEN_SECS

    # ---- session attach / detach ----

    def _detach(self, s: Session):
        if s.tree_id is None:
            return
        tree = self.trees.get(s.tree_id)
        s.tree_id = None
        self.sessions_dirty = True
        if tree is None:
            return
        tree.sessions.remove(s.id)
        if not tree.sessions:
            tree.last_left_at = self.clock()
        self.dirty_trees.add(tree.id)

    def _attach(self, s: Session, tree: Tree):
        if s.tree_id == tree.id:
            return
        self._detach(s)
        tree.sessions.append(s.id)
        tree.last_left_at = None
        s.tree_id = tree.id
        self.sessions_dirty = True
        self.dirty_trees.add(tree.id)

    def _drop_tree(self, tree: Tree):
        for sid in tree.sessions:
            if sid in self.sessions:
                self.sessions[sid].tree_id = None
                self.sessions_dirty = True
        for tid in tree.tasks:
            del self.task_tree[tid]
        del self.trees[tree.id]
        self._last_lifecycle.pop(tree.id, None)
        self.dirty_trees.discard(tree.id)
        self.deleted_trees.add(tree.id)

    # ---- dispatch ----

    def apply(self, req: p.AnyRequest) -> tuple[object, list[str]]:
        """Apply one request. Returns (result, warnings); raises OpError."""
        warnings: list[str] = []
        match req:
            case p.RegisterSession():
                old = self.sessions.get(req.session_id)
                self.sessions[req.session_id] = Session(
                    id=req.session_id, pid=req.pid, pid_start=req.pid_start,
                    project=req.project, title=req.title,
                    tree_id=old.tree_id if old else None,
                )
                self.sessions_dirty = True
                return None, warnings
            case p.EndSession():
                self.end_session(req.session_id)
                return None, warnings
            case p.SetAwaiting():
                self._session(req.session_id).awaiting = req.awaiting
                self.sessions_dirty = True
                return None, warnings
            case p.SetTitle():
                self._session(req.session_id).title = req.title
                self.sessions_dirty = True
                return None, warnings
            case p.CreateTree():
                s = self._session(req.session_id)
                rid = self._new_id()
                tree = Tree(id=rid, project=s.project,
                            tasks={rid: Task(id=rid, goal=req.goal, status="active", parent=None)})
                self.trees[rid] = tree
                self.task_tree[rid] = rid
                self._attach(s, tree)
                return {"tree_id": rid}, warnings
            case p.Attach():
                s = self._session(req.session_id)
                tree = self._tree(req.tree_id)
                if tree.project != s.project:
                    raise OpError(f"tree {tree.id} belongs to project {tree.project}")
                self._attach(s, tree)
                return None, warnings
            case p.Detach():
                self._detach(self._session(req.session_id))
                return None, warnings
            case p.ListCandidates():
                return [p.Candidate(tree_id=t.id, goal=t.tasks[t.id].goal, lifecycle=self.lifecycle(t))
                        for t in self.trees.values() if t.project == req.project], warnings
            case p.GetTree():
                if req.tree_id:
                    tree = self._tree(req.tree_id)
                elif req.session_id:
                    s = self._session(req.session_id)
                    if s.tree_id is None:
                        raise OpError(f"session {s.id} has no tree")
                    tree = self.trees[s.tree_id]
                else:
                    raise OpError("give session_id or tree_id")
                return self.tree_view(tree), warnings
            case p.AddTask():
                tree, parent = self._task(req.parent_id)
                tid = self._new_id()
                tree.tasks[tid] = Task(id=tid, goal=req.goal, status=req.status, parent=parent.id)
                parent.children.append(tid)
                self.task_tree[tid] = tree.id
                self.dirty_trees.add(tree.id)
                warnings += self._status_warnings(tree, tree.tasks[tid])
                return {"task_id": tid}, warnings
            case p.SetStatus():
                tree, task = self._task(req.task_id)
                task.status = req.status
                self.dirty_trees.add(tree.id)
                warnings += self._status_warnings(tree, task)
                return None, warnings
            case p.RenameTask():
                tree, task = self._task(req.task_id)
                task.goal = req.goal
                self.dirty_trees.add(tree.id)
                return None, warnings
            case p.MoveTask():
                self._move(req)
                return None, warnings
            case p.DeleteTask():
                tree, task = self._task(req.task_id)
                if task.parent is None:
                    self._drop_tree(tree)
                    return None, warnings
                for tid in self._subtree(tree, task.id):
                    del tree.tasks[tid]
                    del self.task_tree[tid]
                tree.tasks[task.parent].children.remove(task.id)
                self.dirty_trees.add(tree.id)
                return None, warnings
            case p.Snapshot():
                return self.snapshot(), warnings
        raise OpError(f"unsupported op {type(req).__name__}")

    def end_session(self, sid: str):
        s = self._session(sid)
        self._detach(s)
        del self.sessions[sid]
        self.sessions_dirty = True

    def _move(self, req: p.MoveTask):
        tree, task = self._task(req.task_id)
        ptree, new_parent = self._task(req.new_parent_id)
        if ptree is not tree:
            raise OpError("cannot move a task to another tree")
        if task.parent is None:
            raise OpError("cannot move the root task")
        if new_parent.id in self._subtree(tree, task.id):
            raise OpError("cannot move a task under itself")
        tree.tasks[task.parent].children.remove(task.id)
        kids = new_parent.children
        kids.insert(len(kids) if req.index is None else req.index, task.id)
        task.parent = new_parent.id
        self.dirty_trees.add(tree.id)

    def _subtree(self, tree: Tree, tid: str) -> list[str]:
        out, stack = [], [tid]
        while stack:
            t = stack.pop()
            out.append(t)
            stack += tree.tasks[t].children
        return out

    def _status_warnings(self, tree: Tree, task: Task) -> list[str]:
        w = []
        if task.status in FINISHED:
            open_kids = [c for c in task.children if tree.tasks[c].status not in FINISHED]
            if open_kids:
                w.append(f"{task.id} is {task.status} but Subtasks still open: {', '.join(open_kids)}")
        if task.parent is not None:
            parent = tree.tasks[task.parent]
            if parent.status not in FINISHED and all(tree.tasks[c].status in FINISHED for c in parent.children):
                w.append(f"all Subtasks of {parent.id} finished; {parent.id} still {parent.status}")
            if parent.status in FINISHED and task.status not in FINISHED:
                w.append(f"{task.id} is open but parent {parent.id} is {parent.status}")
        return w

    # ---- periodic sweep ----

    def sweep(self, alive: Callable[[int, float], bool]) -> bool:
        """End dead Sessions, delete expired trees. Returns True if anything visible changed."""
        changed = False
        for s in list(self.sessions.values()):
            if not alive(s.pid, s.pid_start):
                self.end_session(s.id)
                changed = True
        for tree in list(self.trees.values()):
            if self._expired(tree):
                self._drop_tree(tree)
                changed = True
                continue
            lc = self.lifecycle(tree)
            if self._last_lifecycle.get(tree.id) != lc:
                self._last_lifecycle[tree.id] = lc
                changed = True
        return changed

    # ---- views ----

    def _task_view(self, tree: Tree, tid: str) -> p.TaskView:
        t = tree.tasks[tid]
        return p.TaskView(id=t.id, goal=t.goal, status=t.status,
                          children=[self._task_view(tree, c) for c in t.children])

    def tree_view(self, tree: Tree) -> p.TreeView:
        return p.TreeView(id=tree.id, project=tree.project, lifecycle=self.lifecycle(tree),
                          sessions=list(tree.sessions), root=self._task_view(tree, tree.id))

    def visible_trees(self) -> list[Tree]:
        return [t for t in self.trees.values() if self.lifecycle(t) != "hidden"]

    def snapshot(self) -> p.SnapshotView:
        return p.SnapshotView(
            trees=[self.tree_view(t) for t in self.visible_trees()],
            sessions=[p.SessionView(id=s.id, project=s.project, title=s.title,
                                    awaiting=s.awaiting, tree_id=s.tree_id)
                      for s in self.sessions.values()],
        )

    def glance(self) -> p.Glance:
        return p.Glance(
            live=len(self.sessions),
            awaiting=sum(s.awaiting for s in self.sessions.values()),
            blocked=sum(t.status == "blocked" for tr in self.visible_trees() for t in tr.tasks.values()),
        )
