"""Small shared state files: the auto-read toggle, each agent's last reply, and per-turn flags."""

import json
import os
import re
import time
from pathlib import Path

from corvox import paths

TURN_MAX_AGE = 86_400


def _path(name: str) -> Path:
    return paths.state_dir() / name


def _read(name: str, default):
    try:
        return json.loads(_path(name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(name: str, data) -> None:
    path = _path(name)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    for _ in range(20):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            time.sleep(0.01)
    tmp.unlink(missing_ok=True)


def auto_read() -> bool:
    return bool(_read("toggle.json", {}).get("auto_read", False))


def set_auto_read(on: bool) -> None:
    _write("toggle.json", {"auto_read": on})


def save_last(agent: str, text: str) -> None:
    _write(f"last-{agent}.json", {"agent": agent, "time": time.time(), "text": text})


def last_reply(agent: str | None = None) -> dict | None:
    """The newest saved reply, from one agent or from any."""
    names = [f"last-{agent}.json"] if agent else [p.name for p in paths.state_dir().glob("last-*.json")]
    replies = [r for r in (_read(n, None) for n in names) if r and r.get("text")]
    return max(replies, key=lambda r: r.get("time", 0), default=None)


def _turn_name(agent: str, session: str) -> str:
    safe = re.sub(r"[^\w-]", "", session or "")[:64] or "default"
    return f"turn-{agent}-{safe}.json"


def start_turn(agent: str, session: str, marked: bool) -> None:
    cutoff = time.time() - TURN_MAX_AGE
    for old in paths.state_dir().glob("turn-*.json"):
        try:
            if old.stat().st_mtime < cutoff:
                old.unlink()
        except OSError:
            pass
    _write(_turn_name(agent, session), {"start": time.time(), "marked": marked})


def get_turn(agent: str, session: str) -> dict:
    return _read(_turn_name(agent, session), {"start": 0, "marked": False})


def note_direct_speech() -> None:
    """Record that an agent ran `corvox say` itself, so the Stop hook won't talk over it."""
    _write("direct.json", {"time": time.time()})


def direct_speech_since(t: float) -> bool:
    return _read("direct.json", {}).get("time", 0) > t
