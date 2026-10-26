"""Adapters from agent hooks to Corvox.

Claude Code and Codex send near-identical JSON on stdin for their UserPromptSubmit
and Stop hooks (`prompt`, `last_assistant_message`, `session_id`, `transcript_path`),
so one adapter serves both. `agent` tags the saved reply so `corvox last` can pick.
"""

import json
import re

from corvox import config, paths, speech, spool, state

COMMAND = re.compile(r"^\s*/?corvox[\s:_-]+(on|off|toggle|last|stop|status)\s*$", re.I)


def has_marker(prompt: str, markers: list[str]) -> bool:
    lowered = prompt.lower()
    return any(m.lower() in lowered for m in markers if m)


def run_command(command: str, agent: str | None = None) -> str:
    """Run a typed `corvox <command>`. Returns the message shown to the user."""
    if command in ("on", "off", "toggle"):
        on = (not state.auto_read()) if command == "toggle" else command == "on"
        state.set_auto_read(on)
        return f"Corvox: auto-read {'ON, every reply will be read aloud' if on else 'OFF'}."
    if command == "stop":
        spool.stop()
        return "Corvox: stopped."
    if command == "last":
        reply = state.last_reply(agent) or state.last_reply()
        if not reply:
            return "Corvox: no reply saved yet."
        speech.say(reply["text"], source="last")
        return f"Corvox: reading the last {reply['agent']} reply."
    cfg = config.load()
    return (f"Corvox: auto-read {'on' if state.auto_read() else 'off'}, engine {cfg['engine']}, "
            f"voice {cfg['voice']}, speed {cfg['speed']}, "
            f"{'speaking' if spool.is_speaking() else 'idle'}. Home: {paths.home()}")


def on_prompt(agent: str, payload: dict) -> dict | None:
    prompt = payload.get("prompt") or ""
    match = COMMAND.match(prompt)
    if match:
        # Handled here without a model turn; blocking keeps the prompt out of the conversation.
        return {"decision": "block", "reason": run_command(match.group(1).lower(), agent)}
    state.start_turn(agent, payload.get("session_id", ""), has_marker(prompt, config.load()["markers"]))
    return None


def last_text_from_transcript(path: str | None) -> str:
    """Fallback for agents that don't send last_assistant_message: Claude Code's JSONL transcript."""
    if not path:
        return ""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return ""
    for line in reversed(lines):
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if entry.get("type") != "assistant":
            continue
        content = (entry.get("message") or {}).get("content") or []
        texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
        if any(texts):
            return "\n".join(texts)
    return ""


def on_stop(agent: str, payload: dict) -> dict:
    text = payload.get("last_assistant_message") or last_text_from_transcript(payload.get("transcript_path"))
    if not text:
        return {}
    state.save_last(agent, text)
    turn = state.get_turn(agent, payload.get("session_id", ""))
    if (state.auto_read() or turn["marked"]) and not state.direct_speech_since(turn["start"]):
        speech.say(text, source=f"{agent}-reply")
    return {}


def handle(agent: str, event: str, raw: str) -> str:
    """Run one hook. Never raises: a broken hook must not break the agent."""
    try:
        payload = json.loads(raw or "{}")
        result = on_prompt(agent, payload) if event == "prompt" else on_stop(agent, payload)
    except Exception as e:
        paths.log(f"{agent} {event} hook failed: {type(e).__name__}: {e}")
        result = None if event == "prompt" else {}
    # Codex requires JSON from a Stop hook that exits 0; prompt hooks print nothing unless blocking.
    return "" if result is None else json.dumps(result)
