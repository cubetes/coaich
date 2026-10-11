"""Test helpers: a throwaway athlete folder and a way to run an importer like a user would."""
import csv
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts")
FIXTURES = os.path.join(HERE, "fixtures")
sys.path.insert(0, SCRIPTS)


def fixture(name):
    return os.path.join(FIXTURES, name)


def make_folder(test, settings="athlete_coaich.md"):
    d = tempfile.mkdtemp(prefix="coaich-test-")
    test.addCleanup(shutil.rmtree, d)
    if settings:
        shutil.copyfile(fixture(settings), os.path.join(d, "coaich.md"))
    return d


def run(script, *args, ok=True):
    env = dict(os.environ, TZ="UTC")  # Hevy API times are UTC; pin local time for the tests
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *args],
                       capture_output=True, text=True, env=env)
    if ok and r.returncode != 0:
        raise AssertionError(f"{script} failed:\n{r.stdout}\n{r.stderr}")
    return r


def rows(folder, name):
    path = os.path.join(folder, "data", name)
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def text(folder, name):
    with open(os.path.join(folder, "data", name), encoding="utf-8") as fh:
        return fh.read()
