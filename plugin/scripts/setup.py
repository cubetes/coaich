#!/usr/bin/env python3
"""How CoAIch runs and where its data comes from: save the /setup answers in coaich.md and check what can be
checked on this computer.

Usage:
  setup.py save [--dir D] [--runtime claude-code] [--sources a,b|none] [--link file] [--language en|es]
                [--units kg|lb]           set only the keys given; every other line of coaich.md is kept
  setup.py check [--dir D] [--strong F] [--hevy-csv F] [--opengym F] [--apple-health F]
                                          one line per check: ok / fix (with what to do) / note; exit 1 on a fix

Read-only towards every export: the importers' own parsers read them, nothing is written or copied.
Python 3.9+ stdlib only.
"""
import argparse
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import athlete_folder as af  # noqa: E402

SOURCES = ("strong-csv", "hevy-mcp", "hevy-csv", "opengym", "apple-health")
CHOICES = {"runtime": ("claude-code",), "link": ("file",), "language": ("en", "es"), "units": ("kg", "lb")}
DEFAULTS = {"runtime": "claude-code", "link": "file", "language": "en", "units": "kg", "experimental": "off"}
MIN_PYTHON = (3, 9)


def sources(folder):
    """The `data_sources` list in coaich.md, e.g. ['strong-csv', 'hevy-mcp']; [] when absent or empty."""
    v = af.setting(folder, "data_sources") or ""
    return [s.strip().strip("`\"'") for s in v.strip("[]").split(",") if s.strip()]


def save(folder, **answers):
    """Write the given answers (None = not given, left as it is) into coaich.md. Raises ValueError on a bad
    value, before anything is written. `sources` is a list; [] or ['none'] means none."""
    lines = {}
    for key, value in answers.items():
        if value is None:
            continue
        if key == "sources":
            picked = [s for s in value if s != "none"]
            bad = [s for s in picked if s not in SOURCES]
            if bad:
                raise ValueError(f"unknown source(s) {bad}; known: {', '.join(SOURCES)}, none")
            lines["data_sources"] = "[" + ", ".join(dict.fromkeys(picked)) + "]"
        elif key in CHOICES:
            if value not in CHOICES[key]:
                raise ValueError(f"{key} must be one of: {', '.join(CHOICES[key])}")
            lines[key] = value
        else:
            raise ValueError(f"unknown setting {key!r}")
    for key, value in lines.items():
        af.set_header(folder, "coaich.md", key, value)
    return lines


def _parse(fn, path):
    """Run an importer's read-only parser; its own error (it exits with a message) becomes the reason."""
    try:
        fn(path)
        return None
    except SystemExit as e:
        return str(e.code)
    except (OSError, ValueError, UnicodeDecodeError) as e:
        return str(e)


def _strong(path):
    import import_strong
    return _parse(import_strong.read_export, path)


def _hevy_csv(path):
    import import_hevy
    return _parse(import_hevy.load, path)


def _opengym(path):
    def read(p):
        with open(p, encoding="utf-8") as fh:
            json.load(fh)
    return _parse(read, path)


def _apple_health(path):
    if str(path).lower().endswith(".zip"):
        try:
            with zipfile.ZipFile(path) as z:
                if not any(n.endswith("export.xml") for n in z.namelist()):
                    return "the zip has no export.xml"
                return None
        except (OSError, zipfile.BadZipFile) as e:
            return f"not a readable zip ({e})"
    import import_apple_health
    return _parse(import_apple_health.parse_file, path)


EXPORTS = {  # source -> (checker, how to get a good file, in one sentence)
    "strong-csv": (_strong, "In Strong, open Settings > Export Strong Data and give me that CSV file."),
    "hevy-csv": (_hevy_csv, "In Hevy, open Settings > Export & Import Data > Export Workouts and give me that CSV."),
    "opengym": (_opengym, "In openGym, export your workouts as JSON and give me that file."),
    "apple-health": (_apple_health, "In the Health app, tap your picture > Export All Health Data and give me "
                                    "export.zip, or give me a Health Auto Export JSON file."),
}


def check(folder=None, paths=None, platform=None, which=shutil.which, version=None):
    """[(status, what, message)], status ok | fix | note. `paths` maps a source to an export file."""
    paths, out = paths or {}, []
    version = version or sys.version_info[:3]
    if tuple(version[:2]) >= MIN_PYTHON:
        out.append(("ok", "python", ".".join(map(str, version))))
    else:
        out.append(("fix", "python", f"Python {'.'.join(map(str, version))} is too old: install Python 3.9 or newer "
                                     "from python.org and run this again."))
    try:
        folder = af.find(folder)
        out.append(("ok", "athlete folder", str(folder)))
        chosen = sources(folder)
        for key, default in DEFAULTS.items():
            out.append(("note", key, af.setting(folder, key) or f"{default} (not set)"))
    except FileNotFoundError:
        out.append(("fix", "athlete folder", "There is no coaich.md here or above: run /onboard in the folder that "
                                             "will hold your training."))
        folder, chosen = None, []
    out.append(("note", "data_sources", ", ".join(chosen) or "none (you log by hand)"))
    for src in dict.fromkeys(chosen + list(paths)):
        if src == "hevy-mcp":
            out.append(("note", src, "checked by Claude with one read-only Hevy call, not by this script"))
        elif src not in EXPORTS:
            out.append(("fix", src, f"Unknown source: pick from {', '.join(SOURCES)}."))
        elif not paths.get(src):
            out.append(("note", src, "no export file given yet; " + EXPORTS[src][1]))
        elif not Path(paths[src]).is_file():
            out.append(("fix", src, f"{paths[src]} does not exist. {EXPORTS[src][1]}"))
        else:
            err = EXPORTS[src][0](paths[src])
            out.append(("fix", src, f"{paths[src]} can't be read: {err}. {EXPORTS[src][1]}") if err
                       else ("ok", src, f"{paths[src]} reads"))
    if (platform or sys.platform) == "darwin":
        out.append(("ok", "swiftc", "found") if which("swiftc") else
                   ("note", "swiftc", "not found; only photo review needs it: run `xcode-select --install`."))
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("save")
    s.add_argument("--dir")
    for key in ("runtime", "link", "language", "units"):
        s.add_argument("--" + key, choices=CHOICES[key])
    s.add_argument("--sources", help="comma list of " + " | ".join(SOURCES) + ", or none")
    c = sub.add_parser("check")
    c.add_argument("--dir")
    for flag, src in (("--strong", "strong-csv"), ("--hevy-csv", "hevy-csv"), ("--opengym", "opengym"),
                      ("--apple-health", "apple-health")):
        c.add_argument(flag, dest=src, metavar="FILE")
    a = p.parse_args(argv)
    if a.cmd == "save":
        try:
            folder = af.find(a.dir)
            done = save(folder, runtime=a.runtime, link=a.link, language=a.language, units=a.units,
                        sources=None if a.sources is None else [x.strip() for x in a.sources.split(",") if x.strip()])
        except (FileNotFoundError, ValueError) as e:
            print(e, file=sys.stderr)
            return 2
        print("\n".join(f"{k}: {v}" for k, v in done.items()) or "nothing to change")
        return 0
    results = check(a.dir, {k: v for k, v in vars(a).items() if k in EXPORTS and v})
    for status, what, msg in results:
        print(f"{status:4} {what}: {msg}")
    return 1 if any(r[0] == "fix" for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
