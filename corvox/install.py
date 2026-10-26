"""`corvox install` / `corvox uninstall`: wire Corvox into Claude Code and Codex CLI.

Every change is computed first and shown as a diff. Existing files are backed up to
CORVOX_HOME/backups before they are written, and uninstall removes only what install
added: our hook handlers, our marked instruction blocks, and our command files.
"""

import difflib
import json
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from corvox import config, paths

BLOCK_START = "<!-- corvox:start -->"
BLOCK_END = "<!-- corvox:end -->"
COMMAND_TAG = "<!-- corvox-command -->"
HOOK_EVENTS = (("UserPromptSubmit", "prompt"), ("Stop", "stop"))
HOOK_TIMEOUT = 10

INSTRUCTIONS = """\
## Reading aloud with Corvox

When I ask you to read something aloud ("read this to me", "read it out loud", "say it"), use Corvox:

- A file: `{exe} say -f "<path>"`
- Text you write: save it to a temporary file first, then `{exe} say -f "<temp file>"`.
  Don't pipe text through Windows PowerShell; it mangles non-ASCII characters.

Corvox plays in the background and returns at once: run it once, don't wait and don't re-run it.
Read the full text. Never shorten or summarise it unless I ask. Add `--code` to include code
blocks, or `--private` for anything sensitive (offline voice, text stays on this PC).
Don't run Corvox unless I ask.{extra}"""

CODEX_EXTRA = """
If Corvox fails inside your sandbox, say so and suggest I start my prompt with 🔊 instead,
which reads your reply aloud from outside the sandbox."""

COMMANDS = {
    "last": "read the last agent reply aloud",
    "on": "turn auto-read on (every reply is read aloud)",
    "off": "turn auto-read off",
    "stop": "stop reading",
}

COMMAND_FILE = """\
---
description: Corvox, {summary}
disable-model-invocation: true
allowed-tools: Bash({exe} {name})
---
{tag}
!`{exe} {name}`

Corvox has handled this. Reply with only: Done.
"""


@dataclass
class Change:
    path: Path
    before: str | None
    after: str | None

    @property
    def changed(self) -> bool:
        return self.before != self.after

    def diff(self) -> str:
        if self.after is None:
            return f"--- {self.path}\n(delete file)\n"
        label = str(self.path) + ("  (new file)" if self.before is None else "")
        lines = difflib.unified_diff((self.before or "").splitlines(keepends=True),
                                     self.after.splitlines(keepends=True),
                                     fromfile=label, tofile=label, n=2)
        return "".join(line if line.endswith("\n") else line + "\n" for line in lines)


def claude_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def codex_dir() -> Path:
    return Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")


def corvox_exe() -> str:
    exe = Path(sys.executable).with_name("corvox.exe" if os.name == "nt" else "corvox")
    if not exe.exists():
        found = shutil.which("corvox")
        if not found:
            raise SystemExit("corvox: can't find the corvox executable to point hooks at.")
        exe = Path(found)
    # Forward slashes and no quotes run unchanged in cmd, PowerShell and bash.
    return exe.resolve().as_posix()


def _read(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def _is_ours(handler: dict) -> bool:
    command = str(handler.get("command", "")).lower()
    args = handler.get("args") or []
    return "corvox" in command and (" hook " in command or args[:1] == ["hook"])


def _handler(exe: str, agent: str, event: str, exec_form: bool) -> dict:
    if " " not in exe:
        return {"type": "command", "command": f"{exe} hook {agent} {event}", "timeout": HOOK_TIMEOUT}
    if exec_form:
        return {"type": "command", "command": exe, "args": ["hook", agent, event], "timeout": HOOK_TIMEOUT}
    return {"type": "command", "command": f'"{exe}" hook {agent} {event}', "timeout": HOOK_TIMEOUT}


def merged_hooks(before: str | None, exe: str, agent: str, remove: bool = False) -> str | None:
    """Add (or remove) our UserPromptSubmit and Stop handlers in a settings.json / hooks.json."""
    data = json.loads(before) if before and before.strip() else {}
    hooks = data.get("hooks", {})
    for event, arg in HOOK_EVENTS:
        groups = []
        for group in hooks.get(event, []):
            kept = [h for h in group.get("hooks", []) if not _is_ours(h)]
            if kept:
                groups.append({**group, "hooks": kept})
        if not remove:
            groups.append({"hooks": [_handler(exe, agent, arg, exec_form=agent == "claude")]})
        if groups:
            hooks[event] = groups
        else:
            hooks.pop(event, None)
    if hooks:
        data["hooks"] = hooks
    else:
        data.pop("hooks", None)
    if not data and agent == "codex":
        return None  # hooks.json held only our hooks
    newline = "\n" if before is None or before.endswith("\n") else ""
    return json.dumps(data, indent=2, ensure_ascii=False) + newline


def merged_block(before: str | None, block: str, remove: bool = False) -> str | None:
    """Add (or remove) our marked block in a CLAUDE.md / AGENTS.md, leaving the rest alone."""
    text = before or ""
    text = re.sub(rf"\n*{re.escape(BLOCK_START)}.*?{re.escape(BLOCK_END)}\n?", "\n", text, flags=re.S)
    text = text.strip("\n")
    if remove:
        if not text.strip():
            return None
        return text + "\n"
    marked = f"{BLOCK_START}\n{block}\n{BLOCK_END}\n"
    return f"{text}\n\n{marked}" if text else marked


def plan(agents: list[str], remove: bool = False) -> list[Change]:
    exe = corvox_exe()
    changes = []

    def add(path: Path, after: str | None) -> None:
        before = _read(path)
        if before is None and (after is None or remove):
            return
        changes.append(Change(path, before, after))

    if "claude" in agents:
        root = claude_dir()
        settings = root / "settings.json"
        add(settings, merged_hooks(_read(settings), exe, "claude", remove) or "{}\n")
        claude_md = root / "CLAUDE.md"
        add(claude_md, merged_block(_read(claude_md), INSTRUCTIONS.format(exe=exe, extra=""), remove))
        for name, summary in COMMANDS.items():
            path = root / "commands" / f"corvox-{name}.md"
            existing = _read(path)
            if existing is not None and COMMAND_TAG not in existing:
                continue  # someone else's file with our name: leave it
            add(path, None if remove else COMMAND_FILE.format(
                summary=summary, exe=exe, name=name, tag=COMMAND_TAG))
    if "codex" in agents:
        root = codex_dir()
        hooks_json = root / "hooks.json"
        add(hooks_json, merged_hooks(_read(hooks_json), exe, "codex", remove))
        agents_md = root / "AGENTS.md"
        add(agents_md, merged_block(_read(agents_md), INSTRUCTIONS.format(exe=exe, extra=CODEX_EXTRA), remove))
    return [c for c in changes if c.changed]


def apply(changes: list[Change]) -> Path | None:
    """Back up every existing file we touch, then write. Returns the backup folder, if any."""
    backup = paths.home() / "backups" / time.strftime("%Y%m%d-%H%M%S")
    used = False
    for change in changes:
        if change.before is not None:
            backup.mkdir(parents=True, exist_ok=True)
            agent = "claude" if claude_dir() in change.path.parents else "codex"
            shutil.copy2(change.path, backup / f"{agent}-{change.path.name}")
            used = True
        if change.after is None:
            change.path.unlink(missing_ok=True)
        else:
            change.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = change.path.with_name(change.path.name + ".corvox-tmp")
            tmp.write_text(change.after, encoding="utf-8")
            os.replace(tmp, change.path)
    if "commands" in {c.path.parent.name for c in changes}:
        commands = claude_dir() / "commands"
        if commands.exists() and not any(commands.iterdir()):
            commands.rmdir()
    return backup if used else None


def detect_agents() -> list[str]:
    return [name for name, root in (("claude", claude_dir()), ("codex", codex_dir())) if root.exists()]


def run(agents: list[str], *, remove: bool, dry_run: bool, yes: bool) -> int:
    agents = agents or detect_agents()
    if not agents:
        print("corvox: found neither ~/.claude nor ~/.codex. Pass --claude or --codex.", file=sys.stderr)
        return 1
    if not remove:
        config.init()
    changes = plan(agents, remove)
    verb = "uninstall" if remove else "install"
    if not changes:
        print(f"Nothing to change: Corvox is already {'removed' if remove else 'installed'} for {', '.join(agents)}.")
        return 0
    for change in changes:
        print(change.diff())
    if dry_run:
        print(f"Dry run: {len(changes)} file(s) would change. Nothing was written.")
        return 0
    if not yes:
        if not sys.stdin.isatty():
            print("corvox: re-run with --yes to apply these changes.", file=sys.stderr)
            return 2
        if input(f"Apply these {len(changes)} change(s)? [y/N] ").strip().lower() not in ("y", "yes"):
            print("Nothing changed.")
            return 1
    backup = apply(changes)
    print(f"Corvox {verb}ed for {', '.join(agents)}." + (f" Backups: {backup}" if backup else ""))
    if not remove:
        if "claude" in agents:
            print("Claude Code: start a new session so it loads the hooks.")
        if "codex" in agents:
            print("Codex: run /hooks inside Codex and trust the two Corvox hooks; untrusted hooks are skipped.")
    return 0
