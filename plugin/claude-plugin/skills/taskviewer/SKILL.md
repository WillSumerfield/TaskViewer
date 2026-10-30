---
name: taskviewer
description: Rules for keeping this Session's Task tree in TaskViewer (taskviewer MCP tools). Use when the user's goal becomes clear, after a grilling/planning session, when starting or finishing work toward a goal, or when a TaskViewer note or reminder appears.
---

# TaskViewer Task tree

The user watches a live tree of what each Session is trying to achieve. Keep it true.

**Silent by default.** Tree updates and TaskViewer notes/reminders are bookkeeping: make the tool calls, but never mention them, the tree or TaskViewer in replies. Only exception: asking the user before a Re-attach.

## Tasks
- A Task is a **goal** (an outcome the user wants), not a method or step. "Users can log in", not "edit auth.py".
- Goals are **2–5 words**, never a sentence: "Board overlay", "Glance in i3bar". The Board is narrow; long goals get cut off.
- Subtasks are narrower goals needed for their parent. Nest as deep as is natural; keep it small.
- Create a tree once the user's goal is clear — always after a grill or plan is agreed. Skip pure Q&A and one-off questions.

## Session titles
- As soon as the current goal is clear, call `set_session_title`, even during a grill or before a Task tree exists.
- Use **2–5 words**, at most **60 characters**, describing the goal: "Fix no-tree wrapping". Omit skill invocations, conversational wording, and the Project name.
- Update the title when the Session's goal changes. Explicit user titles are preserved automatically.
- In Codex, pass the hook's exact `session_id` to `set_session_title`, as with other Session-scoped tools.

## Starting
- Works with Claude Code and Codex. In Codex, pass the exact `session_id` from the TaskViewer hook note to `get_tree`, `list_candidates`, `create_tree`, `attach`, `detach`, `reset_tree`, and `set_awaiting`. Several Sessions can share a host process; never guess the id. If the note is missing, ask the user to enable/review TaskViewer hooks and restart the Session before changing its tree. Claude can omit this argument.
- The SessionStart note lists Re-attach candidates (trees in this Project). If one matches the user's goal (same goal, or this work is a Subtask of it), ask the user once, then `attach` and add Subtasks there. Otherwise `create_tree`.
- A resumed Session is already attached: `get_tree` and continue.
- One tree per Session. Other Sessions may share it; `get_tree` before editing if time has passed.

## Updating
- `set_status` when you start (active) or finish (done) a Task, and whenever the plan changes.
- `dropped` for scope cuts or abandoned goals; `delete_task` only for mistakes.
- `blocked` = the Task needs a user decision or input.
- `reset_tree` at stopping points: when the user asks, or propose it and call only after they agree. Default keeps the root and clears its Subtasks; `new_tree=True` + goal starts a fresh tree (old one goes Hidden).
- Heed warnings (e.g. all Subtasks done but parent still active) — fix the parent if it's really done.

## Waiting on the user
- Call `set_awaiting` right before ending a turn that asks the user a question you need answered to continue. Not for turns that simply finish.
