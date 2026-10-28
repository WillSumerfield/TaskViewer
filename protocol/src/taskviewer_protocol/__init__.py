"""Messages exchanged between Plugin and App: one JSON object per line over localhost TCP."""

from typing import Any, Literal

import msgspec

Status = Literal["planned", "active", "done", "blocked", "dropped"]
Lifecycle = Literal["live", "dormant", "hidden"]
Topic = Literal["glance", "state"]

STATUSES: tuple[str, ...] = Status.__args__


# ---- Requests (tagged on "op") ----

class Request(msgspec.Struct, tag_field="op", kw_only=True, forbid_unknown_fields=True):
    id: int = 0


class RegisterSession(Request, tag="register_session"):
    session_id: str
    pid: int
    pid_start: float
    project: str
    title: str = ""


class EndSession(Request, tag="end_session"):
    session_id: str


class SetAwaiting(Request, tag="set_awaiting"):
    session_id: str
    awaiting: bool


class SetTitle(Request, tag="set_title"):
    session_id: str
    title: str


class CreateTree(Request, tag="create_tree"):
    session_id: str
    goal: str


class Attach(Request, tag="attach"):
    session_id: str
    tree_id: str


class Detach(Request, tag="detach"):
    session_id: str


class ListCandidates(Request, tag="list_candidates"):
    project: str


class GetTree(Request, tag="get_tree"):
    session_id: str | None = None
    tree_id: str | None = None


class AddTask(Request, tag="add_task"):
    parent_id: str
    goal: str
    status: Status = "planned"


class SetStatus(Request, tag="set_status"):
    task_id: str
    status: Status


class RenameTask(Request, tag="rename_task"):
    task_id: str
    goal: str


class MoveTask(Request, tag="move_task"):
    task_id: str
    new_parent_id: str
    index: int | None = None


class DeleteTask(Request, tag="delete_task"):
    task_id: str


class Snapshot(Request, tag="snapshot"):
    pass


class Subscribe(Request, tag="subscribe"):
    topics: list[Topic] = msgspec.field(default_factory=lambda: ["glance", "state"])


AnyRequest = (
    RegisterSession | EndSession | SetAwaiting | SetTitle | CreateTree | Attach | Detach
    | ListCandidates | GetTree | AddTask | SetStatus | RenameTask | MoveTask | DeleteTask
    | Snapshot | Subscribe
)


class Reply(msgspec.Struct, kw_only=True, omit_defaults=True):
    id: int
    ok: bool
    result: Any = None
    error: str | None = None
    warnings: list[str] = []


# ---- Views (results / event payloads) ----

class TaskView(msgspec.Struct, kw_only=True):
    id: str
    goal: str
    status: Status
    children: list["TaskView"] = []


class TreeView(msgspec.Struct, kw_only=True):
    id: str  # = root task id
    project: str
    lifecycle: Lifecycle
    sessions: list[str]
    root: TaskView


class SessionView(msgspec.Struct, kw_only=True):
    id: str
    project: str
    title: str
    awaiting: bool
    tree_id: str | None


class Candidate(msgspec.Struct, kw_only=True):
    tree_id: str
    goal: str
    lifecycle: Lifecycle


class Glance(msgspec.Struct, kw_only=True):
    live: int
    awaiting: int
    blocked: int


class SnapshotView(msgspec.Struct, kw_only=True):
    trees: list[TreeView]
    sessions: list[SessionView]


# ---- Push events (after subscribe; tagged on "event") ----

class Event(msgspec.Struct, tag_field="event", kw_only=True):
    pass


class GlanceEvent(Event, tag="glance"):
    glance: Glance


class StateEvent(Event, tag="state"):
    snapshot: SnapshotView


AnyEvent = GlanceEvent | StateEvent


# ---- Codec ----

_enc = msgspec.json.Encoder()
_req_dec = msgspec.json.Decoder(AnyRequest)
_reply_dec = msgspec.json.Decoder(Reply)
_event_dec = msgspec.json.Decoder(AnyEvent)


def encode(msg: msgspec.Struct) -> bytes:
    """Encode one message as a JSON line."""
    return _enc.encode(msg) + b"\n"


def decode_request(line: bytes) -> AnyRequest:
    return _req_dec.decode(line)


def decode_reply(line: bytes) -> Reply:
    return _reply_dec.decode(line)


def decode_event(line: bytes) -> AnyEvent:
    return _event_dec.decode(line)
