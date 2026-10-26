"""Shared settings in CORVOX_HOME/config.toml, read by every agent adapter."""

import copy
import json
import os
import re
import tomllib

from corvox import paths

DEFAULTS = {
    "engine": "auto",
    "voice": "en-US-AndrewMultilingualNeural",
    "sapi_voice": "",
    "speed": 1.0,
    "skip_code": True,
    "on_conflict": "cancel",
    "stop_key": "esc",
    "markers": ["🔊", "read aloud", "read this aloud", "read it aloud", "read this to me", "read it to me"],
    "pronunciations": {},
}

CHOICES = {
    "engine": ("auto", "edge", "sapi"),
    "on_conflict": ("cancel", "queue"),
    "stop_key": ("esc", "pause", "f9", "none"),
}

TEMPLATE = """\
# Corvox settings, shared by every agent. `corvox config set KEY VALUE` edits this file
# and keeps these comments.

# auto = Microsoft neural voices (edge-tts, needs internet), falling back to Windows SAPI.
# edge = neural voices only. sapi = offline Windows voices only: text never leaves this PC.
engine = "auto"

# Neural voice. `corvox voices` lists them, `corvox sample` plays a few.
voice = "en-US-AndrewMultilingualNeural"

# Offline SAPI voice name. Empty = Windows default.
sapi_voice = ""

# 1.0 = normal. 1.25 = 25% faster.
speed = 1.0

# Skip fenced code blocks (says "Code block skipped.") but read everything else.
skip_code = true

# What happens when something new is read while another reading is playing:
# cancel = the new reading replaces it. queue = it waits its turn.
on_conflict = "cancel"

# Key that stops playback from any window: esc, pause, f9 or none.
stop_key = "esc"

# A prompt containing any of these (case-insensitive) gets its reply read aloud.
markers = ["🔊", "read aloud", "read this aloud", "read it aloud", "read this to me", "read it to me"]

[pronunciations]
# Added to the built-in list (API -> "A P I", JSON -> "jason", ...). Case-sensitive, whole words.
# Kubernetes = "koo-ber-net-eez"
"""


def load() -> dict:
    cfg = copy.deepcopy(DEFAULTS)
    try:
        with open(paths.config_file(), "rb") as f:
            cfg.update(tomllib.load(f))
    except FileNotFoundError:
        pass
    except (tomllib.TOMLDecodeError, OSError) as e:
        paths.log(f"config.toml ignored: {e}")
    return cfg


def init() -> bool:
    """Write the commented template if no config exists. Returns True if it wrote one."""
    path = paths.config_file()
    if path.exists():
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(TEMPLATE, encoding="utf-8")
    return True


def to_toml(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return "[" + ", ".join(to_toml(v) for v in value) + "]"
    raise TypeError(f"unsupported config value: {value!r}")


def parse_value(key: str, raw: str):
    if key not in DEFAULTS or isinstance(DEFAULTS[key], dict):
        raise KeyError(f"unknown setting '{key}'. Settings: {', '.join(k for k in DEFAULTS if k != 'pronunciations')}")
    default = DEFAULTS[key]
    if isinstance(default, bool):
        lowered = raw.strip().lower()
        if lowered in ("true", "on", "yes", "1"):
            return True
        if lowered in ("false", "off", "no", "0"):
            return False
        raise ValueError(f"{key} must be true or false")
    if isinstance(default, float):
        value = float(raw)
        if not 0.25 <= value <= 3.0:
            raise ValueError("speed must be between 0.25 and 3.0")
        return value
    if isinstance(default, list):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if key in CHOICES and raw not in CHOICES[key]:
        raise ValueError(f"{key} must be one of: {', '.join(CHOICES[key])}")
    return raw


def set_value(key: str, raw: str):
    """Set one top-level key in config.toml, editing the line in place so comments survive."""
    value = parse_value(key, raw)
    path = paths.config_file()
    init()
    text = path.read_text(encoding="utf-8")
    line = f"{key} = {to_toml(value)}"
    pattern = re.compile(rf"^{re.escape(key)}\s*=.*$", re.M)
    if pattern.search(text):
        text = pattern.sub(lambda _: line, text, count=1)
    else:
        table = text.find("\n[")
        text = text + f"\n{line}\n" if table < 0 else text[:table] + f"\n{line}\n" + text[table:]
    tmp = path.with_suffix(".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return value
