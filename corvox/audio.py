"""Playback through Windows' built-in winmm (MCI) and stop-key polling. No audio packages needed."""

import ctypes
import itertools
import os
import time
from pathlib import Path
from typing import Callable

KEYS = {"esc": 0x1B, "pause": 0x13, "f9": 0x78}
POLL = 0.05

if os.name == "nt":
    _winmm = ctypes.WinDLL("winmm")
    _winmm.mciSendStringW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
    _winmm.mciSendStringW.restype = ctypes.c_uint
    _winmm.mciGetErrorStringW.argtypes = [ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_uint]
    _user32 = ctypes.WinDLL("user32")
    _user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    _user32.GetAsyncKeyState.restype = ctypes.c_short

_aliases = itertools.count()


def _mci(command: str) -> str:
    buf = ctypes.create_unicode_buffer(256)
    err = _winmm.mciSendStringW(command, buf, 255, None)
    if err:
        msg = ctypes.create_unicode_buffer(256)
        _winmm.mciGetErrorStringW(err, msg, 255)
        raise RuntimeError(f"MCI error {err}: {msg.value} [{command}]")
    return buf.value


def play(path: Path, should_stop: Callable[[], bool]) -> bool:
    """Play one file, polling should_stop. Returns True if it played to the end."""
    if os.name != "nt":
        raise NotImplementedError("Corvox playback currently supports Windows only")
    alias = f"corvox{os.getpid()}x{next(_aliases)}"
    kind = "mpegvideo" if path.suffix.lower() == ".mp3" else "waveaudio"
    _mci(f'open "{path}" type {kind} alias {alias}')
    try:
        _mci(f"play {alias}")
        while True:
            if should_stop():
                _mci(f"stop {alias}")
                return False
            if _mci(f"status {alias} mode") not in ("playing", "not ready", "seeking"):
                return True
            time.sleep(POLL)
    finally:
        try:
            _mci(f"close {alias}")
        except RuntimeError:
            pass


def key_code(name: str | None) -> int | None:
    return KEYS.get((name or "").lower())


def key_down(code: int | None) -> bool:
    """True while the key is held, whichever window has focus."""
    return bool(code) and os.name == "nt" and bool(_user32.GetAsyncKeyState(code) & 0x8000)
