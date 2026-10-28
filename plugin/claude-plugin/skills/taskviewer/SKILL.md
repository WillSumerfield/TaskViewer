---
name: taskviewer
description: Rules for keeping this Session's Task tree in TaskViewer (taskviewer MCP tools). Use when the user's goal becomes clear, after a grilling/planning session, when starting or finishing work toward a goal, or when a TaskViewer note or reminder appears.
---

# TaskViewer Task tree

The user watches a live tree of what each Session is trying to achieve. Keep it true.

## Tasks
- A Task is a **goal** (an outcome the user wants), not a method or step. "Users can log in", not "edit auth.py".
- Subtasks are narrower goals needed for their parent. Nest as deep as is natural; keep it small.
- Create a tree once the user's goal is clear — always after a grill or plan is agreed. Skip pure Q&A and one-off questions.

## Starting
- The SessionStart note lists Re-attach candidates (trees in this Project). If one matches the user's goal (same goal, or this work is a Subtask of it), ask the user once, then `attach` and add Subtasks there. Otherwise `create_tree`.
- A resumed Session is already attached: `get_tree` and continue.
- One tree per Session. Other Sessions may share it; `get_tree` before editing if time has passed.

## Updating
- `set_status` when you start (active) or finish (done) a Task, and whenever the plan changes.
- `dropped` for scope cuts or abandoned goals; `delete_task` only for mistakes.
- `blocked` = the Task needs a user decision or input.
- Heed warnings (e.g. all Subtasks done but parent still active) — fix the parent if it's really done.

## Waiting on the user
- Call `set_awaiting` right before ending a turn that asks the user a question you need answered to continue. Not for turns that simply finish.
