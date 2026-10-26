"""`corvox` command line."""

import argparse
import os
import sys

from corvox import __version__, config, engines, hooks, paths, speech, spool

SAMPLE_VOICES = [
    "en-US-AndrewMultilingualNeural",
    "en-US-AvaMultilingualNeural",
    "en-US-BrianMultilingualNeural",
    "en-US-EmmaMultilingualNeural",
    "en-US-ChristopherNeural",
    "en-GB-SoniaNeural",
    "en-GB-RyanNeural",
    "en-AU-NatashaNeural",
]
SAMPLE_TEXT = ("Hi, I'm {name}. Your build passed, the API returned JSON in under a second, "
               "and the pull request is ready for review.")


def _read_bytes(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")
    return data.decode("utf-8-sig", errors="replace")


def _input_text(args) -> str:
    if args.file:
        if args.file == "-":
            return _read_bytes(sys.stdin.buffer.read())
        with open(args.file, "rb") as f:
            return _read_bytes(f.read())
    if args.text:
        return " ".join(args.text)
    if not sys.stdin.isatty():
        return _read_bytes(sys.stdin.buffer.read())
    return ""


def cmd_say(args) -> int:
    text = _input_text(args)
    if not text.strip():
        print("corvox: nothing to read. Pass text, -f FILE, or pipe it in.", file=sys.stderr)
        return 2
    skip_code = True if args.skip_code else False if args.code else None
    queued = speech.say(text, engine="sapi" if args.private else args.engine, voice=args.voice,
                        speed=args.speed, mode="queue" if args.queue else None,
                        skip_code=skip_code, raw=args.raw)
    if not queued:
        print("corvox: nothing speakable left after cleanup.", file=sys.stderr)
        return 1
    if args.wait:
        spool.wait_idle()
    return 0


def cmd_simple(args) -> int:
    print(hooks.run_command(args.command))
    return 0


def cmd_last(args) -> int:
    print(hooks.run_command("last", args.agent))
    return 0


def _voice_label(short_name: str) -> str:
    name = short_name.split("-", 2)[-1]
    for suffix in ("MultilingualNeural", "Neural"):
        name = name.removesuffix(suffix)
    return name


def cmd_voices(args) -> int:
    current = config.load()
    if args.engine in (None, "edge"):
        try:
            voices = engines.edge_voices()
        except Exception as e:
            print(f"Neural voices unavailable ({type(e).__name__}: {e}).", file=sys.stderr)
            voices = []
        lang = args.lang.lower()
        for v in sorted(voices, key=lambda v: v["ShortName"]):
            if lang != "all" and not v["Locale"].lower().startswith(lang):
                continue
            tags = ", ".join((v.get("VoiceTag") or {}).get("VoicePersonalities") or [])
            mark = "*" if v["ShortName"] == current["voice"] else " "
            print(f"{mark} {v['ShortName']:<40} {v['Gender']:<7} {tags}")
    if args.engine in (None, "sapi"):
        print("\nOffline (SAPI) voices:")
        for v in engines.sapi_voices():
            mark = "*" if v["Name"] == current["sapi_voice"] else " "
            print(f"{mark} {v['Name']:<40} {v['Gender']:<7} {v['Locale']}")
    return 0


def cmd_sample(args) -> int:
    if args.sapi:
        targets = [(v["Name"], "sapi") for v in engines.sapi_voices()]
    elif args.voices:
        targets = [(v, "edge") for v in args.voices]
    else:
        names = SAMPLE_VOICES
        if args.lang:
            names = sorted(v["ShortName"] for v in engines.edge_voices()
                           if v["Locale"].lower().startswith(args.lang.lower()))
        targets = [(v, "edge") for v in names]
    print(f"Playing {len(targets)} samples. {config.load()['stop_key'].capitalize()} skips one, Ctrl+C stops.")
    try:
        for name, engine in targets:
            label = name if engine == "sapi" else _voice_label(name)
            print(f"  {name}")
            text = args.text or SAMPLE_TEXT.format(name=label.replace("Microsoft ", "").replace(" Desktop", ""))
            if engine == "sapi":
                spool.enqueue(text, mode="queue", source="sample", settings={
                    "engine": "sapi", "sapi_voice": name, "speed": config.load()["speed"],
                    "stop_key": config.load()["stop_key"]})
            else:
                speech.say(text, source="sample", engine="edge", voice=name, mode="queue")
            spool.wait_idle()
    except KeyboardInterrupt:
        spool.stop()
    print("Set one with: corvox config set voice <name>")
    return 0


def cmd_config(args) -> int:
    path = paths.config_file()
    if args.action == "path":
        print(path)
    elif args.action == "init":
        print(f"{'Created' if config.init() else 'Already exists:'} {path}")
    elif args.action == "edit":
        config.init()
        os.startfile(path) if os.name == "nt" else print(path)
    elif args.action == "set":
        if len(args.rest) != 2:
            print("usage: corvox config set KEY VALUE", file=sys.stderr)
            return 2
        try:
            value = config.set_value(*args.rest)
        except (KeyError, ValueError) as e:
            print(f"corvox: {e.args[0]}", file=sys.stderr)
            return 2
        print(f"{args.rest[0]} = {config.to_toml(value)}")
    else:
        for key, value in config.load().items():
            print(f"{key} = {value!r}" if isinstance(value, dict) else f"{key} = {config.to_toml(value)}")
        print(f"# {path}{'' if path.exists() else ' (not created yet, defaults shown)'}")
    return 0


def cmd_install(args) -> int:
    from corvox import install

    agents = [a for a in ("claude", "codex") if getattr(args, a)]
    return install.run(agents, remove=args.remove, dry_run=args.dry_run, yes=args.yes)


def cmd_hook(args) -> int:
    out = hooks.handle(args.agent, args.event, _read_bytes(sys.stdin.buffer.read()))
    if out:
        print(out)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="corvox", description="Read text aloud for your AI coding agents.")
    p.add_argument("--version", action="version", version=f"corvox {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("say", aliases=["speak"], help="read text aloud (argument, -f FILE, or stdin)")
    s.add_argument("text", nargs="*")
    s.add_argument("-f", "--file", help="read this file ('-' for stdin)")
    s.add_argument("--private", action="store_true", help="offline SAPI only: text never leaves this PC")
    s.add_argument("--engine", choices=config.CHOICES["engine"])
    s.add_argument("--voice")
    s.add_argument("--speed", type=float)
    s.add_argument("--queue", action="store_true", help="wait for the current reading instead of replacing it")
    code = s.add_mutually_exclusive_group()
    code.add_argument("--code", action="store_true", help="read code blocks this time")
    code.add_argument("--skip-code", action="store_true", help="skip code blocks this time")
    s.add_argument("--raw", action="store_true", help="no markdown cleanup or pronunciation fixes")
    s.add_argument("--wait", action="store_true", help="block until playback finishes")
    s.set_defaults(func=cmd_say)

    for name, text in [("stop", "stop playback and clear the queue"), ("on", "turn auto-read on"),
                       ("off", "turn auto-read off"), ("toggle", "flip auto-read"), ("status", "show state")]:
        c = sub.add_parser(name, help=text)
        c.set_defaults(func=cmd_simple, command=name)

    last = sub.add_parser("last", help="read the last agent reply again")
    last.add_argument("--agent", choices=["claude", "codex"])
    last.set_defaults(func=cmd_last)

    v = sub.add_parser("voices", help="list voices")
    v.add_argument("--lang", default="en", help="locale prefix, e.g. en, en-GB, ja, or 'all'")
    v.add_argument("--engine", choices=["edge", "sapi"])
    v.set_defaults(func=cmd_voices)

    sm = sub.add_parser("sample", help="play voice samples")
    sm.add_argument("voices", nargs="*", help="voice names (default: a curated English set)")
    sm.add_argument("--lang", help="sample every neural voice for this locale, e.g. en-GB")
    sm.add_argument("--sapi", action="store_true", help="sample the offline voices")
    sm.add_argument("--text", help="custom sample text")
    sm.set_defaults(func=cmd_sample)

    c = sub.add_parser("config", help="show or change settings")
    c.add_argument("action", nargs="?", default="show", choices=["show", "path", "init", "edit", "set"])
    c.add_argument("rest", nargs="*")
    c.set_defaults(func=cmd_config)

    for name, text in [("install", "wire Corvox into Claude Code and Codex (shows a diff first)"),
                       ("uninstall", "remove everything install added")]:
        i = sub.add_parser(name, help=text)
        i.add_argument("--claude", action="store_true", help="only Claude Code")
        i.add_argument("--codex", action="store_true", help="only Codex CLI")
        i.add_argument("--dry-run", action="store_true", help="show the diff, write nothing")
        i.add_argument("--yes", action="store_true", help="apply without asking")
        i.set_defaults(func=cmd_install, remove=name == "uninstall")

    h = sub.add_parser("hook", help="agent hook entry point (reads JSON on stdin)")
    h.add_argument("agent", choices=["claude", "codex"])
    h.add_argument("event", choices=["prompt", "stop"])
    h.set_defaults(func=cmd_hook)

    w = sub.add_parser("_worker")
    w.set_defaults(func=lambda _: spool.run_worker() or 0)
    return p


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    return args.func(args)
