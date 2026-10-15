"""athlete_folder.py stop-wording: the medical stop is printed by a script, so no model paraphrases it.

Found by the evals: models softened the stop ("it will probably stop me") or edged towards a diagnosis ("can be a sign
of a heart problem"). The script prints the safety skill's own sentences; these tests hold the two together.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

import support  # noqa: F401  (puts scripts/ on sys.path)
import athlete_folder as af  # noqa: E402

ROOT = os.path.dirname(support.SCRIPTS)
SCRIPT = os.path.join(support.SCRIPTS, "athlete_folder.py")


def flat(text):
    return " ".join(re.sub(r"[*_>]", " ", text).split())


class StopWordingTest(unittest.TestCase):
    def run_cli(self, *argv):
        return subprocess.run([sys.executable, SCRIPT, "stop-wording", *argv], capture_output=True, text=True)

    def test_every_sentence_is_the_safety_skill_word_for_word(self):
        sources = {"en": "skills/safety/SKILL.md", "es": "skills/safety/copy-es.md"}
        for lang, path in sources.items():
            with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
                skill = flat(fh.read())
            for key, sentence in af.STOP_WORDING[lang].items():
                self.assertIn(flat(sentence), skill, f"{lang}/{key} drifted from {path}")

    def test_a_stop_prints_the_stop_and_the_clearance_sentence(self):
        r = self.run_cli("--reasons", "heart")
        self.assertEqual(r.returncode, 0, r.stderr)
        w = af.STOP_WORDING["en"]
        self.assertEqual(r.stdout.split("\n\n"), [w["stop"], w["clearance"], w["clearance_sentence"] + "\n"])

    def test_chest_pain_and_fainting_lead_with_the_urgent_line(self):
        for reason in ("chest-pain", "fainting"):
            out = self.run_cli("--reasons", f"surgery,{reason}").stdout
            self.assertTrue(out.startswith(af.STOP_WORDING["en"]["urgent"]), reason)

    def test_spanish(self):
        out = self.run_cli("--reasons", "chest-pain", "--lang", "es").stdout
        self.assertIn("Confirmo que un médico me ha autorizado a entrenar fuerza.", out)
        self.assertTrue(out.startswith("Deja de entrenar ahora."))

    def test_reads_the_folder_and_refuses_when_there_is_no_stop(self):
        d = tempfile.mkdtemp(prefix="coaich-test-")
        self.addCleanup(shutil.rmtree, d)
        with open(os.path.join(d, "coaich.md"), "w") as fh:
            fh.write("language: es\nsafety_status: stop\nsafety_reasons: [fainting]\n")
        out = self.run_cli("--dir", d)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertTrue(out.stdout.startswith("Deja de entrenar ahora."))
        with open(os.path.join(d, "coaich.md"), "w") as fh:
            fh.write("language: en\nsafety_status: go\nsafety_reasons: []\n")
        r = self.run_cli("--dir", d)
        self.assertEqual((r.returncode, r.stdout), (1, ""))


if __name__ == "__main__":
    unittest.main()
