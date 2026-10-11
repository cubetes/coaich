#!/usr/bin/env python3
"""Pre-publish checks for the public repo: iCloud duplicates, image metadata, real-data guard.

Usage: python3 scripts/check_public.py [ROOT]      exit 1 and list every hit
       python3 scripts/check_public.py --self-test
Secret scanning is separate (gitleaks + trufflehog, see scripts/checks.sh and CI).
"""
import os
import re
import sys
import tempfile
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD = os.path.join(HERE, "real-data-guard.txt")
SELF = {"scripts/real-data-guard.txt", "scripts/check_public.py"}  # they name the patterns they hunt
DUPE = re.compile(r" 2(\.[^/]*)?$")  # iCloud conflict copies: "File 2.swift", "Folder 2"
FIXTURE = re.compile(r"(^|/)(Tests|UITests|WatchUITests|Fixtures|examples)/|Demo|Fixture|Previews")
IMAGE = (".png", ".jpg", ".jpeg", ".heic", ".webp", ".tif", ".tiff", ".gif")
# EXIF/XMP/text metadata markers in PNG, JPEG, WebP, HEIC and TIFF files.
META = (b"Exif\x00\x00", b"eXIf", b"tEXt", b"iTXt", b"zTXt", b"<x:xmpmeta", b"XMP ", b"EXIF")


def load_guard(path=GUARD):
    rules = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        scope, _, rx = line.partition(": ")
        if scope not in ("all", "fixtures") or not rx:
            sys.exit(f"bad guard line: {line!r}")
        rules.append((scope, re.compile(rx)))
    return rules


def walk(root):
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x != ".git"]
        for name in dirs + [f for f in files if f != ".git"]:  # a worktree's .git is a file
            yield os.path.relpath(os.path.join(d, name), root), name in files


def check(root, rules):
    hits = []
    for rel, is_file in walk(root):
        if DUPE.search(os.path.basename(rel)):
            hits.append(f"{rel}: iCloud duplicate name")
        if not is_file or rel in SELF:
            continue
        data = open(os.path.join(root, rel), "rb").read()
        if rel.lower().endswith(IMAGE):
            found = [m.decode(errors="replace").strip() for m in META if m in data]
            if found:
                hits.append(f"{rel}: image metadata {found} (strip it before publishing)")
            continue
        try:
            text = unicodedata.normalize("NFC", data.decode("utf-8"))
        except UnicodeDecodeError:
            continue  # other binaries (fonts) carry no personal text we can grep
        fixture = bool(FIXTURE.search(rel))
        for n, line in enumerate(text.splitlines(), 1):
            for scope, rx in rules:
                if (scope == "all" or fixture) and rx.search(line):
                    hits.append(f"{rel}:{n}: real-data guard /{rx.pattern}/")
    return hits


def self_test():
    rules = load_guard()
    with tempfile.TemporaryDirectory() as t:
        os.makedirs(os.path.join(t, "Tests"))
        files = {
            "ok.swift": "let x = 1 // 2026-10-08 decision date is fine outside fixtures\n",
            "Tests/T.swift": 'let d = "2026-10-07"\n',
            "a.swift": "// Adrián\n",  # decomposed accent
            "b.swift": 'let id = "79D0BB3A"\n',
            "c 2.swift": "",
            "i.png": b"\x89PNG....eXIf....",
            "j.png": b"\x89PNG....IDAT....",
        }
        for name, body in files.items():
            with open(os.path.join(t, name), "wb") as f:
                f.write(body if isinstance(body, bytes) else body.encode())
        out = "\n".join(check(t, rules))
        for want in ("Tests/T.swift:1", "a.swift:1", "b.swift:1", "c 2.swift: iCloud", "i.png: image metadata"):
            assert want in out, (want, out)
        for clean in ("ok.swift", "j.png"):
            assert clean not in out, (clean, out)
    print("self-test ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
        sys.exit(0)
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(HERE)
    hits = check(root, load_guard())
    for h in hits:
        print("FAIL", h)
    print(f"check_public: {len(hits)} hit(s)")
    sys.exit(1 if hits else 0)
