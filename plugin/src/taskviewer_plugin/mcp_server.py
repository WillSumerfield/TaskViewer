"""MCP server: Claude's tools for reading and changing its Task tree.

Calls identify the Session by this server's parent pid (claude); the App walks up from it to the
most recent Session registered by that process, so /clear is followed.
"""

import os

import msgspec
from mcp.server.mcpserver import MCPServer

import taskviewer_protocol as p

from taskviewer_client import AppDown, call

PID = os.getppid()

mcp = MCPServer("taskviewer", instructions=(
    "Task tree of the user's goals for this Session, shown live in the TaskViewer App. "
    "Follow the taskviewer skill for when to create, attach and update."))


def _send(req: p.Request) -> tuple[object, list[str]]:
    try:
        reply = call(msgspec.to_builtins(req))
    except AppDown:
        raise RuntimeError("TaskViewer App not running")
    if not reply["ok"]:
        raise RuntimeError(reply["error"])
    return reply.get("result"), reply.get("warnings", [])


def _out(text: str, warnings: list[str]) -> str:
    return "\n".join([text, *(f"warning: {w}" for w in warnings)])


def render(tree: dict) -> str:
    lines = [f"tree {tree['id']} [{tree['lifecycle']}] Sessions: {len(tree['sessions'])}"]

    def walk(t: dict, depth: int):
        lines.append(f"{'  ' * depth}{t['id']} [{t['status']}] {t['goal']}")
        for c in t["children"]:
            walk(c, depth + 1)

    walk(tree["root"], 0)
    return "\n".join(lines)


@mcp.tool()
def get_tree(tree_id: str | None = None) -> str:
    """Show a Task tree (default: this Session's) as indented `id [status] goal` lines."""
    result, _ = _send(p.GetTree(pid=PID, tree_id=tree_id))
    return render(result)


@mcp.tool()
def list_candidates() -> str:
    """List other Task trees in this Project that this Session could Re-attach to."""
    result, _ = _send(p.ListCandidates(pid=PID))
    return "\n".join(f"{c['tree_id']} [{c['lifecycle']}] {c['goal']}" for c in result) or "no candidates"


@mcp.tool()
def create_tree(goal: str) -> str:
    """Create a Task tree whose root Task is the user's overall goal (2-5 words); attaches this Session to it."""
    result, w = _send(p.CreateTree(pid=PID, goal=goal))
    return _out(f"created tree {result['tree_id']}", w)


@mcp.tool()
def attach(tree_id: str) -> str:
    """Attach this Session to an existing tree (only after the user confirms). Returns the tree."""
    _, w = _send(p.Attach(pid=PID, tree_id=tree_id))
    result, _ = _send(p.GetTree(tree_id=tree_id))
    return _out(render(result), w)


@mcp.tool()
def detach() -> str:
    """Stop working on the current tree (it becomes Dormant if no other Session is on it)."""
    _, w = _send(p.Detach(pid=PID))
    return _out("detached", w)


@mcp.tool()
def add_task(parent_id: str, goal: str, status: p.Status = "planned") -> str:
    """Add a Subtask under parent_id. goal = an outcome, not a method; 2-5 words, never a sentence."""
    result, w = _send(p.AddTask(parent_id=parent_id, goal=goal, status=status))
    return _out(f"added {result['task_id']}", w)


@mcp.tool()
def set_status(task_id: str, status: p.Status) -> str:
    """Set a Task's status: planned, active, done, blocked (needs a user decision), dropped (out of scope)."""
    _, w = _send(p.SetStatus(task_id=task_id, status=status))
    return _out("ok", w)


@mcp.tool()
def rename_task(task_id: str, goal: str) -> str:
    """Restate a Task's goal (2-5 words)."""
    _, w = _send(p.RenameTask(task_id=task_id, goal=goal))
    return _out("ok", w)


@mcp.tool()
def move_task(task_id: str, new_parent_id: str, index: int | None = None) -> str:
    """Move a Task (with its Subtasks) under another Task in the same tree; index = position among siblings."""
    _, w = _send(p.MoveTask(task_id=task_id, new_parent_id=new_parent_id, index=index))
    return _out("ok", w)


@mcp.tool()
def delete_task(task_id: str) -> str:
    """Delete a Task and its Subtasks (root = whole tree). Only for mistakes; use status dropped for scope cuts."""
    _, w = _send(p.DeleteTask(task_id=task_id))
    return _out("deleted", w)


@mcp.tool()
def set_awaiting() -> str:
    """Call right before ending a turn that asks the user a question you need answered to continue."""
    _, w = _send(p.SetAwaiting(pid=PID))
    return _out("ok", w)


def main():
    mcp.run()
