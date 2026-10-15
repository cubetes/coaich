#!/usr/bin/env python3
"""SessionStart hook (hooks/hooks.json): in an athlete folder, tell Claude to coach only through the CoAIch skills.

The safeguards live in the scripts the skills run (the medical stop, the eating-disorder question, the wellbeing
gate). The evals found that a plain question ("how many calories should I eat?") could be answered from general
knowledge without loading a skill, so no safeguard ran. Whatever this hook prints is added to the session's context.
Outside an athlete folder it prints nothing, so other projects are untouched. It never fails the session.
"""
import json
import os
import sys
from pathlib import Path

from photo_guard import athlete_folder

CONTEXT = """This session works in a CoAIch athlete folder ({folder}).
Coach only through the CoAIch skills. For any question about training, loads, programs, nutrition (calories, protein,
macros, meals, weight loss or gain), body composition or progress photos, load the matching skill first (progression,
weekly-review, program-build, nutrition, physique, adapt, roadmap, safety) and follow it. Never give calorie, macro,
load or program numbers from general knowledge here: the skills' scripts apply this athlete's safeguards (the medical
stop, the eating-disorder question, the experimental switch, age limits) before any number. If coaich.md says
safety_status: stop, run the safety skill and change nothing. Never open an original photo; only the photo copies the
plugin filed in photos/."""


def main():
    try:
        cwd = Path(json.loads(sys.stdin.read()).get("cwd") or os.getcwd()).resolve()
        folder = athlete_folder(cwd)
    except Exception:  # noqa: BLE001  a context hint must never stop a session from starting
        return 0
    if folder:
        print(CONTEXT.format(folder=folder))
    return 0


if __name__ == "__main__":
    sys.exit(main())
