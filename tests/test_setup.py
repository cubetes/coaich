"""setup.py: the /setup answers in coaich.md and the local checks. Synthetic files only."""
import os
import shutil
import tempfile
import unittest
import zipfile

from support import fixture, run  # support puts scripts/ on sys.path
import athlete_folder as af  # noqa: E402
import setup  # noqa: E402


class SetupTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="coaich-test-")
        self.addCleanup(shutil.rmtree, self.dir)
        af.init(self.dir)

    def write(self, name, text, mode="w"):
        path = os.path.join(self.dir, name)
        with open(path, mode) as f:
            f.write(text)
        return path

    def read(self):
        with open(os.path.join(self.dir, "coaich.md"), encoding="utf-8") as f:
            return f.read()

    def status(self, results, what):
        return [r for r in results if r[1] == what][-1]

    # ---------------------------------------------------------------- coaich.md keys

    def test_template_defaults(self):
        for key, value in (("runtime", "claude-code"), ("link", "file"), ("language", "en"), ("units", "kg")):
            self.assertEqual(af.setting(self.dir, key), value)
        self.assertEqual(setup.sources(self.dir), [])

    def test_save_changes_only_given_keys(self):
        before = self.read()
        setup.save(self.dir, sources=["strong-csv", "hevy-mcp"], units="lb")
        self.assertEqual(setup.sources(self.dir), ["strong-csv", "hevy-mcp"])
        self.assertEqual(af.setting(self.dir, "units"), "lb")
        self.assertEqual(af.setting(self.dir, "language"), "en")
        after = self.read()
        changed = [b for a, b in zip(before.splitlines(), after.splitlines()) if a != b]
        self.assertEqual(len(changed), 2, changed)
        self.assertIn("# kg | lb", after)  # trailing comments kept
        setup.save(self.dir, language="es")
        self.assertEqual(setup.sources(self.dir), ["strong-csv", "hevy-mcp"])  # untouched by a later run

    def test_none_clears_sources(self):
        setup.save(self.dir, sources=["opengym"])
        setup.save(self.dir, sources=["none"])
        self.assertEqual(setup.sources(self.dir), [])

    def test_bad_values_write_nothing(self):
        before = self.read()
        for kw in ({"sources": ["fitbit"]}, {"runtime": "other"}, {"link": "server"}, {"units": "stone"}):
            with self.assertRaises(ValueError):
                setup.save(self.dir, **{"language": "es", **kw})
        self.assertEqual(self.read(), before)

    def test_save_cli(self):
        out = run("setup.py", "save", "--dir", self.dir, "--sources", "apple-health,hevy-csv", "--link", "file").stdout
        self.assertIn("data_sources: [apple-health, hevy-csv]", out)
        self.assertEqual(setup.sources(self.dir), ["apple-health", "hevy-csv"])

    # ---------------------------------------------------------------- checks

    def test_python_version(self):
        self.assertEqual(self.status(setup.check(self.dir, version=(3, 9, 0)), "python")[0], "ok")
        self.assertEqual(self.status(setup.check(self.dir, version=(3, 8, 10)), "python")[0], "fix")

    def test_athlete_folder(self):
        self.assertEqual(self.status(setup.check(self.dir), "athlete folder")[0], "ok")
        empty = tempfile.mkdtemp(prefix="coaich-test-")
        self.addCleanup(shutil.rmtree, empty)
        r = self.status(setup.check(empty), "athlete folder")
        self.assertEqual(r[0], "fix")
        self.assertIn("/onboard", r[2])

    def test_strong_export(self):
        good = fixture("strong_semicolon_kg.csv")
        self.assertEqual(self.status(setup.check(self.dir, {"strong-csv": good}), "strong-csv")[0], "ok")
        bad = self.write("bad.csv", "a,b\n1,2\n")
        r = self.status(setup.check(self.dir, {"strong-csv": bad}), "strong-csv")
        self.assertEqual(r[0], "fix")
        self.assertIn("Export Strong Data", r[2])
        missing = self.status(setup.check(self.dir, {"strong-csv": os.path.join(self.dir, "nope.csv")}),
                              "strong-csv")
        self.assertEqual(missing[0], "fix")
        self.assertIn("does not exist", missing[2])

    def test_hevy_csv_export(self):
        good = fixture("hevy_export_kg.csv")
        self.assertEqual(self.status(setup.check(self.dir, {"hevy-csv": good}), "hevy-csv")[0], "ok")
        bad = self.write("bad.csv", "a,b\n1,2\n")
        self.assertEqual(self.status(setup.check(self.dir, {"hevy-csv": bad}), "hevy-csv")[0], "fix")

    def test_opengym_export(self):
        good = self.write("og.json", '{"workouts": []}')
        self.assertEqual(self.status(setup.check(self.dir, {"opengym": good}), "opengym")[0], "ok")
        bad = self.write("og-bad.json", "{not json")
        self.assertEqual(self.status(setup.check(self.dir, {"opengym": bad}), "opengym")[0], "fix")

    def test_apple_health_zip_is_refused(self):
        z = os.path.join(self.dir, "export.zip")
        with zipfile.ZipFile(z, "w") as f:
            f.writestr("apple_health_export/export.xml", "<HealthData/>")
        r = self.status(setup.check(self.dir, {"apple-health": z}), "apple-health")
        self.assertEqual(r[0], "fix")
        self.assertIn("Health Auto Export", r[2])

    def test_apple_health_json(self):
        good = fixture("hae_export_a.json")
        self.assertEqual(self.status(setup.check(self.dir, {"apple-health": good}), "apple-health")[0], "ok")
        bad = self.write("hae.json", "{}")
        self.assertEqual(self.status(setup.check(self.dir, {"apple-health": bad}), "apple-health")[0], "fix")

    def test_chosen_source_without_file_and_hevy_mcp_are_notes(self):
        setup.save(self.dir, sources=["strong-csv", "hevy-mcp"])
        results = setup.check(self.dir)
        self.assertEqual(self.status(results, "strong-csv")[0], "note")
        self.assertIn("read-only Hevy call", self.status(results, "hevy-mcp")[2])
        self.assertEqual(self.status(results, "experimental")[2], "off")

    def test_swiftc_only_on_macos(self):
        self.assertEqual(self.status(setup.check(self.dir, platform="darwin", which=lambda _: "/x"), "swiftc")[0],
                         "ok")
        self.assertEqual(self.status(setup.check(self.dir, platform="darwin", which=lambda _: None), "swiftc")[0],
                         "note")
        self.assertFalse([r for r in setup.check(self.dir, platform="linux") if r[1] == "swiftc"])

    def test_check_cli_exit_code(self):
        run("setup.py", "check", "--dir", self.dir, "--strong", fixture("strong_semicolon_kg.csv"))
        r = run("setup.py", "check", "--dir", self.dir, "--strong", os.path.join(self.dir, "nope.csv"), ok=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("fix  strong-csv", r.stdout)


if __name__ == "__main__":
    unittest.main()
