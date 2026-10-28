import pytest

import taskviewer_protocol as p
from taskviewer_app.state import State


class FakeClock:
    def __init__(self, t: float = 1000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, secs: float):
        self.t += secs


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def state(clock):
    return State(clock)


def register(state: State, sid: str = "s1", project: str = "/proj", pid: int = 100, pid_start: float = 1.0):
    state.apply(p.RegisterSession(session_id=sid, pid=pid, pid_start=pid_start, project=project))


def make_tree(state: State, sid: str = "s1", goal: str = "root") -> str:
    result, _ = state.apply(p.CreateTree(session_id=sid, goal=goal))
    return result["tree_id"]


def add(state: State, parent: str, goal: str = "sub", status: str = "planned") -> str:
    result, _ = state.apply(p.AddTask(parent_id=parent, goal=goal, status=status))
    return result["task_id"]
