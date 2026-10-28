# TaskViewer

See what every Claude Code Session is working on, at a glance.

Each Session keeps a **Task tree**: its goal broken into Subtasks, each marked Planned, Active, Done, Blocked or Dropped. TaskViewer shows all trees in two places:

- **Board**: a small overlay with every tree, grouped by Project. Show or hide it with a hotkey. It never steals focus.
- **Glance**: a one-line summary that is always visible (polybar on Linux, a tray icon on Windows), e.g. `Tasks: ●3 live  ⚠1 awaiting`.

```
 ── TaskViewer ──────────────────────
 ⚠ Create task app
   ✓ Claude task plugin
   ● App display
       ○ Glance
 ── No tree ─────────────────────────
   ◦ quick question     scratch
```

`○` Planned · `●` Active · `✓` Done · `⧖` Blocked · `✗` Dropped · `⚠` waiting for you

## Contents

- [Requirements](#requirements)
- [Install](#install)
- [Setup](#setup)
  - [Linux (i3)](#linux-i3)
  - [Windows](#windows)
  - [WSL](#wsl)
  - [How it works](#how-it-works)
- [Config](#config)
- [Troubleshooting](#troubleshooting)
- [Development](#development)

## Requirements

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Claude Code
- One of:
  - Linux with i3 (polybar and picom are optional)
  - Windows 10/11
  - Windows with WSL2

## Install

Run this where Claude Code runs (Linux, Windows or inside WSL), from the repo folder:

```sh
uv tool install -e ./plugin --with-editable ./app --with-editable ./protocol --with-editable ./board \
  --with-executables-from taskviewer-app --with-executables-from taskviewer-board --force
```

On Windows PowerShell, put it on one line. Make sure uv's tool folder is on your PATH: run `uv tool update-shell` once, then open a new terminal.

Then add the Claude Code plugin:

```sh
claude plugin marketplace add /path/to/TaskViewer
claude plugin install taskviewer@taskviewer
```

Start a new Claude Session; tracking now works. The next section sets up the views for your system.

## Setup

### Linux (i3)

Add to `~/.config/i3/config`, then restart i3 (`$mod+Shift+r`):

```
for_window [class="TaskViewer"] floating enable, sticky enable, border none
no_focus [class="TaskViewer"]
bindsym $mod+t exec --no-startup-id taskviewer-board toggle
bindsym $mod+Shift+t exec --no-startup-id taskviewer-board collapse
bindsym $mod+Ctrl+t exec --no-startup-id taskviewer-board reload
exec --no-startup-id taskviewer-board
exec_always --no-startup-id taskviewer-board reload
```

| Key | Does |
|---|---|
| `$mod+t` | show / hide the Board |
| `$mod+Shift+t` | collapse / expand all trees |
| `$mod+Ctrl+t` | reload the Board config |

**Rounded corners and transparency** need a compositor: `sudo apt install picom`, then add `exec --no-startup-id picom` to the i3 config.

**Glance in polybar:** paste `board/examples/glance.ini` into your polybar config and add `taskviewer` to a bar's modules (e.g. `modules-center`). Left click toggles the Board; right click collapses it.

### Windows

Nothing else to do. The first Claude Session starts the Board, and a dot appears in the tray showing the Session count.

| Action | Does |
|---|---|
| `Ctrl+Alt+T` or left-click the tray dot | show / hide the Board |
| `Ctrl+Alt+Shift+T` | collapse / expand all trees |
| `Ctrl+Alt+R` | reload the Board config |
| Right-click the tray dot | menu: collapse, reload, quit |

The dot is blue normally, yellow when a Session is waiting for you, amber when a Task is Blocked, and grey when the App isn't running. Hover over it to see the counts.

**Start at login (optional):** press `Win+R`, type `shell:startup`, and add a shortcut to `taskviewer-boardw` (in uv's tool folder, usually `%USERPROFILE%\.local\bin`). It runs the Board without a console window.

**Font (optional):** install [JetBrains Mono](https://www.jetbrains.com/lp/mono/) for the same look as on Linux; otherwise Consolas is used.

### WSL

For when Claude Code runs inside WSL. The App and plugin run in WSL; the Board and tray run on Windows and connect to the WSL App, so you get the same hotkeys and tray as native Windows.

You install TaskViewer twice: once inside WSL (for the App and plugin) and once on Windows (for the Board and tray). Each needs its own copy of the repo.

**1. Inside WSL** (a WSL terminal):

```sh
curl -LsSf https://astral.sh/uv/install.sh | sh     # install uv (skip if you have it)
git clone https://github.com/WillSumerfield/TaskViewer.git ~/TaskViewer && cd ~/TaskViewer
uv tool install -e ./plugin --with-editable ./app --with-editable ./protocol --with-editable ./board \
  --with-executables-from taskviewer-app --with-executables-from taskviewer-board --force
claude plugin marketplace add ~/TaskViewer
claude plugin install taskviewer@taskviewer
```

**2. On Windows** (PowerShell, a new window):

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"   # install uv (skip if you have it)
git clone https://github.com/WillSumerfield/TaskViewer.git $HOME\TaskViewer; cd $HOME\TaskViewer
uv tool install -e ./plugin --with-editable ./app --with-editable ./protocol --with-editable ./board --with-executables-from taskviewer-app --with-executables-from taskviewer-board --force
uv tool update-shell
```

Clone onto the Windows drive, not into WSL: an editable install from a `\\wsl.localhost` path is slow and fragile. The Claude plugin isn't needed on Windows.

**3. Point the Windows Board at the WSL App.** In WSL, run `printf '%s\n' "//wsl.localhost/$WSL_DISTRO_NAME$HOME/.local/state/taskviewer" | tr / '\\'` to print the path. Then, on Windows, create `%APPDATA%\taskviewer\board.toml` with that path in single quotes:

```toml
app_state_dir = '\\wsl.localhost\Ubuntu\home\me\.local\state\taskviewer'
```

**4. Check that WSL can launch the Board.** Close and reopen the WSL terminal, then run `which taskviewer-boardw.exe`. It should print a `/mnt/c/...` path, because WSL adds the Windows PATH. If it prints nothing, open a new terminal after step 2 (so `uv tool update-shell` applies), or check that `appendWindowsPath` isn't turned off in `/etc/wsl.conf`.

**5. Start a Claude Session in WSL.** Its hook starts the App in WSL and the Board on Windows, and the tray dot appears.

Notes:
- With `app_state_dir` set, the Board never starts an App itself. The Sessions in WSL start the WSL App, and until then the tray stays grey.
- The Board shows one App. If you also run Claude natively on Windows, those Sessions use a separate Windows App that this Board won't show.
- This relies on WSL2 forwarding localhost (the default). If the tray stays grey while Sessions run, check that `localhostForwarding` isn't turned off in `.wslconfig`.

### How it works

```
 Claude Code Session ──hooks + tools──▶ App ──live updates──▶ Board / Glance
   (plugin)                             (state, saved to disk)  (read-only views)
```

- **App:** a small background program that holds every Task tree and Session and saves them to disk. Hooks start it when it isn't running. It talks over a localhost TCP port and writes that port to its state folder.
- **Plugin:** what Claude Code loads. It has three parts:
  - **Tools:** let Claude create and update its tree.
  - **Hooks:** report Session events (started, waiting for you, ended) and remind Claude when its tree looks stale.
  - **Skill:** tells Claude when to keep a tree.
- **Board and Glance:** subscribe to the App and redraw whenever something changes. They never edit anything. Hotkeys reach the running Board through a small local channel: a Unix socket on Linux, a named pipe on Windows.
- **Sessions:**
  - A Session counts as live while its Claude process runs.
  - When a tree's last Session leaves, the tree is hidden from the Board straight away, and deleted a month later.
  - A new Session in the same Project is offered the old tree to pick up again.

## Config

The config file is optional:
- Linux and WSL: `~/.config/taskviewer/board.toml`
- Windows: `%APPDATA%\taskviewer\board.toml`

Every key is optional; these are the defaults:

```toml
monitor = "focused"     # or an output name (e.g. "DP-0"); falls back to focused if unplugged
corner = "top-right"    # top-left | top-right | bottom-left | bottom-right | center
offset = [8, 8]         # px from the corner, x then y
width = 300             # px
max_height = 0.8        # fraction of the monitor height
opacity = 0.9
font_size = 10          # pt

# Windows only
hotkey_toggle = "ctrl+alt+t"
hotkey_collapse = "ctrl+alt+shift+t"
hotkey_reload = "ctrl+alt+r"
app_state_dir = ""      # use an App elsewhere, e.g. in WSL (see WSL)
```

After editing, reload the config (see the key tables above). You can also drag the Board anywhere; it remembers the spot per monitor until it restarts.

## Troubleshooting

- **Board says "App not running":** start any Claude Session, or run `taskviewer-app` yourself.
- **Windows: nothing happens:** check `%LOCALAPPDATA%\taskviewer\board.log`.
- **A hotkey does nothing:** another program owns it. Pick a different one in `board.toml`; the log names the key that failed.
- **Linux: black corners:** picom isn't running.

## Development

```sh
uv sync
uv run pytest
```

The repo is a uv workspace:
- `protocol/`: message types and the stdlib client
- `app/`: the background App
- `plugin/`: the Claude Code plugin
- `board/`: Board and Glance

`CONTEXT.md` defines the terms used throughout.
