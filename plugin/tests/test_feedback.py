import datetime
import os
import unittest
from urllib.parse import parse_qs, urlsplit

from support import make_folder, run  # support also puts scripts/ on the path
import feedback  # noqa: E402

TODAY = datetime.date(2030, 3, 31)
LOG = """# Log

One line per skill run.

- 2029-11-01 · progression · too old to count
- 2030-03-01 · weekly-review · 18/21 targets met, private result text
- 2030-03-08 · weekly-review · 19/21 targets met
- 2030-03-08 · progression · 3 go up
- 2030-03-09 · Not A Skill · ignored
"""


def query(url):
    return {k: v[0] for k, v in parse_qs(urlsplit(url).query, keep_blank_values=True).items()}


class BuildTest(unittest.TestCase):
    def test_idea_and_question_go_to_discussions(self):
        for kind, category in (("idea", "ideas"), ("question", "q-a")):
            title, body, url = feedback.build(kind, "Add a rest timer & more?\nThanks", ver="9.9.9", osn="TestOS 1")
            self.assertTrue(url.startswith("https://github.com/cubetes/coaich/discussions/new?"), url)
            q = query(url)
            self.assertEqual((q["category"], q["title"], q["body"]), (category, "Add a rest timer & more?", body))
            self.assertNotIn(" ", url)
            self.assertIn("%26", url)  # "&" in the text never splits the query
            self.assertIn("CoAIch 9.9.9 · TestOS 1", body)

    def test_problem_prefills_the_bug_form(self):
        title, body, url = feedback.build("problem", "Import fails", ver="9.9.9", osn="TestOS 1")
        self.assertTrue(url.startswith("https://github.com/cubetes/coaich/issues/new?"), url)
        q = query(url)
        self.assertEqual(q, {"template": "bug.yml", "title": "Import fails", "version": "9.9.9",
                             "platform": "TestOS 1", "actual": "Import fails"})
        self.assertNotIn("privacy", url)  # the user ticks the privacy box on the page

    def test_real_version_and_os(self):
        _, body, _ = feedback.build("idea", "x")
        self.assertIn(f"CoAIch {feedback.version()} · {feedback.os_name()}", body)
        self.assertRegex(feedback.version(), r"^\d+\.\d+\.\d+$")
        self.assertTrue(feedback.os_name())

    def test_long_text_is_shortened_to_fit(self):
        for kind in ("idea", "problem"):
            text = "é" * 5000 + "END"
            _, body, url = feedback.build(kind, text, title="t", ver="1.0.0", osn="TestOS 1")
            self.assertLessEqual(len(url), feedback.MAX_URL)
            self.assertIn("(shortened)", body)
            self.assertNotIn("END", body)
            self.assertGreater(len(url), feedback.MAX_URL - 200)  # shortened only as much as needed
        _, body, _ = feedback.build("idea", "short", ver="1.0.0", osn="TestOS 1")
        self.assertNotIn("(shortened)", body)


class UsageTest(unittest.TestCase):
    def test_counts_skill_names_only_and_only_when_asked(self):
        d = make_folder(self)
        with open(os.path.join(d, "log.md"), "w", encoding="utf-8") as f:
            f.write(LOG)
        counts = feedback.usage(d, TODAY)
        self.assertEqual(counts, {"progression": 1, "weekly-review": 2})
        _, body, url = feedback.build("idea", "x", counts=counts, ver="1.0.0", osn="TestOS 1")
        self.assertIn("Skills run, last 90 days: progression 1, weekly-review 2", body)
        for private in ("targets met", "2030-03", "Not A Skill", "too old"):
            self.assertNotIn(private, body)
        _, body, _ = feedback.build("idea", "x", ver="1.0.0", osn="TestOS 1")
        self.assertNotIn("Skills run", body)

    def test_future_dated_lines_do_not_count(self):
        # the demo athlete lives in 2030: run today, its log must not count as "the last 90 days"
        d = make_folder(self)
        with open(os.path.join(d, "log.md"), "w", encoding="utf-8") as f:
            f.write(LOG + "- 2030-04-01 · import · tomorrow\n")
        self.assertEqual(feedback.usage(d, TODAY), {"progression": 1, "weekly-review": 2})

    def test_first_line_is_the_title_not_repeated_in_the_body(self):
        title, body, _ = feedback.build("idea", "Add a deload button\nWhen I travel I want a lighter week.",
                                        ver="1.0.0", osn="TestOS 1")
        self.assertEqual(title, "Add a deload button")
        self.assertTrue(body.startswith("When I travel"), body)
        title, body, _ = feedback.build("idea", "One line only", ver="1.0.0", osn="TestOS 1")
        self.assertEqual(title, "One line only")
        self.assertIn("One line only", body)

    def test_missing_log_or_folder(self):
        self.assertEqual(feedback.usage(make_folder(self), TODAY), {})
        self.assertEqual(feedback.usage(make_folder(self, settings=None), TODAY), {})
        self.assertIn("none recorded", feedback.usage_line({}))


class WarningTest(unittest.TestCase):
    def test_flags_personal_looking_text(self):
        found = feedback.warnings("Mail sam@example.com or +34 600 000 000. Born 01/02/2001, 80.5 kg, 15 %, 180cm")
        kinds = [w for w, _ in found]
        self.assertEqual(sorted(set(kinds)), ["body number", "date (a birth date?)", "email address", "phone number"])
        self.assertIn(("body number", "80.5 kg"), found)
        self.assertIn(("body number", "180cm"), found)

    def test_plain_text_passes(self):
        self.assertEqual(feedback.warnings("The weekly review crashes after week 12 in version 0.2.0"), [])

    def test_cli_warns_but_still_drafts(self):
        d = make_folder(self)
        path = os.path.join(d, "words.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("I weigh 80 kg and the import fails")
        out = run("feedback.py", "draft", "--kind", "problem", "--text-file", path, "--dir", d).stdout
        self.assertIn("WARNING", out)
        self.assertIn("- body number: 80 kg", out)
        self.assertIn("URL: https://github.com/cubetes/coaich/issues/new?template=bug.yml", out)
        self.assertNotIn("Skills run", out)
        out = run("feedback.py", "draft", "--kind", "idea", "--text-file", path, "--usage", "--dir", d).stdout
        self.assertIn("Skills run, last 90 days: none recorded", out)


if __name__ == "__main__":
    unittest.main()
