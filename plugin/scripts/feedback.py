#!/usr/bin/env python3
"""Draft a feedback post for the user to open and post themselves. Nothing is sent from here.

Usage:
  feedback.py draft --kind idea|problem|question --text-file F [--title T] [--usage] [--dir D]
      prints any personal-data warnings, then the title, the body and the URL to open.
      --usage adds a count per skill name over the last 90 days of log.md (names and counts only).
Python stdlib only.
"""
import argparse
import datetime
import json
import platform
import re
import sys
from pathlib import Path
from urllib.parse import quote, urlencode

import athlete_folder

REPO = "cubetes/coaich"
PLUGIN_JSON = Path(__file__).resolve().parent.parent / ".claude-plugin" / "plugin.json"
MAX_URL = 7500  # browsers and GitHub start failing on longer URLs
SHORTENED = "\n\n(shortened)"
USAGE_DAYS = 90
LOG_LINE = re.compile(r"^- (\d{4}-\d{2}-\d{2}) · ([a-z0-9-]+) · ")  # only a well-formed skill name is counted
LOOKS_PERSONAL = [
    ("email address", re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")),
    ("phone number", re.compile(r"(?<![\w-])\+?\d(?:[ ().-]?\d){8,14}(?![\w-])")),
    ("date (a birth date?)", re.compile(r"\b(?:\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4})\b")),
    ("body number", re.compile(r"\b\d+(?:[.,]\d+)?\s?(?:(?:kgs?|lbs?|cm)\b|%)", re.I)),
]


def version():
    return json.loads(PLUGIN_JSON.read_text(encoding="utf-8"))["version"]


def os_name():
    mac = platform.mac_ver()[0]
    return f"macOS {mac}" if mac else f"{platform.system()} {platform.release()}".strip()


def warnings(text):
    """[(what, found)] for anything that looks like personal data. Warns only; the user decides."""
    return [(what, m.group(0)) for what, rx in LOOKS_PERSONAL for m in rx.finditer(text)]


def usage(folder, today=None):
    """{skill: runs} from log.md over the last 90 days. No folder or no log.md → {}."""
    try:
        path = athlete_folder.find(folder) / "log.md"
        lines = path.read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, OSError):
        return {}
    end = today or datetime.date.today()
    since, until = (end - datetime.timedelta(days=USAGE_DAYS)).isoformat(), end.isoformat()
    counts = {}
    for line in lines:
        m = LOG_LINE.match(line)
        if m and since <= m.group(1) <= until:  # future-dated lines (the 2030 demo) don't count
            counts[m.group(2)] = counts.get(m.group(2), 0) + 1
    return dict(sorted(counts.items()))


def usage_line(counts):
    runs = ", ".join(f"{k} {v}" for k, v in counts.items()) or "none recorded"
    return f"Skills run, last {USAGE_DAYS} days: {runs}"


def build(kind, text, title=None, counts=None, ver=None, osn=None):
    """→ (title, body, url). `counts` None = no usage summary. Shortens `text` until the URL fits."""
    text = text.strip()
    lines = text.splitlines()
    if not title and len(lines) > 1:  # the first line becomes the title, so the body starts after it
        title, text = lines[0], "\n".join(lines[1:]).strip()
    title = (title or (lines or [kind])[0]).strip()[:80]
    ver, osn = ver or version(), osn or os_name()
    extra = [usage_line(counts)] if counts is not None else []
    cut = len(text)
    while True:
        words = text if cut == len(text) else text[:cut].rstrip() + SHORTENED
        if kind == "problem":
            # bug.yml field ids; the privacy box can't be prefilled, so the user ticks it on the page.
            actual = "\n\n".join([words, *extra])
            q = {"template": "bug.yml", "title": title, "version": ver, "platform": osn, "actual": actual}
            body = f"CoAIch version: {ver}\nWhere it runs: {osn}\nWhat happened instead:\n{actual}"
            url = f"https://github.com/{REPO}/issues/new?" + urlencode(q, quote_via=quote)
        else:
            body = "\n".join([words, "", "---", f"CoAIch {ver} · {osn}", *extra])
            q = {"category": "ideas" if kind == "idea" else "q-a", "title": title, "body": body}
            url = f"https://github.com/{REPO}/discussions/new?" + urlencode(q, quote_via=quote)
        if len(url) <= MAX_URL or cut == 0:
            return title, body, url
        cut = max(0, cut - (len(url) - MAX_URL) // 9 - 1)  # one character encodes to at most 9 URL characters


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("draft")
    d.add_argument("--kind", required=True, choices=["idea", "problem", "question"])
    d.add_argument("--text-file", required=True)
    d.add_argument("--title")
    d.add_argument("--usage", action="store_true")
    d.add_argument("--dir")
    a = p.parse_args(argv)
    try:
        text = Path(a.text_file).read_text(encoding="utf-8")
    except OSError as e:
        print(f"can't read the text file: {e}", file=sys.stderr)
        return 1
    if not text.strip():
        print("the text file is empty: write the user's words into it first", file=sys.stderr)
        return 1
    found = warnings((a.title or "") + "\n" + text)
    if found:
        print("WARNING: these look like personal data; ask the user to remove them:")
        print("\n".join(f"- {what}: {s}" for what, s in found))
        print()
    title, body, url = build(a.kind, text, a.title, usage(a.dir) if a.usage else None)
    print(f"TITLE: {title}\n\nBODY:\n{body}\n\nURL: {url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
