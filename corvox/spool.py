"""The single playback queue shared by every agent.

Readers write a job file into CORVOX_HOME/spool and make sure one detached worker
is draining it, so `corvox say` and the hooks return immediately. Cancelling uses
a generation counter instead of killing processes: `stop`, the stop key, or a new
reading in cancel mode bumps the counter, and the worker drops any job from an
older generation within one poll (~50 ms).
"""

import contextlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

from corvox import paths

if os.name == "nt":
    import msvcrt

    def _try_lock(fd: int) -> bool:
        os.lseek(fd, 0, os.SEEK_SET)
        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def _unlock(fd: int) -> None:
        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _try_lock(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def _unlock(fd: int) -> None:
        fcntl.flock(fd, fcntl.LOCK_UN)


class FileLock:
    """An OS file lock: released automatically if the holding process dies."""

    def __init__(self, path: Path):
        self.path = path
        self.fd = None

    def acquire(self, timeout: float | None = None) -> bool:
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT)
        deadline = None if timeout is None else time.monotonic() + timeout
        while not _try_lock(fd):
            if deadline is not None and time.monotonic() >= deadline:
                os.close(fd)
                return False
            time.sleep(0.02)
        self.fd = fd
        return True

    def release(self) -> None:
        if self.fd is not None:
            try:
                _unlock(self.fd)
            finally:
                os.close(self.fd)
                self.fd = None


@contextlib.contextmanager
def _mutex():
    lock = FileLock(paths.state_dir() / "spool.lock")
    lock.acquire(timeout=5)
    try:
        yield
    finally:
        lock.release()


def _worker_lock() -> FileLock:
    return FileLock(paths.state_dir() / "worker.lock")


def generation(default: int = 0) -> int:
    try:
        return int((paths.state_dir() / "generation").read_text())
    except (OSError, ValueError):
        return default


def _bump_generation() -> int:
    gen = generation() + 1
    path = paths.state_dir() / "generation"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(str(gen))
    for _ in range(20):
        try:
            os.replace(tmp, path)
            break
        except PermissionError:  # a reader has it open for a moment
            time.sleep(0.01)
    return gen


def _jobs() -> list[Path]:
    return sorted(paths.spool_dir().glob("*.json"))


def _clear() -> None:
    for job in _jobs():
        job.unlink(missing_ok=True)


def enqueue(text: str, *, mode: str, settings: dict, source: str) -> None:
    with _mutex():
        if mode == "cancel":
            gen = _bump_generation()
            _clear()
        else:
            gen = generation()
        job = {"text": text, "source": source, "gen": gen, "id": time.time_ns(), **settings}
        name = f"{job['id']}-{uuid.uuid4().hex[:6]}"
        tmp = paths.spool_dir() / f"{name}.tmp"
        tmp.write_text(json.dumps(job, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, tmp.with_suffix(".json"))
    ensure_worker()


def stop() -> None:
    with _mutex():
        _bump_generation()
        _clear()


def _take_next() -> dict | None:
    with _mutex():
        for path in _jobs():
            try:
                job = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError) as e:
                paths.log(f"dropping unreadable job {path.name}: {e}")
                job = None
            path.unlink(missing_ok=True)
            if job:
                return job
    return None


def is_speaking() -> bool:
    lock = _worker_lock()
    if lock.acquire(timeout=0):
        lock.release()
        return False
    return True


def ensure_worker() -> None:
    if not is_speaking():
        _spawn_worker()


def _spawn_worker() -> None:
    exe = Path(sys.executable)
    windowless = exe.with_name("pythonw.exe")
    cmd = [str(windowless if windowless.exists() else exe), "-m", "corvox", "_worker"]
    kwargs = dict(stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                  close_fds=True, cwd=str(paths.home()))
    if os.name != "nt":
        subprocess.Popen(cmd, start_new_session=True, **kwargs)
        return
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    try:
        # Leave the caller's job object, so an agent cleaning up its hook process doesn't cut playback.
        subprocess.Popen(cmd, creationflags=flags | subprocess.CREATE_BREAKAWAY_FROM_JOB, **kwargs)
    except OSError:
        subprocess.Popen(cmd, creationflags=flags, **kwargs)


def run_worker() -> None:
    """Drain the spool. Exactly one worker holds worker.lock; extras exit at once."""
    from corvox import player

    lock = _worker_lock()
    if not lock.acquire(timeout=0):
        return
    try:
        while True:
            job = _take_next()
            if job is None:
                # Release, then look once more: a job enqueued while we held the lock
                # saw a live worker and didn't spawn one, so it is ours to play.
                lock.release()
                if not _jobs() or not lock.acquire(timeout=0):
                    return
                continue
            if job["gen"] < generation(default=job["gen"]):
                continue
            try:
                player.play_job(job)
            except Exception as e:
                paths.log(f"playback failed: {type(e).__name__}: {e}")
    finally:
        lock.release()


def wait_idle(timeout: float | None = None) -> bool:
    """Block until the queue is empty and nothing is playing."""
    deadline = None if timeout is None else time.monotonic() + timeout
    time.sleep(0.3)  # let a just-spawned worker take its lock
    while _jobs() or is_speaking():
        if deadline is not None and time.monotonic() >= deadline:
            return False
        time.sleep(0.1)
    return True
