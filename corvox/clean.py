"""Turn an agent's markdown reply into text that sounds right when spoken."""

import re

PRONUNCIATIONS = {
    "API": "A P I",
    "JSON": "jason",
    "CLI": "C L I",
    "URL": "U R L",
    "UI": "U I",
    "UX": "U X",
    "SQL": "sequel",
    "HTTP": "H T T P",
    "HTTPS": "H T T P S",
    "HTML": "H T M L",
    "CSS": "C S S",
    "JS": "J S",
    "TS": "T S",
    "npm": "N P M",
    "PR": "P R",
    "CI": "C I",
    "ID": "I D",
    "IDE": "I D E",
    "CPU": "C P U",
    "GPU": "G P U",
    "OS": "O S",
    "AI": "A I",
    "LLM": "L L M",
    "SDK": "S D K",
    "SSH": "S S H",
    "TTS": "T T S",
    "YAML": "yammel",
    "TOML": "tommel",
    "README": "read me",
    "stdin": "standard in",
    "stdout": "standard out",
    "stderr": "standard error",
}

CODE_SKIPPED = "Code block skipped."
TABLE_SKIPPED = "Table skipped."

FENCE = re.compile(r"^[ \t]*(`{3,}|~{3,})[^\n]*\n(.*?)(?:^[ \t]*\1[ \t]*$|\Z)", re.M | re.S)
TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]")


def _strip_tables(text: str) -> str:
    out, in_table = [], False
    for line in text.split("\n"):
        if TABLE_ROW.match(line):
            if not in_table:
                out += ["", TABLE_SKIPPED, ""]
            in_table = True
            continue
        in_table = False
        out.append(line)
    return "\n".join(out)


def _inline(text: str) -> str:
    text = re.sub(r"<(https?://[^>]+)>", "", text)
    text = re.sub(r"</?[A-Za-z][^>\n]*>", "", text)
    text = re.sub(r"!\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\[[^\]]*\]", r"\1", text)
    text = re.sub(r"\b(?:https?://|www\.)\S+", "", text)
    text = re.sub(r"`([^`\n]+)`", r"\1", text)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    text = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\1", text)
    text = re.sub(r"(?<!\w)_(?!\s)(.+?)(?<!\s)_(?!\w)", r"\1", text)
    text = re.sub(r"~~(.+?)~~", r"\1", text)
    text = text.replace("→", " to ").replace("->", " to ").replace("=>", " to ")
    return EMOJI.sub("", text)


def _line(line: str) -> str:
    line = re.sub(r"^\s{0,3}#{1,6}\s+(.*?)\s*#*\s*$", r"\1", line)
    line = re.sub(r"^\s*>\s?", "", line)
    line = re.sub(r"^\s*[-*+]\s+(\[[ xX]\]\s+)?", "", line)
    if re.fullmatch(r"\s*([-*_]\s*){3,}", line):
        return ""
    line = _inline(line).strip()
    # Give every line-ending a pause, so bullets and headings don't run together.
    if line and line[-1] not in ".!?:;,":
        line += "."
    return line


def pronounce(text: str, extra: dict | None = None) -> str:
    table = {**PRONUNCIATIONS, **(extra or {})}
    for word in sorted(table, key=len, reverse=True):
        said = table[word]
        plural = "'s" if " " in said else "s"
        text = re.sub(rf"(?<![\w.-]){re.escape(word)}(s?)(?![\w-])",
                      lambda m, s=said, p=plural: s + (p if m.group(1) else ""), text)
    return text


def clean(text: str, *, skip_code: bool = True, pronunciations: dict | None = None) -> str:
    text = text.replace("\r\n", "\n")
    text = FENCE.sub(lambda m: f"\n{CODE_SKIPPED}\n" if skip_code else f"\n{m.group(2)}\n", text)
    text = _strip_tables(text)
    paragraphs, current = [], []
    for raw in text.split("\n"):
        line = _line(raw)
        if line:
            current.append(line)
        elif current:
            paragraphs.append(" ".join(current))
            current = []
    if current:
        paragraphs.append(" ".join(current))
    spoken = "\n".join(paragraphs)
    spoken = re.sub(r"[ \t]{2,}", " ", spoken)
    spoken = re.sub(r"\s+([.,;:!?])", r"\1", spoken)
    spoken = re.sub(r"([.!?])\.+", r"\1", spoken)
    return pronounce(spoken, pronunciations).strip()


def chunk(text: str, first: int = 220, size: int = 1500) -> list[str]:
    """Split for streaming: a short first chunk so speech starts fast, then larger ones."""
    pieces = [p.strip() for p in re.split(r"(?<=[.!?;:])\s+|\n+", text) if p.strip()]
    out, current, limit = [], "", first
    for piece in pieces:
        while len(piece) > size:
            cut = piece.rfind(" ", 0, size)
            cut = size if cut <= 0 else cut
            if current:
                out.append(current)
                current = ""
            out.append(piece[:cut].strip())
            piece = piece[cut:].strip()
            limit = size
        if current and len(current) + 1 + len(piece) > limit:
            out.append(current)
            current, limit = piece, size
        else:
            current = f"{current} {piece}".strip()
    if current:
        out.append(current)
    return out
