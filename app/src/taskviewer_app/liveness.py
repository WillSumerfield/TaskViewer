import psutil


def process_start(pid: int) -> float:
    """Start time (epoch secs) of a process; used with pid to detect pid reuse."""
    return psutil.Process(pid).create_time()


def is_alive(pid: int, pid_start: float) -> bool:
    try:
        return abs(psutil.Process(pid).create_time() - pid_start) < 1.0
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False
