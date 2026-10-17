#!/usr/bin/env python3
"""PreToolUse hook (hooks/hooks.json): Claude never opens a photo the plugin has not anonymised.

Reads the hook JSON on stdin. A Read of an image is blocked (exit 2, the reason on stderr) when the session works
in an athlete folder or the image sits in one, unless the image is a filed copy: <athlete folder>/photos/
YYYY-MM-DD/<pose>.jpg, which photos.py wrote after removing the face and the metadata. Fails closed: input that
cannot be read but names an image is blocked. Anything else, and every other project, passes untouched.

A second layer only: photos.py never copies an original in, and skills/physique says never to open one. It does
not see shell commands (a `cat` of a picture), which the skills never run.
"""
import json
import os
import re
import sys
from pathlib import Path

MARKER = "coaich.md"
IMAGE = re.compile(r"\.(jpe?g|png|heic|heif|webp|tiff?|gif|bmp|dng|raw|cr2|nef|arw)$", re.I)
IMAGE_IN_TEXT = re.compile(r"[^\"'\s]+\.(jpe?g|png|heic|heif|webp|tiff?|gif|bmp|dng|raw|cr2|nef|arw)\b", re.I)
# Every pose photos.py files: today's three, and the six-photo protocol planned for 0.11 (docs/roadmap.md).
FILED_POSES = ("front", "side", "back",
               "front-relaxed", "front-flexed", "side-left", "side-right", "back-relaxed", "back-flexed")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}$")
REASON = ("CoAIch: this photo has not been anonymised, so it is not opened. File it with the physique skill "
          "(photos.py file), which removes the face and the metadata on this computer first, then read the filed "
          "copy in photos/YYYY-MM-DD/.")


def athlete_folder(start):
    """The nearest folder at or above `start` holding coaich.md, or None."""
    for d in (start, *start.parents):
        if (d / MARKER).is_file():
            return d
    return None


def filed_copy(path):
    """True for <athlete folder>/photos/YYYY-MM-DD/<pose>.jpg (path already resolved, links followed)."""
    day, photos = path.parent, path.parent.parent
    return (path.suffix == ".jpg" and path.stem in FILED_POSES and DATE.match(day.name) is not None
            and photos.name == "photos" and (photos.parent / MARKER).is_file())


def decide(raw):
    """→ None to allow, or the reason to block."""
    try:
        event = json.loads(raw)
        if event.get("tool_name", "Read") != "Read":
            return None
        file_path = (event.get("tool_input") or {}).get("file_path") or ""
        cwd = Path(event.get("cwd") or os.getcwd())
    except (ValueError, AttributeError, TypeError):
        return REASON if IMAGE_IN_TEXT.search(raw or "") else None
    if not IMAGE.search(file_path):
        return None
    try:
        path = (cwd / file_path).resolve()
        if athlete_folder(cwd.resolve()) is None and athlete_folder(path.parent) is None:
            return None  # another project: not ours to guard
        return None if filed_copy(path) else REASON
    except (OSError, RuntimeError, ValueError):
        return REASON


def main():
    reason = decide(sys.stdin.read())
    if reason:
        print(reason, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
