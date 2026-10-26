"""Where Corvox keeps its config, state, queue and audio cache."""

import os
import sys
import time
from pathlib import Path

# A venv whose parent folder holds this marker treats that folder as CORVOX_HOME,
# so `D:\Tools\corvox\venv` keeps everything under `D:\Tools\corvox`.
HOME_MARKER = ".corvox-home"
LOG_LIMIT = 1_000_000


def home() -> Path:
    """Resolve CORVOX_HOME: env var, then the folder beside our venv, then a per-user default."""
    env = os.environ.get("CORVOX_HOME")
    if env:
        return Path(env).expanduser()
    beside_venv = Path(sys.prefix).parent
    if (beside_venv / HOME_MARKER).exists():
        return beside_venv
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
    else:
        base = os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share"
    return Path(base) / "corvox"


def _dir(name: str) -> Path:
    path = home() / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def state_dir() -> Path:
    return _dir("state")


def spool_dir() -> Path:
    return _dir("spool")


def cache_dir() -> Path:
    return _dir("cache")


def config_file() -> Path:
    return home() / "config.toml"


def log(message: str) -> None:
    """Append to CORVOX_HOME/corvox.log. Hooks and the worker have no console, so this is where errors go."""
    try:
        path = home() / "corvox.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size > LOG_LIMIT:
            path.replace(path.with_suffix(".log.1"))
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except OSError:
        pass
