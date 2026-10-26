# Corvox

*corvid + vox*: on-demand, natural-sounding text-to-speech for AI coding agents.

Corvox lets **Claude Code** and **OpenAI Codex CLI** read text aloud, but only when you
ask. It uses Microsoft's neural voices (via [edge-tts](https://github.com/rany2/edge-tts))
and falls back to the offline Windows voices when you're offline or the text is private.
There are no length limits: long replies are streamed chunk by chunk.

> **Status:** alpha. Windows 10/11 only for now.

## Requirements

- Windows 10 or 11
- Python 3.11 or newer
- Git (to install from GitHub until Corvox is on PyPI)
- Claude Code and/or Codex CLI (the desktop apps use the same config and work too)

## 1. Install Corvox

Pick one.

### Option A: pipx (simplest)

```powershell
pipx install git+https://github.com/Honokii/corvox.git
```

Corvox keeps its settings in `%LOCALAPPDATA%\corvox`. To keep them somewhere else,
set `CORVOX_HOME` once (`setx CORVOX_HOME D:\Tools\corvox`) and restart your terminal
and agents.

### Option B: everything in one folder, on any drive

Useful if your system drive is short on space. Everything (Python packages, settings,
state) stays inside the folder you choose, about 20 MB.

```powershell
py -m venv D:\Tools\corvox\venv
D:\Tools\corvox\venv\Scripts\pip install git+https://github.com/Honokii/corvox.git
New-Item D:\Tools\corvox\.corvox-home
```

The empty `.corvox-home` file tells Corvox to keep its data in `D:\Tools\corvox`.
In the commands below, use `D:\Tools\corvox\venv\Scripts\corvox.exe` instead of `corvox`
(or add `D:\Tools\corvox\venv\Scripts` to your PATH).

### Check it works

```powershell
corvox say "Hello from Corvox."
```

## 2. Pick a voice

```powershell
corvox sample                     # plays a few English voices; each says its name
corvox sample --lang en-GB        # every British voice
corvox voices --lang all          # list every voice
corvox config set voice en-GB-SoniaNeural
```

## 3. Connect your agents

```powershell
corvox install
```

This shows a diff of every config file it will change, and only writes after you
confirm. It finds Claude Code (`~/.claude`) and Codex (`~/.codex`) automatically; use
`--claude` or `--codex` to pick one, or `--dry-run` to look without writing.

It adds:

| Agent | Changes |
|---|---|
| Claude Code | Two hooks in `settings.json`, a short "how to read aloud" block in `CLAUDE.md`, and the `/corvox-last`, `/corvox-on`, `/corvox-off`, `/corvox-stop` commands |
| Codex | Two hooks in `hooks.json` and the same block in `AGENTS.md` |

Existing files are backed up to `<CORVOX_HOME>\backups` first.

**Then, in Codex, run `/hooks` and allow the two Corvox hooks.** Codex skips hooks
you haven't approved. If your Claude Code session doesn't respond to Corvox
commands, start a new session.

## 4. Use it

Corvox is silent until you ask. The same commands work in both agents.

| You want | Type this in your agent | What happens |
|---|---|---|
| Hear this one reply | Start your prompt with `🔊`, or include "read aloud" | The agent's reply is read when it finishes |
| Hear every reply | `corvox on` (and `corvox off` to stop) | Applies to both agents at once |
| Hear the last reply again | `corvox last` (or `/corvox-last` in Claude Code) | Reads that agent's last reply (`corvox last` in a terminal reads the newest from either) |
| Have a file or some text read | "Read README.md to me" | The agent runs Corvox on it |
| Stop talking | Press **Esc** anywhere, or type `corvox stop` | Stops and clears anything queued |
| Check settings | `corvox status` | Shows voice, engine, and whether auto-read is on |

Typed `corvox …` commands are handled by a hook before the model sees them, so they
don't use a model turn or tokens.

> **"A hook blocked your prompt" is expected.** To keep a Corvox command away from the
> model, the hook blocks the prompt once it has handled it. Claude Code shows every
> blocked prompt as a warning card, with Corvox's message in it (for example
> "Corvox: reading the last claude reply."). The command still worked. The card only
> means the prompt wasn't sent to the model.

A new reading replaces the one playing. If both agents want to speak at once, they
share one queue, so they never talk over each other.

## Command line

You can also use Corvox directly from any terminal:

```text
corvox say "text"              read text
corvox say -f notes.md         read a file (markdown is cleaned up first)
type notes.txt | corvox say    read from stdin
corvox say --private ...       offline Windows voice: the text never leaves your PC
corvox say --code ...          include code blocks this time
corvox say --queue ...         wait for the current reading instead of replacing it
corvox stop | last | on | off | toggle | status
corvox voices [--lang en-GB | all]
corvox sample [VOICE ...] [--lang en-GB] [--sapi]
corvox config [show | path | edit | set KEY VALUE]
corvox install | uninstall [--claude] [--codex] [--dry-run] [--yes]
```

## Settings

`corvox config edit` opens `config.toml`, which both agents share. Each setting is
commented in the file.

| Setting | Default | Meaning |
|---|---|---|
| `voice` | `en-US-AndrewMultilingualNeural` | Neural voice (`corvox voices`) |
| `engine` | `auto` | `auto` (neural, offline fallback), `edge` (neural only), `sapi` (offline only) |
| `sapi_voice` | Windows default | Offline voice name |
| `speed` | `1.0` | `1.25` = 25% faster |
| `skip_code` | `true` | Say "Code block skipped." instead of reading code |
| `on_conflict` | `cancel` | `cancel` = new reading replaces the current one; `queue` = it waits |
| `stop_key` | `esc` | `esc`, `pause`, `f9` or `none` |
| `markers` | 🔊, "read aloud", ... | Words in a prompt that get its reply read |
| `[pronunciations]` | | Your own fixes, e.g. `Kubernetes = "koo-ber-net-eez"` |

Before speaking, Corvox strips markdown, links, URLs and tables, and fixes common
acronyms (API → "A P I", JSON → "jason", SQL → "sequel").

## Privacy

The neural voices send text to Microsoft's online speech service. For anything
sensitive, use `corvox say --private` or set `engine = "sapi"`. edge-tts uses an
unofficial endpoint that Microsoft can change; `auto` falls back to the offline voice
if it stops working.

## Troubleshooting

- **Nothing happens in Codex:** run `/hooks` and check both Corvox hooks are allowed.
- **Nothing happens in Claude Code:** start a new session.
- **"A hook blocked your prompt" after a Corvox command:** this is expected, not an
  error. Corvox handled the command and kept it from reaching the model.
- **No sound:** run `corvox say "test"` in a terminal. Errors go to `corvox.log` in
  `CORVOX_HOME` (`corvox config path` shows where that is).
- **Esc stops Corvox when I didn't mean it to:** Esc works from any window while
  Corvox is speaking. Change it with `corvox config set stop_key f9`, or `none`.
- **Offline voices sound robotic:** Windows only exposes its older voices to apps.
  Use the neural voices when you can.

## Uninstall

```powershell
corvox uninstall          # removes only what `corvox install` added
pipx uninstall corvox     # Option A
```

For Option B, run `uninstall` and then delete the folder (for example `D:\Tools\corvox`).

## License

MIT
