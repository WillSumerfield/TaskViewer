# Context Map

## Structure

```
 0 .
 1 ├── app
 2 │   ├── CONTEXT.md
 2 │   ├── src/taskviewer_app             ← state, lifecycle, storage, server, tvc
 2 │   └── tests
 1 ├── CONTEXT.md                          ← shared glossary
 1 ├── CONTEXT-MAP.md
 1 ├── protocol
 2 │   ├── src/taskviewer_protocol        ← message types + codec
 2 │   └── tests
 1 ├── pyproject.toml                      ← uv workspace root
 1 └── temp                                ← design + phase plans
```

## Contexts

- [Shared glossary](./CONTEXT.md) — Task, Session, statuses, lifecycle terms used by every context
- [App](./app/CONTEXT.md) — always-running program that holds all state and shows the Glance and Board
- Plugin (`plugin/`, not yet created) — Claude Code plugin: MCP tools, hooks and skill that let Sessions read and change their Task tree
- Protocol (`protocol/`) — message types exchanged between Plugin and App

## Relationships

- **Plugin → App**: Plugin sends individual Task changes and Session events (start, end, Awaiting user); App applies them in arrival order.
- **App → Plugin**: App answers Plugin reads of a Task tree and of Re-attach candidates in the same Project.
- **Plugin ↔ App**: both depend on Protocol for message shapes; neither depends on the other directly.
