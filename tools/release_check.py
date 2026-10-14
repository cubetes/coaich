#!/usr/bin/env python3
"""Release preflight: the tag, the plugin version and the changelog must agree. Prints the release notes.

Usage: python3 tools/release_check.py vX.Y.Z > notes.md     exit 1 with the reason on stderr
       python3 tools/release_check.py --self-test
The notes are the tag's changelog section, word for word. The "tag is on main" check lives in the workflow.
"""
import json
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def notes(tag, root=ROOT):
    m = re.fullmatch(r"v(\d+\.\d+\.\d+)", tag)
    if not m:
        raise ValueError(f"tag {tag!r} is not vX.Y.Z")
    version = m.group(1)
    with open(os.path.join(root, ".claude-plugin/plugin.json"), encoding="utf-8") as f:
        have = json.load(f)["version"]
    if have != version:
        raise ValueError(f"plugin.json says {have}, the tag says {version}")
    with open(os.path.join(root, "CHANGELOG.md"), encoding="utf-8") as f:
        text = f.read()
    # "## 0.3.0 — preview" or "## 1.0.0 — Achilles": the heading starts with the version
    sec = re.search(rf"^## {re.escape(version)}\b.*?$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not sec or not sec.group(1).strip():
        raise ValueError(f"CHANGELOG.md has no '## {version}' section with notes")
    return sec.group(1).strip() + "\n"


def self_test():
    with tempfile.TemporaryDirectory() as t:
        os.makedirs(os.path.join(t, ".claude-plugin"))
        with open(os.path.join(t, ".claude-plugin/plugin.json"), "w") as f:
            json.dump({"version": "0.3.0"}, f)
        with open(os.path.join(t, "CHANGELOG.md"), "w") as f:
            f.write("# Changelog\n\n## Unreleased\n\n## 0.3.0 — preview\n\nAdded\n- x\n\n## 0.2.0 — preview\n\n- y\n")
        assert notes("v0.3.0", t) == "Added\n- x\n", notes("v0.3.0", t)
        for bad, why in (("v0.2.0", "plugin.json says"), ("0.3.0", "not vX.Y.Z"), ("v0.3", "not vX.Y.Z")):
            try:
                notes(bad, t)
            except ValueError as e:
                assert why in str(e), (bad, e)
            else:
                raise AssertionError(bad)
        with open(os.path.join(t, "CHANGELOG.md"), "w") as f:
            f.write("# Changelog\n\n## 0.3.0 — preview\n\n## 0.2.0\n- y\n")
        try:
            notes("v0.3.0", t)
        except ValueError as e:
            assert "no '## 0.3.0' section" in str(e), e
        else:
            raise AssertionError("empty section passed")
    print("self-test ok")


if __name__ == "__main__":
    if sys.argv[1:] == ["--self-test"]:
        self_test()
        sys.exit(0)
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    try:
        sys.stdout.write(notes(sys.argv[1]))
    except ValueError as e:
        sys.exit(f"release check failed: {e}")
