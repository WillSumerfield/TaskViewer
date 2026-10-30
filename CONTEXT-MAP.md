# Context Map

## Structure

```
 0 .
 1 ├── .agents
 2 │   └── plugins
 3 │       └── marketplace.json
 1 ├── app
 2 │   ├── CONTEXT.md
 2 │   ├── pyproject.toml
 2 │   ├── src
 3 │   │   └── taskviewer_app
 4 │   │       ├── __init__.py
 4 │   │       ├── liveness.py
 4 │   │       ├── main.py
 4 │   │       ├── __pycache__
 4 │   │       ├── server.py
 4 │   │       ├── state.py
 4 │   │       ├── storage.py
 4 │   │       ├── titles.py
 4 │   │       └── tvc.py
 2 │   └── tests
 3 │       ├── app_helpers.py
 3 │       ├── conftest.py
 3 │       ├── __pycache__
 3 │       ├── test_lifecycle.py
 3 │       ├── test_server.py
 3 │       ├── test_sessions.py
 3 │       ├── test_state.py
 3 │       ├── test_storage.py
 3 │       └── test_titles.py
 1 ├── board
 2 │   ├── CONTEXT.md
 2 │   ├── examples
 3 │   │   └── glance.ini
 2 │   ├── pyproject.toml
 2 │   ├── src
 3 │   │   └── taskviewer_board
 4 │   │       ├── config.py
 4 │   │       ├── control.py
 4 │   │       ├── feed.py
 4 │   │       ├── glance.py
 4 │   │       ├── __init__.py
 4 │   │       ├── layout.py
 4 │   │       ├── main.py
 4 │   │       ├── __pycache__
 4 │   │       ├── tray.py
 4 │   │       ├── winapi.py
 4 │   │       └── window.py
 2 │   └── tests
 3 │       ├── conftest.py
 3 │       ├── __pycache__
 3 │       ├── test_board_io.py
 3 │       ├── test_config.py
 3 │       ├── test_glance.py
 3 │       ├── test_layout.py
 3 │       └── test_session_rendering.py
 1 ├── .claude-plugin
 2 │   └── marketplace.json
 1 ├── CONTEXT-MAP.md
 1 ├── CONTEXT.md
 1 ├── .gitignore
 1 ├── plugin
 2 │   ├── claude-plugin
 3 │   │   ├── hooks
 4 │   │   │   ├── codex.json
 4 │   │   │   └── hooks.json
 3 │   │   └── skills
 4 │   │       └── taskviewer
 5 │   │           └── SKILL.md
 2 │   ├── pyproject.toml
 2 │   ├── src
 3 │   │   └── taskviewer_plugin
 4 │   │       ├── hook.py
 4 │   │       ├── __init__.py
 4 │   │       ├── mcp_server.py
 4 │   │       └── __pycache__
 2 │   └── tests
 3 │       ├── conftest.py
 3 │       ├── plugin_helpers.py
 3 │       ├── __pycache__
 3 │       └── test_plugin.py
 1 ├── protocol
 2 │   ├── pyproject.toml
 2 │   ├── src
 3 │   │   ├── taskviewer_client
 4 │   │   │   ├── __init__.py
 4 │   │   │   └── __pycache__
 3 │   │   └── taskviewer_protocol
 4 │   │       ├── __init__.py
 4 │   │       └── __pycache__
 2 │   └── tests
 3 │       ├── __pycache__
 3 │       └── test_codec.py
 1 ├── pyproject.toml
 1 ├── .pytest_cache
 1 ├── README.md
 1 ├── temp
 2 │   ├── commit-plan.md
 2 │   ├── design.md
 2 │   ├── phase1.md
 2 │   ├── phase2.md
 2 │   ├── phase3.md
 2 │   ├── phase4.md
 2 │   ├── phase5.md
 2 │   ├── reset_tree.md
 2 │   └── session-titles.md
 1 ├── uv.lock
 1 └── .venv
```

## Contexts

- [Shared glossary](./CONTEXT.md) — Task, Session, statuses, lifecycle terms used by every context
- [App](./app/CONTEXT.md) — always-running background program that holds all state
- [Board](./board/CONTEXT.md) — desktop views of the App's state: toggleable Board + Glance in the bar
- Plugin (`plugin/`) — Claude Code and Codex plugin: MCP tools, hooks and skill that let Sessions read and change their Task tree
- Protocol (`protocol/`) — message types exchanged between Plugin and App

## Relationships

- **Plugin → App**: Plugin sends individual Task changes and Session events (start, end, turns, Awaiting user); App applies them in arrival order. Plugin starts the App if it isn't running.
- **App → Plugin**: App answers Plugin reads of a Task tree and of Re-attach candidates in the same Project, and tells the Plugin when a Session's tree has gone stale.
- **App → Board**: Board and Glance subscribe to the App's state stream; read-only.
- **Plugin ↔ App**: both depend on Protocol for message shapes; neither depends on the other directly.
