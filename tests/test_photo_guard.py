"""photo_guard.py: the PreToolUse hook that keeps Claude from opening a photo the plugin has not anonymised.

Every refusal path has a test (CLAUDE.md photo rule). Synthetic paths and folders only; no real image is read.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

import support  # noqa: F401  (puts scripts/ on sys.path)

GUARD = os.path.join(support.SCRIPTS, "photo_guard.py")


class PhotoGuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="coaich-test-")
        self.addCleanup(shutil.rmtree, self.tmp)
        self.athlete = os.path.join(self.tmp, "athlete")
        os.makedirs(os.path.join(self.athlete, "photos", "2030-01-06"))
        with open(os.path.join(self.athlete, "coaich.md"), "w") as fh:
            fh.write("language: en\n")
        self.elsewhere = os.path.join(self.tmp, "project")
        os.makedirs(self.elsewhere)

    def hook(self, file_path, cwd=None, raw=None, tool="Read"):
        body = raw if raw is not None else json.dumps({
            "hook_event_name": "PreToolUse", "tool_name": tool, "cwd": cwd or self.athlete,
            "tool_input": {"file_path": file_path}})
        return subprocess.run([sys.executable, GUARD], input=body, capture_output=True, text=True)

    def blocked(self, r):
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("photos.py file", r.stderr)

    def test_an_original_outside_the_folder_is_blocked(self):
        self.blocked(self.hook(os.path.join(self.tmp, "Pictures", "IMG_0001.HEIC")))
        self.blocked(self.hook(os.path.join(self.tmp, "Pictures", "front.jpg")))

    def test_an_image_elsewhere_in_the_folder_is_blocked(self):
        self.blocked(self.hook(os.path.join(self.athlete, "originals", "front.jpg")))
        self.blocked(self.hook("originals/front.jpeg"))                                     # relative to cwd
        self.blocked(self.hook(os.path.join(self.athlete, "photos", "front.jpg")))          # not in a dated set
        self.blocked(self.hook(os.path.join(self.athlete, "photos", "2030-01-06", "me.jpg")))  # not a pose name
        self.blocked(self.hook(os.path.join(self.athlete, "photos", "2030-01-06", "front.png")))

    def test_a_link_to_an_original_named_like_a_filed_copy_is_blocked(self):
        original = os.path.join(self.tmp, "Pictures", "front.jpg")
        os.makedirs(os.path.dirname(original))
        open(original, "wb").close()
        os.symlink(original, os.path.join(self.athlete, "photos", "2030-01-06", "front.jpg"))
        self.blocked(self.hook(os.path.join(self.athlete, "photos", "2030-01-06", "front.jpg")))

    def test_an_image_read_from_outside_into_an_athlete_folder_is_blocked(self):
        self.blocked(self.hook(os.path.join(self.athlete, "originals", "front.jpg"), cwd=self.elsewhere))

    def test_unreadable_hook_input_blocks_when_it_names_an_image(self):
        self.blocked(self.hook(None, raw='{"tool_input": {"file_path": "x.jpg"'))           # cut-off JSON
        self.assertEqual(self.hook(None, raw="not json at all").returncode, 0)              # names no image

    def test_filed_anonymised_copies_are_allowed(self):
        for pose in ("front", "side", "back", "front-relaxed", "front-flexed", "side-left", "side-right",
                     "back-relaxed", "back-flexed"):
            r = self.hook(os.path.join(self.athlete, "photos", "2030-01-06", f"{pose}.jpg"))
            self.assertEqual(r.returncode, 0, (pose, r.stderr))

    def test_other_files_and_other_projects_are_left_alone(self):
        for path in ("plan/CURRENT.md", "data/sets.csv", "notes.txt", os.path.join(self.tmp, "x.py")):
            self.assertEqual(self.hook(path).returncode, 0, path)
        self.assertEqual(self.hook(os.path.join(self.elsewhere, "diagram.png"), cwd=self.elsewhere).returncode, 0)
        self.assertEqual(self.hook("shot.jpg", tool="Write").returncode, 0)  # only Read is guarded

    def test_every_pose_photos_py_files_is_allowed(self):
        import photo_guard
        import photos
        self.assertLessEqual(set(photos.POSES), set(photo_guard.FILED_POSES))


if __name__ == "__main__":
    unittest.main()
