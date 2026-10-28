# Context Map

## Structure

```
 0 .
 1 ├── app
 2 │   ├── CONTEXT.md
 2 │   ├── src/taskviewer_app             ← state, lifecycle, storage, server, tvc
 2 │   └── tests
 1 ├── .claude-plugin/marketplace.json     ← local plugin marketplace
 1 ├── board                               ← Board (PySide6), separate process
 1 ├── CONTEXT.md                          ← shared glossary
 1 ├── CONTEXT-MAP.md
 1 ├── plugin
 2 │   ├── claude-plugin                  ← installable plugin: hooks, .mcp.json, skill (config only)
 2 │   ├── src/taskviewer_plugin          ← hook, MCP server, stdlib App client
 2 │   └── tests
 1 ├── protocol
 2 │   ├── src/taskviewer_protocol        ← message types + codec
 2 │   └── tests
 1 ├── pyproject.toml                      ← uv workspace root
 1 └── temp                                ← design + phase plans
```

## Contexts

- [Shared glossary](./CONTEXT.md) — Task, Session, statuses, lifecycle terms used by every context
- [App](./app/CONTEXT.md) — always-running background program that holds all state; shows the Glance
- [Board](./board/CONTEXT.md) — separate desktop process showing the App's state, toggled on demand
- Plugin (`plugin/`) — Claude Code plugin: MCP tools, hooks and skill that let Sessions read and change their Task tree
- Protocol (`protocol/`) — message types exchanged between Plugin and App

## Relationships

- **Plugin → App**: Plugin sends individual Task changes and Session events (start, end, turns, Awaiting user); App applies them in arrival order. Plugin starts the App if it isn't running.
- **App → Plugin**: App answers Plugin reads of a Task tree and of Re-attach candidates in the same Project, and tells the Plugin when a Session's tree has gone stale.
- **App → Board**: Board subscribes to the App's state stream; read-only.
- **Plugin ↔ App**: both depend on Protocol for message shapes; neither depends on the other directly.
