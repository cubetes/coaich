"""Every reference a skill makes resolves: skill handoffs, plugin paths, script subcommands and relative links.

A renamed skill, script or subcommand would otherwise break onboard or the weekly review silently: nothing runs the
skill text until a user does.
"""
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HANDOFF = re.compile(r"Skill tool with `([a-z-]+)`|[Tt]he `([a-z-]+)` skill")
PLUGIN_PATH = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/([A-Za-z0-9_./-]+)")
SUBCOMMAND = re.compile(r"\$\{CLAUDE_PLUGIN_ROOT\}/(scripts/[A-Za-z0-9_]+\.py)\"? +([a-z][a-z-]*)\b")
LINK = re.compile(r"\]\(([^)\s#]+)(?:#[^)]*)?\)")


def markdown(*dirs):
    for top in dirs:
        for d, _, files in os.walk(os.path.join(ROOT, top)):
            for name in sorted(files):
                if name.endswith(".md"):
                    path = os.path.join(d, name)
                    with open(path, encoding="utf-8") as fh:
                        for n, line in enumerate(fh, 1):
                            yield os.path.relpath(path, ROOT), n, line


def subcommands(path):
    """The subcommands a script's argparse offers, from its own --help ({a,b,c}); None when it has none."""
    if not os.path.exists(path):
        return None
    r = subprocess.run([sys.executable, path, "--help"], capture_output=True, text=True, cwd=ROOT)
    m = re.search(r"\{([a-z-]+(?:,[a-z-]+)*)\} \.\.\.", r.stdout)  # argparse prints subcommands as {a,b} ...
    return set(m.group(1).split(",")) if m else None


class SkillRefsTest(unittest.TestCase):
    def test_handoffs_name_an_existing_skill(self):
        bad, seen = [], 0
        for rel, n, line in markdown("skills"):
            for m in HANDOFF.finditer(line):
                seen += 1
                name = m.group(1) or m.group(2)
                if not os.path.exists(os.path.join(ROOT, "skills", name, "SKILL.md")):
                    bad.append(f"{rel}:{n}: no skills/{name}/SKILL.md")
        self.assertGreaterEqual(seen, 10, "the handoff pattern found almost nothing: is the regex broken?")
        self.assertEqual(bad, [])

    def test_plugin_paths_exist(self):
        bad, seen = [], 0
        for rel, n, line in markdown("skills"):
            for m in PLUGIN_PATH.finditer(line):
                seen += 1
                if not os.path.exists(os.path.join(ROOT, m.group(1))):
                    bad.append(f"{rel}:{n}: ${{CLAUDE_PLUGIN_ROOT}}/{m.group(1)} does not exist")
        self.assertGreaterEqual(seen, 50, "the path pattern found almost nothing: is the regex broken?")
        self.assertEqual(bad, [])

    def test_script_subcommands_exist(self):
        bad, seen, known = [], 0, {}
        for rel, n, line in markdown("skills"):
            for m in SUBCOMMAND.finditer(line):
                script = m.group(1)
                if script not in known:
                    known[script] = subcommands(os.path.join(ROOT, script))
                if known[script] is None:
                    continue  # missing (reported by test_plugin_paths_exist) or no subcommands: the word is an argument
                seen += 1
                if m.group(2) not in known[script]:
                    bad.append(f"{rel}:{n}: {script} has no subcommand '{m.group(2)}'")
        self.assertGreaterEqual(seen, 20, "the subcommand pattern found almost nothing: is the regex broken?")
        self.assertEqual(bad, [])

    def test_agents_are_cheap_read_only_workers(self):
        agents = sorted(os.listdir(os.path.join(ROOT, "agents")))
        self.assertTrue(agents)
        for name in agents:
            with open(os.path.join(ROOT, "agents", name), encoding="utf-8") as fh:
                head = fh.read().split("---")[1]
            fields = dict(line.split(":", 1) for line in head.strip().splitlines())
            self.assertIn(fields["model"].strip(), ("haiku", "sonnet"), name)  # Opus stays the orchestrator
            tools = {x.strip() for x in fields["tools"].split(",")}
            self.assertFalse(tools & {"Write", "Edit", "NotebookEdit", "Agent"}, name)  # workers draft, never write

    def test_delegations_name_an_existing_agent(self):
        bad, seen = [], 0
        for rel, n, line in markdown("skills"):
            for m in re.finditer(r"`coaich:([a-z-]+)`", line):
                seen += 1
                if not os.path.exists(os.path.join(ROOT, "agents", m.group(1) + ".md")):
                    bad.append(f"{rel}:{n}: no agents/{m.group(1)}.md")
        self.assertGreaterEqual(seen, 4)
        self.assertEqual(bad, [])

    def test_relative_links_resolve(self):
        bad = []
        for rel, n, line in markdown("skills", "docs", "references"):
            for m in LINK.finditer(line):
                target = m.group(1)
                if re.match(r"[a-z]+:", target) or target.startswith("/"):
                    continue
                if not os.path.exists(os.path.normpath(os.path.join(ROOT, os.path.dirname(rel), target))):
                    bad.append(f"{rel}:{n}: {target}")
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
