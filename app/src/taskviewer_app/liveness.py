import psutil


def process_start(pid: int) -> float:
    """Start time (epoch secs) of a process; used with pid to detect pid reuse."""
    return psutil.Process(pid).create_time()


def is_alive(pid: int, pid_start: float) -> bool:
    try:
        return abs(psutil.Process(pid).create_time() - pid_start) < 1.0
    except psutil.Error:
        return False


def ancestors(pid: int) -> list[int]:
    """Parent pids of a process, nearest first."""
    try:
        return [p.pid for p in psutil.Process(pid).parents()]
    except psutil.Error:
        return []


CLAUDE = {"claude", "claude.exe", "node", "node.exe"}
# short-lived processes between Claude and a hook: uv's .exe launchers (Windows) and shells
LAUNCHERS = {"sh", "bash", "bash.exe", "zsh", "dash", "cmd.exe", "powershell.exe", "pwsh", "pwsh.exe"}


def _launcher(name: str) -> bool:
    return name in LAUNCHERS or name.startswith("taskviewer-")


def claude_ancestor(pid: int, name=lambda pid: psutil.Process(pid).name(), ancestors=ancestors) -> int:
    """The Claude process behind a hook's parent pid: walk up through launchers to claude/node.

    Any other chain keeps `pid`.
    """
    try:
        if not _launcher(name(pid)):
            return pid
        for a in ancestors(pid):
            n = name(a)
            if n in CLAUDE:
                return a
            if not _launcher(n):
                return pid
    except psutil.Error:
        pass
    return pid
