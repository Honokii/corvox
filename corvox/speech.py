"""The one entry point everything uses to read text aloud."""

from corvox import clean, config, spool, state


def say(text: str, *, source: str = "cli", engine: str | None = None, voice: str | None = None,
        speed: float | None = None, mode: str | None = None, skip_code: bool | None = None,
        raw: bool = False) -> bool:
    """Clean the text and queue it. Returns False if nothing speakable was left."""
    cfg = config.load()
    if not raw:
        text = clean.clean(text, skip_code=cfg["skip_code"] if skip_code is None else skip_code,
                           pronunciations=cfg["pronunciations"])
    if not text.strip():
        return False
    settings = {
        "engine": engine or cfg["engine"],
        "voice": voice or cfg["voice"],
        "sapi_voice": cfg["sapi_voice"],
        "speed": speed or cfg["speed"],
        "stop_key": cfg["stop_key"],
    }
    if source == "cli":
        state.note_direct_speech()
    spool.enqueue(text, mode=mode or cfg["on_conflict"], settings=settings, source=source)
    return True
