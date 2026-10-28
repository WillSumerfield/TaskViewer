# TaskViewer (shared)

A lightweight, always-at-hand view of what live Claude sessions are trying to achieve, what they consider done, and what they plan next. Shared glossary for all contexts; see [CONTEXT-MAP](./CONTEXT-MAP.md).

## Language

**Task**:
A goal the user wants to accomplish, stated at the level of outcome, not method. Created by Claude from session context (typically a grilling session).
_Avoid_: Todo, job, step

**Subtask**:
A Task whose achievement is needed for its parent Task. Recursive; same nature as a Task, only narrower.
_Avoid_: Step, todo item

**Task tree**:
A root Task together with all its descendant Subtasks.

**Session**:
One running Claude conversation attached to a live terminal. Ceases to exist from the tool's view once no longer active in a terminal.
_Avoid_: Agent, conversation, instance

**Project**:
The git repository a Session runs in, or its starting directory if outside one; each worktree is its own Project. Every Task tree belongs to the Project it was created in, and Re-attach candidates are limited to that Project.
_Avoid_: Workspace, repo, cwd

**Awaiting user**:
A Session state: the Session is idle at a prompt or permission request, waiting on the user. Distinct from a Blocked Task.
_Avoid_: Blocked, idle

### Task status

**Planned**:
A Task Claude intends to pursue but has not started.

**Active**:
A Task Claude is currently pursuing.

**Done**:
A Task Claude considers achieved.

**Blocked**:
A Task that cannot progress without a user decision or input.
_Avoid_: Waiting, stuck

**Dropped**:
A Task abandoned or ruled out of scope; kept visible, not deleted.
_Avoid_: Cancelled, removed

### Task tree lifecycle

**Live**:
A Task tree with at least one active Session working on it. A tree may have many Sessions; Sessions attach to the tree as a whole, not to individual Tasks. A Session works on at most one tree at a time.

**Dormant**:
A Task tree whose last Session has left; still visible, awaiting re-attachment. Lasts 8 hours from when the last Session left.
_Avoid_: Stale, inactive, paused

**Hidden**:
A Task tree past its Dormant period; not shown, but still findable by new Sessions. Permanently deleted after 1 month Hidden.
_Avoid_: Archived

**Re-attach**:
A new Session claiming an existing Dormant or Hidden Task tree as the one it is working on, after confirming with the user.
_Avoid_: Resume
