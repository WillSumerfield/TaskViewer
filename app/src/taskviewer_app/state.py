"""In-memory Task trees + Sessions, and the rules for changing them."""

import time
from collections.abc import Callable

import msgspec

import taskviewer_protocol as p

from .liveness import ancestors, process_start

DORMANT_SECS = 8 * 3600
HIDDEN_SECS = 30 * 24 * 3600
FINISHED = ("done", "dropped")
STALE_TURNS = 5  # working turns without a tree change before reminding
MAX_CANDIDATES = 10
_LC_ORDER = {"live": 0, "dormant": 1, "hidden": 2}


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
    transcript_path: str = ""
    title: str = ""
    activity: p.Activity = "idle"  # until the first prompt
    tree_id: str | None = None
    # turn bookkeeping (stale-tree reminder, set_awaiting)
    ask_pending: bool = False
    used_tools: bool = False
    touched: bool = False
    stale_turns: int = 0


class State:
    def __init__(self, clock: Callable[[], float] = time.time,
                 proc_start: Callable[[int], float] = process_start,
                 ancestors: Callable[[int], list[int]] = ancestors):
        self.clock = clock
        self.proc_start = proc_start
        self.ancestors = ancestors
        self.trees: dict[str, Tree] = {}
        self.sessions: dict[str, Session] = {}
        self.pid_session: dict[int, str] = {}  # pid -> most recent Session it registered
        self.last_tree: dict[str, str] = {}  # ended Session id -> its tree (for resume)
        self.task_tree: dict[str, str] = {}  # task id -> tree id
        self.next_id = 1
        # Change tracking for storage
        self.dirty_trees: set[str] = set()
        self.deleted_trees: set[str] = set()
        self.sessions_dirty = False
        self._last_lifecycle: dict[str, p.Lifecycle] = {}

    # ---- loading ----

    def load(self, trees: list[Tree], sessions: list[Session], next_id: int,
             last_tree: dict[str, str] | None = None):
        self.trees = {t.id: t for t in sorted(trees, key=lambda t: int(t.id[1:]))}
        self.sessions = {s.id: s for s in sessions}
        self.pid_session = {s.pid: s.id for s in sessions}  # saved in registration order
        self.last_tree = dict(last_tree or {})
        self.task_tree = {tid: t.id for t in trees for tid in t.tasks}
        self.next_id = next_id
        self._last_lifecycle = {t.id: self.lifecycle(t) for t in trees}

    # ---- lookups ----

    def _session(self, sid: str) -> Session:
        if sid not in self.sessions:
            raise OpError(f"unknown session {sid}")
        return self.sessions[sid]

    def _who(self, req: p.Who) -> Session:
        if req.session_id is not None:
            return self._session(req.session_id)
        if req.pid is None:
            raise OpError("give session_id or pid")
        for pid in [req.pid, *self.ancestors(req.pid)]:
            sid = self.pid_session.get(pid)
            if sid in self.sessions:
                return self.sessions[sid]
        raise OpError("no Session for this process (is the TaskViewer hook installed?)")

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
        s.touched = True
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
        self.last_tree = {k: v for k, v in self.last_tree.items() if v != tree.id}
        self.sessions_dirty = True
        self._last_lifecycle.pop(tree.id, None)
        self.dirty_trees.discard(tree.id)
        self.deleted_trees.add(tree.id)

    # ---- dispatch ----

    def apply(self, req: p.AnyRequest) -> tuple[object, list[str]]:
        """Apply one request. Returns (result, warnings); raises OpError."""
        warnings: list[str] = []
        match req:
            case p.RegisterSession():
                return self._register(req), warnings
            case p.EndSession():
                self.end_session(req.session_id)
                return None, warnings
            case p.SetActivity():
                self._session(req.session_id).activity = req.activity
                self.sessions_dirty = True
                return None, warnings
            case p.SetAwaiting():
                self._who(req).ask_pending = True
                return None, warnings
            case p.PromptSubmitted():
                s = self._session(req.session_id)
                s.activity, s.ask_pending = "working", False
                remind = s.stale_turns >= STALE_TURNS
                if remind:
                    s.stale_turns = 0
                self.sessions_dirty = True
                return {"remind": remind, "tree_id": s.tree_id}, warnings
            case p.ToolUsed():
                s = self._session(req.session_id)
                s.used_tools = True
                if s.activity != "working":
                    s.activity = "working"
                    self.sessions_dirty = True
                return None, warnings
            case p.TurnEnded():
                s = self._session(req.session_id)
                if s.used_tools:
                    s.stale_turns = 0 if s.touched else s.stale_turns + 1
                s.used_tools = s.touched = False
                s.activity = "awaiting" if s.ask_pending else "idle"
                self.sessions_dirty = True
                return None, warnings
            case p.SetTitle():
                self._session(req.session_id).title = req.title
                self.sessions_dirty = True
                return None, warnings
            case p.CreateTree():
                s = self._who(req)
                rid = self._new_id()
                tree = Tree(id=rid, project=s.project,
                            tasks={rid: Task(id=rid, goal=req.goal, status="active", parent=None)})
                self.trees[rid] = tree
                self.task_tree[rid] = rid
                self._attach(s, tree)
                return {"tree_id": rid}, warnings
            case p.Attach():
                s = self._who(req)
                tree = self._tree(req.tree_id)
                if tree.project != s.project:
                    raise OpError(f"tree {tree.id} belongs to project {tree.project}")
                self._attach(s, tree)
                return None, warnings
            case p.Detach():
                self._detach(self._who(req))
                return None, warnings
            case p.ListCandidates():
                if req.project is not None:
                    return self._candidates(req.project), warnings
                s = self._who(req)
                return self._candidates(s.project, exclude=s.tree_id), warnings
            case p.GetTree():
                if req.tree_id:
                    tree = self._tree(req.tree_id)
                else:
                    s = self._who(req)
                    if s.tree_id is None:
                        raise OpError(f"session {s.id} has no tree")
                    tree = self.trees[s.tree_id]
                return self.tree_view(tree), warnings
            case p.AddTask():
                tree, parent = self._task(req.parent_id)
                tid = self._new_id()
                tree.tasks[tid] = Task(id=tid, goal=req.goal, status=req.status, parent=parent.id)
                parent.children.append(tid)
                self.task_tree[tid] = tree.id
                self._touch(tree)
                warnings += self._status_warnings(tree, tree.tasks[tid])
                return {"task_id": tid}, warnings
            case p.SetStatus():
                tree, task = self._task(req.task_id)
                task.status = req.status
                self._touch(tree)
                warnings += self._status_warnings(tree, task)
                return None, warnings
            case p.RenameTask():
                tree, task = self._task(req.task_id)
                task.goal = req.goal
                self._touch(tree)
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
                self._touch(tree)
                return None, warnings
            case p.Snapshot():
                return self.snapshot(), warnings
        raise OpError(f"unsupported op {type(req).__name__}")

    def _touch(self, tree: Tree):
        """A tree changed: save it, and reset the stale count of its Sessions."""
        self.dirty_trees.add(tree.id)
        for sid in tree.sessions:
            self.sessions[sid].touched = True

    def _register(self, req: p.RegisterSession) -> dict:
        old = self.sessions.get(req.session_id)
        if req.pid_start is not None:
            start = req.pid_start
        else:
            try:
                start = self.proc_start(req.pid)
            except Exception:
                raise OpError(f"no process {req.pid}")
        # one claude process runs one Session at a time (/clear starts a new one)
        for other in [o for o in self.sessions.values() if o.pid == req.pid and o.id != req.session_id]:
            self.end_session(other.id)
        s = Session(id=req.session_id, pid=req.pid, pid_start=start, project=req.project,
                    transcript_path=req.transcript_path,
                    title=req.title or (old.title if old else ""),
                    tree_id=old.tree_id if old else None)
        self.sessions[s.id] = s
        self.pid_session[s.pid] = s.id
        self.sessions_dirty = True
        last = self.trees.get(self.last_tree.pop(s.id, ""))
        if s.tree_id is None and last is not None and last.project == s.project:
            self._attach(s, last)  # resumed Session returns to its tree
        return {"tree_id": s.tree_id, "candidates": self._candidates(s.project, exclude=s.tree_id)}

    def _candidates(self, project: str, exclude: str | None = None) -> list[p.Candidate]:
        trees = [t for t in self.trees.values() if t.project == project and t.id != exclude]
        trees.sort(key=lambda t: (_LC_ORDER[self.lifecycle(t)], -(t.last_left_at or 0), -int(t.id[1:])))
        return [p.Candidate(tree_id=t.id, goal=t.tasks[t.id].goal, lifecycle=self.lifecycle(t))
                for t in trees[:MAX_CANDIDATES]]

    def end_session(self, sid: str):
        s = self._session(sid)
        if s.tree_id is not None:
            self.last_tree[sid] = s.tree_id
        self._detach(s)
        del self.sessions[sid]
        if self.pid_session.get(s.pid) == sid:
            del self.pid_session[s.pid]
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
        self._touch(tree)

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
                                    activity=s.activity, tree_id=s.tree_id)
                      for s in self.sessions.values()],
        )

    def glance(self) -> p.Glance:
        return p.Glance(
            live=len(self.sessions),
            awaiting=sum(s.activity == "awaiting" for s in self.sessions.values()),
            blocked=sum(t.status == "blocked" for tr in self.visible_trees() for t in tr.tasks.values()),
        )
