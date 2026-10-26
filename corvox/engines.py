"""Speech engines: Microsoft neural voices via edge-tts, and offline Windows SAPI voices."""

import asyncio
import base64
import os
import subprocess
from pathlib import Path

from corvox import paths

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# SAPI runs through Windows PowerShell's System.Speech, so it needs no Python packages.
# Inputs travel in environment variables to avoid any quoting of user text or paths.
SAPI_RENDER = r"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
if ($env:CORVOX_SAPI_VOICE) { $s.SelectVoice($env:CORVOX_SAPI_VOICE) }
$s.Rate = [int]$env:CORVOX_SAPI_RATE
$s.SetOutputToWaveFile($env:CORVOX_SAPI_OUT)
$s.Speak([IO.File]::ReadAllText($env:CORVOX_SAPI_IN, [Text.Encoding]::UTF8))
$s.Dispose()
"""

SAPI_LIST = r"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$s.GetInstalledVoices() | Where-Object Enabled | ForEach-Object {
  $v = $_.VoiceInfo; "{0}`t{1}`t{2}" -f $v.Name, $v.Gender, $v.Culture
}
"""


def _powershell(script: str, env: dict | None = None, timeout: float = 120) -> str:
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        env={**os.environ, **(env or {})}, capture_output=True, text=True,
        timeout=timeout, creationflags=NO_WINDOW,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or f"powershell exited {result.returncode}")
    return result.stdout


def edge_rate(speed: float) -> str:
    return f"{round((speed - 1) * 100):+d}%"


def sapi_rate(speed: float) -> int:
    return max(-10, min(10, round((speed - 1) * 10)))


def render_edge(text: str, out: Path, voice: str, speed: float) -> Path:
    import edge_tts

    asyncio.run(edge_tts.Communicate(text, voice, rate=edge_rate(speed)).save(str(out)))
    if not out.exists() or out.stat().st_size == 0:
        raise RuntimeError("edge-tts returned no audio")
    return out


def render_sapi(text: str, out: Path, voice: str, speed: float) -> Path:
    source = out.with_suffix(".txt")
    source.write_text(text, encoding="utf-8")
    try:
        _powershell(SAPI_RENDER, {
            "CORVOX_SAPI_IN": str(source), "CORVOX_SAPI_OUT": str(out),
            "CORVOX_SAPI_VOICE": voice or "", "CORVOX_SAPI_RATE": str(sapi_rate(speed)),
        })
    finally:
        source.unlink(missing_ok=True)
    return out


class Synth:
    """Renders chunks for one job. In `auto` mode the first edge-tts failure switches the rest of the job to SAPI."""

    def __init__(self, job: dict):
        self.engine = job.get("engine", "auto")
        self.voice = job.get("voice", "")
        self.sapi_voice = job.get("sapi_voice", "")
        self.speed = float(job.get("speed", 1.0))

    def render(self, text: str, base: Path) -> Path:
        if self.engine in ("auto", "edge"):
            try:
                return render_edge(text, base.with_suffix(".mp3"), self.voice, self.speed)
            except Exception as e:
                if self.engine == "edge":
                    raise
                paths.log(f"edge-tts failed ({type(e).__name__}: {e}); falling back to SAPI")
                self.engine = "sapi"
        return render_sapi(text, base.with_suffix(".wav"), self.sapi_voice, self.speed)


def edge_voices() -> list[dict]:
    import edge_tts

    return asyncio.run(edge_tts.list_voices())


def sapi_voices() -> list[dict]:
    voices = []
    for line in _powershell(SAPI_LIST, timeout=30).splitlines():
        parts = line.strip().split("\t")
        if len(parts) == 3:
            voices.append({"Name": parts[0], "Gender": parts[1], "Locale": parts[2]})
    return voices
