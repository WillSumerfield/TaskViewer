"""Claude/Codex hook: `taskviewer-hook <event> [--provider codex]`, JSON on stdin. Stdlib only.

Hook connection/input errors never block the assistant.
"""

import json
import os
import platform
import shutil
import subprocess
import sys

from taskviewer_client import AppDown, call, call_or_start

AWAIT_NOTIFICATIONS = ("permission_prompt", "elicitation_dialog")
SILENT = ("Act on this note silently: update the tree with the tools, but don't mention TaskViewer, "
          "the note or the tree update in your reply (asking before a Re-attach is the only exception).")


TITLE_NOTE = ("Set a concise Session title with set_session_title as soon as the goal is clear, "
              "even before creating a tree. Use 2-5 words (max 60 characters), omit skill invocations "
              "and conversational wording, and update it when the goal changes. Explicit titles are preserved.")


def project_of(cwd: str) -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=cwd,
                             capture_output=True, text=True, timeout=2)
        if out.returncode == 0 and out.stdout.strip():
            return os.path.normpath(out.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    return os.path.normpath(cwd)


def host_pid(provider: str) -> int:
    key = "CODEX_PID" if provider == "codex" else "CLAUDE_PID"
    return int(os.environ.get(key) or os.getppid())


def register(h: dict, provider: str = "claude") -> dict:
    request = {"op": "register_session", "session_id": h["session_id"], "pid": host_pid(provider),
                          "project": project_of(h.get("cwd") or os.getcwd()),
                          "transcript_path": h.get("transcript_path") or ""}
    if provider == "codex":
        request["shared_process"] = True
    return call_or_start(request)


def ensure_board():
    """Windows has no i3 exec: start the Board (and its tray Glance) if none answers. Needs taskviewer-board."""
    try:
        from taskviewer_board.control import send
    except ImportError:
        return
    if not send("ping"):
        subprocess.Popen(["taskviewer-boardw"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,
                         creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)


def in_wsl() -> bool:
    return sys.platform == "linux" and "microsoft" in platform.release().lower()


def ensure_windows_board():
    """From WSL: launch the Windows Board through interop. It can't ping the Windows pipe, so always launch;
    a second Board exits by itself."""
    if exe := shutil.which("taskviewer-boardw.exe"):
        subprocess.Popen([exe], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)


def start_note(result: dict) -> str:
    lines = ["TaskViewer is on: keep a Task tree of the user's goals with the taskviewer MCP tools "
             "(rules: taskviewer skill)."]
    if result.get("tree_id"):
        lines.append(f"This Session is attached to tree {result['tree_id']} (resumed); "
                     "call get_tree before continuing.")
    cands = result.get("candidates") or []
    if cands:
        lines.append("Existing trees in this Project (Re-attach candidates):")
        lines += [f"  {c['tree_id']} [{c['lifecycle']}] {c['goal']}" for c in cands]
        if not result.get("tree_id"):
            lines.append("If the user's goal matches one, ask the user before attaching.")
    return "\n".join(lines)


def remind_note(tree_id: str | None) -> str:
    if tree_id:
        return (f"TaskViewer: tree {tree_id} hasn't changed in several working turns. "
                "If progress or the plan changed, update Task statuses/Subtasks.")
    return ("TaskViewer: no Task tree yet after several working turns. "
            "If the user's goal is clear, create one (or attach to a matching candidate).")


def context(event: str, text: str):
    text += f"\n{TITLE_NOTE}\n{SILENT}"
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}))


def handle(event: str, h: dict, provider: str = "claude"):
    sid = h["session_id"]
    match event:
        case "session-start":
            reply = register(h, provider)
            if reply.get("ok"):
                note = start_note(reply["result"])
                if provider == "codex":
                    note += (f"\nYour TaskViewer session_id is {json.dumps(sid)}. Pass this exact session_id "
                             "to every session-scoped taskviewer tool; never infer identity from a PID.")
                context("SessionStart", note)
            if sys.platform == "win32":
                ensure_board()
            elif in_wsl():
                ensure_windows_board()
        case "prompt":
            msg = {"op": "prompt_submitted", "session_id": sid}
            if provider == "codex":
                words = [w for w in (h.get("prompt") or "").split() if not w.startswith(("$", "/"))]
                msg["title"] = " ".join(words[:5])[:60]
            reply = call_or_start(msg)
            if not reply.get("ok") and "unknown session" in reply.get("error", ""):
                register(h, provider)  # App lost the Session; join now
                reply = call(msg)
            if reply.get("ok") and reply["result"]["remind"]:
                context("UserPromptSubmit", remind_note(reply["result"]["tree_id"]))
            elif provider == "codex":
                # Refresh identity each turn, including installs mid-Session.
                context("UserPromptSubmit", f"TaskViewer session_id: {json.dumps(sid)}. "
                        "Pass it to session-scoped taskviewer tools.")
        case "tool-start":
            tool = h.get("tool_name", "").rsplit(".", 1)[-1]
            activity = "awaiting" if tool in ("request_user_input", "AskUserQuestion") else "working"
            call({"op": "set_activity", "session_id": sid, "activity": activity})
        case "tool":
            call({"op": "tool_used", "session_id": sid})
        case "ask":
            # Older installed Codex hook definitions still send these events here.
            # Approval checks may be automatic; async questions do not stop work.
            if provider == "codex" and (h.get("hook_event_name") == "PermissionRequest"
                                        or h.get("tool_name", "").endswith("request_user_input_async")):
                return
            call({"op": "set_activity", "session_id": sid, "activity": "awaiting"})
        case "notify":
            if h.get("notification_type") in AWAIT_NOTIFICATIONS:
                call({"op": "set_activity", "session_id": sid, "activity": "awaiting"})
        case "stop":
            call({"op": "turn_ended", "session_id": sid})
        case "end":
            call({"op": "end_session", "session_id": sid})


def main():
    provider = "codex" if sys.argv[2:] == ["--provider", "codex"] else "claude"
    try:
        handle(sys.argv[1], json.load(sys.stdin), provider)
    except (AppDown, KeyError, IndexError, ValueError, OSError):
        pass
    finally:
        if provider == "codex" and sys.argv[1] == "stop":
            print("{}")  # Codex Stop expects JSON; never request a continuation.
