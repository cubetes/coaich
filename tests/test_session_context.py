"""session_context.py: the SessionStart hook that tells Claude, in an athlete folder only, to coach through the skills.

Found by the evals: asked "how many calories?" in a folder, the model answered from general knowledge without loading
the nutrition skill, so the safeguards in its script never ran. The hook names the rule at the start of the session.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import support  # noqa: F401  (puts scripts/ on sys.path)

HOOK = os.path.join(support.SCRIPTS, "session_context.py")


class SessionContextTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="coaich-test-")
        self.addCleanup(shutil.rmtree, self.tmp)
        self.athlete = os.path.join(self.tmp, "athlete")
        os.makedirs(os.path.join(self.athlete, "plan"))
        with open(os.path.join(self.athlete, "coaich.md"), "w") as fh:
            fh.write("language: en\n")

    def hook(self, cwd, raw=None):
        body = raw if raw is not None else json.dumps({"hook_event_name": "SessionStart", "cwd": cwd})
        return subprocess.run([sys.executable, HOOK], input=body, capture_output=True, text=True)

    def test_in_an_athlete_folder_the_coaching_rule_is_added(self):
        for cwd in (self.athlete, os.path.join(self.athlete, "plan")):
            r = self.hook(cwd)
            self.assertEqual(r.returncode, 0, r.stderr)
            text = r.stdout
            for must in ("nutrition", "calorie", "skill", "safety_status", "photo", "verify", "clerk"):
                self.assertIn(must, text, cwd)

    def test_other_projects_get_nothing(self):
        r = self.hook(self.tmp)
        self.assertEqual((r.returncode, r.stdout), (0, ""))

    def test_unreadable_input_never_breaks_the_session(self):
        r = self.hook(None, raw="not json")
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
