# Corvox

*corvid + vox*: on-demand, natural-sounding text-to-speech for AI coding agents.

Corvox lets **Claude Code** and **OpenAI Codex CLI** read text aloud only when you want
them to, using Microsoft's neural voices (via [edge-tts](https://github.com/rany2/edge-tts))
with an offline fallback to Windows SAPI voices. No length limits: long replies are
streamed chunk by chunk.

> Status: alpha, Windows only for now.

## Triggers

| Trigger | How | Claude Code | Codex CLI |
|---|---|---|---|
| Direct | Ask "read this to me"; the agent runs `corvox say` | yes | yes* |
| Toggle | Type `corvox on` / `corvox off` as a prompt | yes | yes |
| Per-message | Start a prompt with 🔊 or include "read aloud" | yes | yes |
| Read last | Type `corvox last` (or `/corvox-last` in Claude Code) | yes | yes |
| Stop | Press **Esc** anywhere, or type `corvox stop` | yes | yes |

Typed `corvox …` commands are caught by a `UserPromptSubmit` hook and never reach the
model, so they cost no tokens. \*Codex runs shell commands in its sandbox; if that blocks
audio or network, ask with a marker instead and the reply is read by the Stop hook.

## Command line

```
corvox say "text"            # or: corvox say -f notes.md, or pipe text in
corvox say --private ...     # offline SAPI voice: text never leaves your PC
corvox say --code ...        # read code blocks this time
corvox stop | last | on | off | toggle | status
corvox voices [--lang en-GB|all]
corvox sample [VOICE ...] [--lang en-GB] [--sapi]
corvox config [show|path|edit|set KEY VALUE]
```

## Settings

One `config.toml`, shared by every agent: `engine` (auto/edge/sapi), `voice`, `sapi_voice`,
`speed`, `skip_code`, `on_conflict` (cancel/queue), `stop_key`, `markers`, and a
`[pronunciations]` table that extends the built-in list (API → "A P I", JSON → "jason", ...).

Everything lives in `CORVOX_HOME`: the `CORVOX_HOME` environment variable if set,
otherwise the folder holding Corvox's venv when it carries a `.corvox-home` marker,
otherwise `%LOCALAPPDATA%\corvox`.

## Privacy

The `edge` engine sends text to Microsoft's online speech service. Use `--private`
or `engine = "sapi"` for anything that shouldn't leave your machine. edge-tts uses an
unofficial endpoint, which Microsoft can change; `auto` falls back to SAPI when it fails.

## License

MIT
