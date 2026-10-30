# TaskViewer (shared)

A lightweight, always-at-hand view of what live Claude Code and Codex sessions are trying to achieve, what they consider done, and what they plan next. Shared glossary for all contexts; see [CONTEXT-MAP](./CONTEXT-MAP.md).

## Language

**Task**:
A goal the user wants to accomplish, stated at the level of outcome, not method. Created by the assistant from session context (typically a grilling session).
_Avoid_: Todo, job, step

**Subtask**:
A Task whose achievement is needed for its parent Task. Recursive; same nature as a Task, only narrower.
_Avoid_: Step, todo item

**Task tree**:
A root Task together with all its descendant Subtasks.

**Session**:
One active Claude Code or Codex conversation. A host may run several Sessions at once. Ending the conversation ends its Session; clearing starts a new Session, and resuming an old conversation brings its Session back.
_Avoid_: Agent, conversation, instance

**Session title**:
A short name for a Session's current goal, which can change as the goal changes. A title explicitly chosen by the user takes priority over an assistant's suggestion. Distinct from a Task's goal: a Session can have a title before it has a Task tree.

**Project**:
The git repository a Session runs in, or its starting directory if outside one; each worktree is its own Project. Every Task tree belongs to the Project it was created in, and Re-attach candidates are limited to that Project.
_Avoid_: Workspace, repo, cwd

**Awaiting user**:
A Session state: the Session cannot continue until the user answers, either a permission request or a question the assistant has put to the user. The assistant judges the latter; a Session that has simply finished its turn is not Awaiting user. Distinct from a Blocked Task.
_Avoid_: Blocked, waiting

**Idle**:
A Session state: the Session has finished its turn and is not Awaiting user.
_Avoid_: Done, finished, waiting

### Task status

**Planned**:
A Task the assistant intends to pursue but has not started.

**Active**:
A Task the assistant is currently pursuing.

**Done**:
A Task the assistant considers achieved.

**Blocked**:
A Task that cannot progress without a user decision or input.
_Avoid_: Waiting, stuck

**Dropped**:
A Task abandoned or ruled out of scope; kept visible, not deleted.
_Avoid_: Cancelled, removed

### Task tree lifecycle

**Live**:
A Task tree with at least one active Session working on it. A tree may have many Sessions; Sessions attach to the tree as a whole, not to individual Tasks. A Session works on at most one tree at a time.

**Hidden**:
A Task tree whose last Session has left; not shown, but still findable by new Sessions. Permanently deleted after 1 month Hidden.
_Avoid_: Archived, Dormant, stale

**Reset**:
Clearing a Session's Task tree in one action, at a stopping point, when the user asks or agrees. Two forms: keep the root Task and remove all its Subtasks (other Sessions on the tree see it too), or leave the tree (it goes Hidden if no other Session remains) and start a new tree with a new root.
_Avoid_: Clear, wipe, restart

**Re-attach**:
A Session claiming an existing Hidden Task tree as the one it is working on, after confirming with the user. A resumed Session returns to its previous tree without asking.
_Avoid_: Resume
