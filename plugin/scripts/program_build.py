#!/usr/bin/env python3
"""Build a starter program from an athlete folder's intake answers.

Usage: python3 program_build.py --dir <athlete folder> [--week N] [--today YYYY-MM-DD] [--dry-run]

Reads `coaich.md` (safety acknowledgement + clearance) and `profile.md` (intake answers in its YAML header, as the
onboard and safety skills write them: templates/athlete/profile.md). Places the athlete (level), picks one of
eight layouts, adapts it (time, goal, priority, age, pain), gates it with program_audit.py, then writes
`plan/program.json` (docs/program-schema.md), the program block of `plan/CURRENT.md` and one line in `log.md`. Exit 0 = written, 1 = the audit refused the program, 2 = stop (the
medical gate, under 16, or unusable answers): nothing is written.

A faithful port of the Release 1 Swift core (AthleteCore `Onboarding`, `Placement`, `StarterProgram`); the
parity test checks every answer cell against it. Rules and their sources: references/starter-programs.md.
"""
import argparse
import copy
import datetime
import json
import os
import re
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import program_audit as pa  # noqa: E402

LEVELS = ["beginner", "intermediate", "advanced"]
AGES = ["under_16", "16_17", "adult", "60_plus"]
HISTORY = ["under_6_months", "6_months_to_2_years", "over_2_years"]
LAST_TRAINED = ["last_3_months", "3_to_12_months", "over_a_year"]
GOALS = ["strength", "muscle", "both"]
AREAS = ["knee", "low_back", "shoulder", "elbow_wrist", "hip", "other"]
REGIONS = {
    "chest": ["HP", "FL"], "back": ["HR", "VR"], "shoulders": ["VP", "LR", "RD"], "arms": ["CU", "TE"],
    "quads": ["SQ", "SM", "KE", "LU"], "glutes_hamstrings": ["HI", "KF"], "calves": ["CA"],
}
HEALTH = ["pregnancy_or_postpartum", "heart_or_circulation", "high_blood_pressure", "chest_pain",
          "dizziness_or_fainting", "doctor_said_no", "recent_operation", "osteoporosis_or_hernia", "other_reason",
          "bone_or_joint_problem", "urine_leak", "diabetes"]
NOT_SERIOUS = {"high_blood_pressure", "osteoporosis_or_hernia", "diabetes", "bone_or_joint_problem", "urine_leak"}
# Diabetes: a warning in the plugin's safety skill (plan §4); the Swift core has no diabetes item (G120 D10).
STRONG_WARNING = {"high_blood_pressure", "osteoporosis_or_hernia", "diabetes"}
EASY_WEEK_EVERY = pa.EASY_WEEK_EVERY

# Copy (copy: lawyer review pending — medical and legal lines).
DISCLAIMER = ("This app does not replace a doctor. If you have a condition, an injury or any doubt about your health, "
              "see one before you train.")
CLEARANCE_NEEDED = ("From your answers, you need a doctor to tell you that you can do strength training before you "
                    "start. Once you have that, confirm it here.")
CLEARANCE_SENTENCES = ("I confirm a doctor has cleared me to do strength training.",
                       "Confirmo que un médico me ha autorizado a entrenar fuerza")
UNDER_AGE = "This app is for ages 16 and over."
AREA_NAMES = {"knee": "Knee", "low_back": "Lower back", "shoulder": "Shoulder", "elbow_wrist": "Elbow or wrist",
              "hip": "Hip", "other": "Somewhere else"}
WARNINGS = {
    "strong_medical": ("With what you ticked, strength training is usually recommended, but talk to your doctor before "
                       "you start and tell them you will lift weights."),
    "left_out_for_pain": "We leave out or change the exercises that load the area you told us about.",
    "stop_if_sharp": "Stop if the pain is sharp.",
    "leak": ("Breathe out on the effort and don't hold your breath. Consider seeing a pelvic-floor "
             "physiotherapist."),
    "supervision": "Train with an adult who knows the lifts.",
}
RED_FLAG = ("{}: that pain should be checked by a physiotherapist or doctor before you load the area. Until then we "
            "leave out the exercises that load it. Once it's been checked, mark it in Settings › Health.")
NOTES = {
    "minimum_dose": "2 days is the minimum dose. Our rule: once you've kept it up for 4 weeks, try 3.",
    "beginner_day_cap": "Our rule: at most 4 days a week for your first 12 weeks.",
    "older_day_cap": "Our rule from 60: up to {} days a week.",
    "short_sessions": ("Shorter sessions grow muscle more slowly than 45–60 minutes, but only if you keep doing "
                       "them."),
    "advanced_scope": "Advanced: general strength and muscle. Not for competition prep.",
    "returning": "You're back after a break: we start easy and check your level in a few weeks.",
    "advanced_check": "At week 6 we offer you Advanced.",
    "older_tempo": "On every rep: lift briskly, lower slowly.",
}
LAYOUT_NAMES = {"fb2b": "Full body, 2 days", "fb3b": "Full body A/B, 3 days", "ul4b": "Upper/lower, 4 days",
                "fb2i": "Full body, 2 days", "fb3i": "Full body, 3 days", "ul4i": "Upper/lower, 4 days",
                "ulf5i": "Upper/lower + full body, 5 days", "ppl6i": "Push/pull/legs, 6 days"}


# ---------------------------------------------------------------- placement

def place(history, last_trained, known_loads):
    """Level from history and recency, never a self-label; every ambiguous answer goes down. A missing
    last_trained counts as the most conservative answer. → {level, returning, promotion_check_week,
    advanced_check_week, row}."""
    last = last_trained or "over_a_year"

    def r(level, returning, promo, adv, row):
        return {"level": level, "returning": returning, "promotion_check_week": promo, "advanced_check_week": adv,
                "row": row}
    if history == "under_6_months":
        return r("beginner", False, None, None, 1)
    if history == "6_months_to_2_years":
        return {"last_3_months": r("intermediate", False, None, None, 2),
                "3_to_12_months": r("beginner", True, 4, None, 3),
                "over_a_year": r("beginner", True, 6, None, 4)}[last]
    if last == "last_3_months":
        return r("advanced", False, None, None, 5) if known_loads else r("intermediate", False, None, 6, 6)
    if last == "3_to_12_months":
        return r("intermediate", True, None, 6, 7)
    return r("beginner", True, 4, None, 8)


PLACEMENT_WHY = {
    1: "under 6 months of lifting",
    2: "6 months to 2 years of lifting, and you trained in the last 3 months",
    3: "6 months to 2 years of lifting, with a long break: we build back up",
    5: "over 2 years, training now, and you know your squat and bench weights",
    6: "over 2 years and training now; at week 6 we offer you Advanced",
    7: "over 2 years, with a break of a few months: we build back up",
    8: "over 2 years, but more than a year off: we build back up",
}


def placement_line(pl):
    why = PLACEMENT_WHY[3 if pl["row"] == 4 else pl["row"]]
    return f"We've put you in {pl['level'].capitalize()}: {why}."


# ---------------------------------------------------------------- templates

def variant(minutes):
    return pa.variant(minutes)


def pick(level, asked, older):
    """Layout for a level and the days asked → (layout, days run, cap note). Every cell has a program."""
    d = min(max(asked, 2), 6)
    if level == "beginner":
        if older and d > 3:
            return "fb3b", 3, ("older_day_cap", 3)
        return {2: ("fb2b", 2, None), 3: ("fb3b", 3, None), 4: ("ul4b", 4, None)}.get(d, ("ul4b", 4, ("beginner_day_cap",)))
    if older and d > 4:
        return "ul4i", 4, ("older_day_cap", 4)
    return {2: ("fb2i", 2, None), 3: ("fb3i", 3, None), 4: ("ul4i", 4, None), 5: ("ulf5i", 5, None)}.get(d, ("ppl6i", 6, None))


def R(id_, sets, role="plain"):
    return (id_, sets, role)


def M(id_, sets):
    return (id_, sets, "main")


def day(title, full, m45, m30, plus75=()):
    """One day in every time variant: 60 = full; 75 = full + plus75 (intermediate and advanced; two entries = an
    antagonist pair); 45 = m45 (id, sets); 30 = m30 antagonist pairs (a, b, sets each)."""
    return {"title": title, "full": list(full), "plus75": list(plus75), "m45": list(m45), "m30": list(m30)}


def days_of(layout):
    squat, bench, rdl = "Barbell_Squat", "Barbell_Bench_Press_-_Medium_Grip", "Romanian_Deadlift"
    row, iso_row, bb_row = "Seated_Cable_Rows", "Leverage_Iso_Row", "Bent_Over_Barbell_Row"
    press, db_press = "Standing_Military_Press", "Dumbbell_Shoulder_Press"
    pulldown, cg_pulldown = "Wide-Grip_Lat_Pulldown", "Close-Grip_Front_Lat_Pulldown"
    leg_press, split, leg_ext = "Leg_Press", "Split_Squat_with_Dumbbells", "Leg_Extensions"
    lying_curl, seated_curl, calf, seated_calf = "Lying_Leg_Curls", "Seated_Leg_Curl", "Standing_Calf_Raises", "Seated_Calf_Raise"
    incline, db_bench, flyes = "Incline_Dumbbell_Press", "Dumbbell_Bench_Press", "Dumbbell_Flyes"
    lateral, cable_lateral, face_pull = "Side_Lateral_Raise", "Cable_Seated_Lateral_Raise", "Face_Pull"
    curl, hammer, overhead = "Dumbbell_Bicep_Curl", "Hammer_Curls", "Cable_Rope_Overhead_Triceps_Extension"
    pushdown = "Triceps_Pushdown"
    if layout in ("fb2b", "fb3b"):
        return [
            day("Full body A", [M(squat, 3), R(bench, 3), R(row, 3), R(rdl, 2, "light"), R(lateral, 2), R(curl, 2)],
                [(squat, 3), (bench, 3), (row, 3), (rdl, 2)], [(squat, row, 3), (bench, rdl, 2)]),
            day("Full body B", [M(rdl, 3), R(press, 3), R(pulldown, 3), R(leg_press, 2, "accessory"),
                                R(incline, 2, "accessory"), R(face_pull, 2)],
                [(rdl, 3), (press, 3), (pulldown, 3), (leg_press, 2)], [(rdl, press, 3), (pulldown, leg_press, 2)]),
        ]
    if layout == "ul4b":
        return [
            day("Upper A", [R(bench, 3), R(row, 3), R(press, 2), R(pulldown, 2), R(lateral, 2), R(curl, 2)],
                [(bench, 3), (row, 3), (press, 2), (pulldown, 2)], [(bench, row, 3), (press, pulldown, 2)]),
            day("Lower A", [M(squat, 3), R(rdl, 3), R(split, 2), R(lying_curl, 2), R(calf, 2), R("Dead_Bug", 2)],
                [(squat, 3), (rdl, 2), (lying_curl, 2), (calf, 2), ("Dead_Bug", 2)],
                [(squat, lying_curl, 3), (rdl, calf, 2)]),
            day("Upper B", [R(incline, 3), R(cg_pulldown, 3), R(db_press, 2), R(iso_row, 2), R(face_pull, 2), R(overhead, 2)],
                [(incline, 3), (cg_pulldown, 3), (db_press, 2), (iso_row, 2)],
                [(incline, cg_pulldown, 3), (db_press, iso_row, 2)]),
            day("Lower B", [M(rdl, 3), R(leg_press, 3), R(split, 2), R(seated_calf, 2), R("Plank", 2)],
                [(rdl, 3), (leg_press, 3), (seated_calf, 2), ("Plank", 2)],
                [(rdl, leg_press, 3), (seated_calf, "Plank", 2)]),
        ]
    if layout == "fb2i":
        return [
            day("Full body A", [M(squat, 4), R(bench, 4), R(row, 3), R(rdl, 2), R(lateral, 2)],
                [(squat, 4), (bench, 3), (row, 3), (rdl, 1)], [(squat, row, 3), (bench, rdl, 2)],
                plus75=[R(curl, 2), R(pushdown, 2)]),
            # Calves only on the 75-minute day: with 6 exercises, calves + dead bug would make 8 (G7 allows 7).
            day("Full body B", [M(rdl, 4), R(pulldown, 3), R(incline, 3), R(press, 2), R(leg_press, 2), R(face_pull, 2)],
                [(rdl, 4), (pulldown, 3), (incline, 2), (leg_press, 2)], [(rdl, press, 3), (leg_press, pulldown, 2)],
                plus75=[R(calf, 2)]),
        ]
    if layout == "fb3i":
        return [
            day("Day 1", [M(squat, 4), R(bench, 3), R(row, 3), R(lying_curl, 3), R(lateral, 2), R(leg_ext, 2)],
                [(squat, 4), (bench, 3), (row, 3), (leg_ext, 2)], [(squat, row, 3), (bench, lying_curl, 2)],
                plus75=[R(curl, 2)]),
            day("Day 2", [M(bench, 4), R(rdl, 3), R(pulldown, 3), R(press, 2), R(leg_press, 2), R(face_pull, 2)],
                [(bench, 4), (rdl, 3), (pulldown, 2), (leg_press, 2)], [(bench, pulldown, 3), (rdl, press, 2)],
                plus75=[R(calf, 2)]),
            day("Day 3", [M(rdl, 4), R(incline, 3), R(iso_row, 3), R(split, 2), R(calf, 3), R(overhead, 2)],
                [(rdl, 4), (incline, 3), (iso_row, 3), (lying_curl, 2)], [(rdl, incline, 3), (iso_row, split, 2)],
                plus75=[R(hammer, 2)]),
        ]
    if layout in ("ul4i", "ulf5i"):
        ul = [
            day("Upper A", [M(bench, 4), R(bb_row, 4), R(press, 3), R(pulldown, 3), R(lateral, 2)],
                [(bench, 4), (bb_row, 3), (press, 2), (pulldown, 2)], [(bench, bb_row, 3), (press, pulldown, 2)],
                plus75=[R(pushdown, 2), R(curl, 2)]),
            day("Lower A", [M(squat, 4), R(rdl, 3), R(leg_press, 3), R(lying_curl, 2), R(calf, 3)],
                [(squat, 4), (rdl, 3), (lying_curl, 2), (calf, 2)], [(squat, lying_curl, 3), (rdl, calf, 2)],
                plus75=[R("Dead_Bug", 2)]),
            # Overhead triceps only on the 75-minute day: with hammer curls it would make 8 exercises (G7 allows 7).
            day("Upper B", [R(incline, 4), R(row, 3), R(db_press, 2), R(cg_pulldown, 3), R(flyes, 2), R(face_pull, 2)],
                [(incline, 4), (row, 3), (db_press, 2), (cg_pulldown, 2)], [(incline, row, 3), (db_press, cg_pulldown, 2)],
                plus75=[R(overhead, 2)]),
            day("Lower B", [M(rdl, 4), R(split, 3), R(leg_ext, 3), R(seated_curl, 2), R(seated_calf, 3)],
                [(rdl, 4), (split, 3), (leg_ext, 2), (seated_calf, 2)], [(rdl, split, 3), (leg_ext, seated_calf, 2)],
                plus75=[R("Plank", 2)]),
        ]
        if layout == "ulf5i":  # 7 exercises (G7): the pushdown is left out, triceps stay above the floor
            ul.append(day("Full body", [R(db_bench, 2), R(pulldown, 2), R(squat, 2), R(lateral, 2), R(face_pull, 2),
                                        R(curl, 3), R(calf, 2)],
                          [(db_bench, 2), (pulldown, 2), (squat, 2), (lateral, 2)],
                          [(db_bench, pulldown, 2), (squat, lateral, 2)]))
        return ul

    def ppl(title, full):  # 45 = the first 4; 30 = those 4 as two pairs, 3 and 2 sets
        ids = [r[0] for r in full]
        return day(title, full, [(r[0], r[1]) for r in full[:4]], [(ids[0], ids[1], 3), (ids[2], ids[3], 2)])
    return [
        ppl("Push A", [M(bench, 3), R(press, 3), R("Flat_Bench_Cable_Flyes", 2), R(cable_lateral, 3), R(overhead, 3)]),
        ppl("Pull A", [R(pulldown, 3), R(row, 3), R("Pullups", 2), R("Reverse_Machine_Flyes", 3),
                       R("Standing_Biceps_Cable_Curl", 3)]),
        ppl("Legs A", [M(squat, 4), R(rdl, 3), R(leg_ext, 3), R(seated_curl, 2), R(calf, 3)]),
        ppl("Push B", [R(incline, 3), R(db_bench, 2), R(lateral, 3), R(pushdown, 2), R(cable_lateral, 2),
                       R("Cable_Crunch", 2)]),
        ppl("Pull B", [R(iso_row, 3), R(cg_pulldown, 3), R(face_pull, 3), R(curl, 2)]),
        ppl("Legs B", [M(rdl, 3), R(split, 3), R(lying_curl, 2), R(seated_calf, 3), R("Knee_Hip_Raise_On_Parallel_Bars", 2)]),
    ]


PRIORITY_PAIR = {
    "chest": ("Barbell_Incline_Bench_Press_-_Medium_Grip", "Incline_Dumbbell_Flyes"),
    "back": ("Weighted_Pull_Ups", "Leverage_Iso_Row"),
    "shoulders": ("Dumbbell_Shoulder_Press", "Side_Lateral_Raise"),
    "arms": ("Barbell_Curl", "Cable_Rope_Overhead_Triceps_Extension"),
    "quads": ("Front_Barbell_Squat", "Leg_Extensions"),
    "glutes_hamstrings": ("Barbell_Hip_Thrust", "Seated_Leg_Curl"),
    "calves": ("Standing_Calf_Raises", "Seated_Calf_Raise"),
}
NOT_FOR_BEGINNERS = {"Bent_Over_Barbell_Row", "Pullups", "Weighted_Pull_Ups", "Barbell_Deadlift", "Front_Barbell_Squat"}
# Bodyweight ladders (easiest first). The last rung is loaded and progresses by load.
LADDERS = {
    "pull": ["Band_Assisted_Pull-Up", "Pullups", "Weighted_Pull_Ups"],
    "push": ["Incline_Push-Up", "Pushups", "Push-Ups_With_Feet_Elevated", "Dumbbell_Bench_Press"],
    "core": ["Dead_Bug", "Plank", "Flat_Bench_Lying_Leg_Raise", "Hanging_Leg_Raise"],
    "squat": ["Chair_Squat", "Goblet_Squat", "Barbell_Squat"],
}
LOADED_RUNGS = {"Weighted_Pull_Ups", "Dumbbell_Bench_Press", "Goblet_Squat", "Barbell_Squat"}


def ladder_of(id_):
    if id_ in LOADED_RUNGS:
        return None
    return next((k for k, rungs in LADDERS.items() if id_ in rungs), None)


# ---------------------------------------------------------------- pain

NEUTRAL = "Dumbbell_Bench_Press_with_Neutral_Grip"


def change(injury, p, id_):
    """What a painful area does to one slot → ("keep",) | ("swap", id) | ("drop",). A red flag not yet checked drops
    every slot that loads the area (low back: every spine exercise too); otherwise a safer exercise, same slot."""
    area = injury["area"]
    active = injury.get("red_flag", False) and not injury.get("checked", False)
    if active and (p in pa.AREA_PATTERNS[area] or area == "low_back" and id_ in pa.SPINE):
        return ("drop",)
    if area == "low_back":
        if id_ not in pa.SPINE:
            return ("keep",)
        to = {"SQ": "Goblet_Squat", "SM": "Leg_Extensions", "HI": "Barbell_Hip_Thrust", "KF": "Barbell_Hip_Thrust",
              "LU": "Bodyweight_Walking_Lunge", "KE": "Bodyweight_Walking_Lunge", "HR": "Leverage_Iso_Row",
              "VP": "Seated_Dumbbell_Press"}.get(p)
        return ("swap", to) if to else ("drop",)
    if area == "shoulder":
        if p == "FL":
            return ("drop",)
        if p == "VR":
            return ("swap", "Close-Grip_Front_Lat_Pulldown")
        if id_ in ("Barbell_Bench_Press_-_Medium_Grip", "Barbell_Incline_Bench_Press_-_Medium_Grip",
                   "Dumbbell_Bench_Press", "Machine_Bench_Press"):
            return ("swap", NEUTRAL)
        if id_ == "Standing_Military_Press":
            return ("swap", "Machine_Shoulder_Military_Press")
        return ("keep",)
    if area == "knee":
        return {"SQ": ("swap", "Leg_Press"), "LU": ("swap", "Barbell_Hip_Thrust"), "KE": ("drop",)}.get(p, ("keep",))
    if area == "hip":
        return {"SQ": ("swap", "Leg_Press"), "HI": ("swap", "Barbell_Glute_Bridge"), "LU": ("drop",)}.get(p, ("keep",))
    if area == "elbow_wrist":
        if id_ in ("Barbell_Bench_Press_-_Medium_Grip", "Barbell_Incline_Bench_Press_-_Medium_Grip"):
            return ("swap", NEUTRAL)
        if id_ == "Standing_Military_Press":
            return ("swap", "Dumbbell_Shoulder_Press")
        if p == "CU":
            return ("swap", "Hammer_Curls")
        if p == "VR" and id_ in ("Pullups", "Weighted_Pull_Ups", "Band_Assisted_Pull-Up"):
            return ("swap", "Close-Grip_Front_Lat_Pulldown")
        return ("keep",)
    return ("keep",)


def allowed(id_, p, injuries):
    """Whether id_ is allowed on a p slot for every injury (a swap onto itself counts as allowed)."""
    return all(change(i, p, id_) in (("keep",), ("swap", id_)) for i in injuries)


# ---------------------------------------------------------------- prescription

def prescription(p, id_, role, level, week, older, goal, leak):
    """Rep range, reps-in-reserve target and rest (s) for a slot."""
    iso = p in pa.ISOLATION
    lad = ladder_of(id_)
    if lad:
        reps = [6, 12] if lad == "pull" else [8, 15]
    elif iso:
        reps = [12, 20] if level == "beginner" else [10, 20]
    elif role in ("light", "accessory"):
        reps = [10, 15]
    elif role == "main" and level != "beginner":
        reps = [4, 6] if goal == "strength" else [6, 10]
    else:
        reps = [8, 12]
    if older and reps[0] < 8:
        reps = [8, 12]  # 60+: no 4–6 bracket
    if iso:
        rir = ([2, 3] if week <= 4 else [1, 2]) if level == "beginner" else [0, 2]
    elif role == "light":
        rir = [3, 3]
    elif level == "beginner":
        rir = [2, 3] if week <= 4 else [1, 2]
    elif role == "main":
        rir = [1, 2] if level == "advanced" else [2, 2]
    else:
        rir = [1, 2]
    # Spine lifts never below 2 left; the leak path keeps squat and hinge at 2 or more.
    if not iso and (id_ in pa.SPINE or leak and p in ("SQ", "SM", "HI")):
        rir = [max(2, rir[0]), max(2, rir[1])]
    if older and week <= 8 and not iso:
        rir = [3, 3]  # 60+: compounds 3 in the tank for 8 weeks
    rest = 75 if iso else 180 if role == "main" or p in ("SQ", "HI") else 120
    return reps, rir, rest


def set_cap(prog):
    if prog["level"] == "beginner" and prog["week"] <= 4 or prog["older"] and prog["week"] <= 8:
        return 2
    return pa.max_sets(prog["level"])


def slug(name, taken):
    folded = unicodedata.normalize("NFKD", name)
    folded = "".join(c for c in folded if not unicodedata.combining(c)).lower()
    base = "-".join(w for w in re.split(r"[^a-z0-9]+", folded) if w)[:37].strip("-")
    root, n, out = base or "gym", 2, base or "gym"
    while out in taken:
        out, n = f"{root}-{n}", n + 1
    return out


# ---------------------------------------------------------------- build

def build(layout, level, days, a, week=1):
    """The layout at a level for the answers a, in their time variant, at week (1-based, counted in sessions done).
    Returns the program dict (program.json shape) with `swaps` (what changed and why) for the explanation."""
    older = a["age"] == "60_plus"
    minutes = min(max(a["minutes"], 30), 75)
    v = variant(minutes)
    goal = None if level == "beginner" else a.get("goal") or "both"
    leak = "urine_leak" in a.get("health", ())
    priority = a.get("priority") if level == "advanced" else None
    prog = {"layout": layout, "level": level, "goal": goal, "minutes": minutes, "variant": v, "days": days,
            "week": week, "older": older, "priority": priority, "pain": copy.deepcopy(a.get("injuries", [])),
            "routines": [], "left_out": [], "swaps": []}
    # The low back last, as it is the most restrictive; `allowed` then drops what two areas disagree on.
    injuries = [i for i in prog["pain"] if i["area"] != "low_back"] + [i for i in prog["pain"] if i["area"] == "low_back"]
    table = days_of(layout)
    if layout == "ulf5i" and priority:
        # 5 days → day 5 is the priority day: its two exercises (4 + 3 sets) + 2 × 2 sets of other regions.
        p1, p2 = PRIORITY_PAIR[priority]
        others = [r[0] for r in table[4]["full"] if pa.PATTERN_OF[r[0]] not in REGIONS[priority] and r[0] not in (p1, p2)]
        o1, o2 = others[0], others[1]
        table[4] = day("Priority", [R(p1, 4), R(p2, 3), R(o1, 2), R(o2, 2)], [(p1, 4), (p2, 3), (o1, 2), (o2, 2)],
                       [(p1, p2, 3), (o1, o2, 2)])
    routine_keys = set()
    for d in table:
        roles = {}
        for r in d["full"] + d["plus75"]:
            roles.setdefault(r[0], r[2])
        if v == 30:
            rows = [x for i, (a1, b1, s) in enumerate(d["m30"])
                    for x in ((a1, s, roles.get(a1, "plain"), i + 1), (b1, s, roles.get(b1, "plain"), i + 1))]
        elif v == 45:
            rows = [(i, s, roles.get(i, "plain"), None) for i, s in d["m45"]]
        else:
            rows = [(i, s, role, None) for i, s, role in d["full"]]
            if v == 75 and level != "beginner":
                rows += [(i, s, role, 1 if len(d["plus75"]) == 2 else None) for i, s, role in d["plus75"]]
        key = slug(d["title"], routine_keys)
        routine_keys.add(key)
        used, slugs, warmed, slots = set(), set(), False, []
        for row_id, sets, role, pair in rows:
            p = pa.PATTERN_OF[row_id]
            id_, swapped, dropped, why = row_id, False, False, []
            if goal == "strength" and role == "main" and p == "HI":
                id_, sets = "Barbell_Deadlift", 3
                why.append("strength goal: the main hinge is the deadlift")
            if older and level == "beginner" and a.get("chair_stand") is False and p == "SQ":
                id_ = "Chair_Squat"
                why.append("60+ and the chair-stand screen: the squat starts at the chair")
            if level == "advanced" and role == "main" and id_ == "Barbell_Bench_Press_-_Medium_Grip" \
                    and not a.get("bench_safeties"):
                id_ = "Dumbbell_Bench_Press"
                why.append("no safety bars or spotter for the bench top set: dumbbells")
            for inj in injuries:
                if dropped:
                    break
                c = change(inj, p, id_)
                if c[0] == "swap":
                    if c[1] != id_:
                        why.append(f"{AREA_NAMES[inj['area']].lower()} pain")
                    swapped = swapped or c[1] != id_
                    id_ = c[1]
                elif c[0] == "drop":
                    dropped = True
            if dropped or not allowed(id_, p, injuries):
                prog["left_out"].append(p)
                continue
            if id_ in used:
                # Never the same exercise twice a day (G7): the column's next allowed one, unless it was a swap.
                nxt = None if swapped else next((x for x in pa.COLUMN[p] if x not in used and allowed(x, p, injuries)), None)
                if nxt is None:
                    prog["left_out"].append(p)
                    continue
                id_ = nxt
            if id_ != row_id:
                prog["swaps"].append({"routine": d["title"], "from": row_id, "to": id_,
                                      "why": "; ".join(why) or "already used that day"})
            used.add(id_)
            s = slug(id_, slugs)
            slugs.add(s)
            reps, rir, rest = prescription(p, id_, role, level, week, older, goal, leak)
            if level == "beginner" and week <= 4:
                sets = 2  # 2 sets in weeks 1–4
            if older and week <= 8:
                sets = min(sets, 2)  # 60+: 2 sets for 8 weeks
            alts = [] if swapped else [x for x in pa.COLUMN[p] if x != id_ and allowed(x, p, injuries)
                                       and not (level == "beginner" and x in NOT_FOR_BEGINNERS)][:3]
            iso = p in pa.ISOLATION
            slots.append({"key": f"{key}/{s}", "pattern": p, "exercise_id": id_, "sets": sets, "rep_range": reps,
                          "rir": rir, "rest_seconds": 60 if pair is not None else rest, "alternatives": alts,
                          "warmup": not iso and not warmed, "pair": pair, "main": role == "main" and level != "beginner",
                          "top_set": role == "main" and level == "advanced"})
            if not iso:
                warmed = True
        for sl in slots:  # a pair that lost a member runs as straight sets
            if sl["pair"] is not None and sum(1 for x in slots if x["pair"] == sl["pair"]) < 2:
                sl["pair"] = None
                sl["rest_seconds"] = prescription(sl["pattern"], sl["exercise_id"], "plain", level, week, older, goal, leak)[2]
        prog["routines"].append({"key": key, "title": d["title"], "exercises": slots})
    if priority:
        if layout == "ulf5i":
            _trim_priority_day(prog)
        prog = _apply_priority(prog, priority)
    return prog


def _trim_priority_day(prog):
    """The priority day's 4 + 3 sets on top of four upper/lower days can pass MRV (G2): its two exercises lose a set
    at a time (never under 2 each) until no group is over."""
    r = next((x for x in prog["routines"] if x["title"] == "Priority"), None)
    if r is None:
        return
    while not pa.audit(prog)[1]["passed"]:
        cand = [s for s in r["exercises"][:2] if s["sets"] > 2]
        if not cand:
            break
        max(cand, key=lambda s: s["sets"])["sets"] -= 1


def _no_worse(before, new, floors_only=False):
    old, now = pa.audit(before), pa.audit(new)
    for g in ([0] if floors_only else [0, 1]):
        for m, v in now[g]["misses"]:
            if not any(om == m and (v >= ov - 1e-9 if g == 0 else v <= ov + 1e-9) for om, ov in old[g]["misses"]):
                return False
    return True


def _apply_priority(prog, region):
    """Advanced, one region: +2 sets on two of its slots (each ≤ the set cap), −1 set on two non-priority isolation
    slots, its slot right after the day's main lift. Never costs a gate: a cut that puts a group under its floor is
    skipped, a day pushed over the minutes keeps its sets, an add that puts a group over MRV is undone. Our rule."""
    before = copy.deepcopy(prog)
    pats = REGIONS[region]
    flat = [s for r in prog["routines"] for s in r["exercises"]]
    adds = [s["key"] for s in sorted((s for s in flat if s["pattern"] in pats and s["pair"] is None),
                                     key=lambda s: s["sets"])[:2]]
    cap = set_cap(prog)
    for s in flat:
        if s["key"] in adds:
            s["sets"] = max(s["sets"], min(cap, s["sets"] + 2))
    idx = range(len(prog["routines"]))
    has_add = [i for i in idx if any(s["key"] in adds for s in prog["routines"][i]["exercises"])]
    order = has_add + [i for i in idx if i not in has_add]
    cut = 0
    for ri in order:
        for si in reversed(range(len(prog["routines"][ri]["exercises"]))):
            if cut >= 2:
                break
            s = prog["routines"][ri]["exercises"][si]
            if s["pattern"] not in pa.ISOLATION or s["pattern"] in pats or s["sets"] <= 1 or s["pair"] is not None:
                continue
            nxt = copy.deepcopy(prog)
            nxt["routines"][ri]["exercises"][si]["sets"] -= 1
            if _no_worse(before, nxt, floors_only=True):
                prog, cut = nxt, cut + 1
    for i in idx:
        if pa.routine_minutes(prog["routines"][i]["exercises"]) > prog["minutes"]:
            prog["routines"][i] = copy.deepcopy(before["routines"][i])
    if not _no_worse(before, prog):
        prog = before
    for r in prog["routines"]:
        ex = r["exercises"]
        if any(s["pair"] is not None for s in ex):
            continue
        i = next((k for k, s in enumerate(ex) if s["pattern"] in pats), None)
        if i is None:
            continue
        to = 1 if ex[0]["main"] and i > 0 else 0
        ex.insert(to, ex.pop(i))
    return prog


def program_name(prog):
    return pa.program_name(prog)


def is_easy_week(prog, sessions_done):
    """Whether the next session falls in an easy week, counted in sessions done (`days` sessions = a week)."""
    every = EASY_WEEK_EVERY[prog["level"]]
    return bool(every) and (sessions_done // prog["days"] + 1) % every == 0


# ---------------------------------------------------------------- the tree

def decide(a, week=1):
    """Answers → {"outcome": "needs_acknowledgement" | "under_age" | "needs_clearance" | "program", ...}."""
    if not a.get("acknowledged"):
        return {"outcome": "needs_acknowledgement", "message": DISCLAIMER}
    if a["age"] == "under_16":
        return {"outcome": "under_age", "message": UNDER_AGE}
    health = set(a.get("health", ()))
    serious = [h for h in HEALTH if h in health and h not in NOT_SERIOUS]
    cleared = a.get("clearance") in CLEARANCE_SENTENCES
    if serious and not cleared:
        return {"outcome": "needs_clearance", "items": serious, "message": CLEARANCE_NEEDED}
    fired, notes, warnings = [], [], []
    if serious:
        fired.append("row 2: cleared by a doctor")
    pl = place(a["history"], a.get("last_trained"), a.get("known_loads"))
    fired.append(f"§3.2 placement row {pl['row']}: {pl['level']}")
    older = a["age"] == "60_plus"
    layout, days, cap = pick(pl["level"], a["days"], older)
    fired.append(f"row 14: {layout}, {days} days")
    prog = build(layout, pl["level"], days, a, week)
    fired.append(f"row 15: {prog['variant']}-minute variant")
    if days == 2:
        notes.append(NOTES["minimum_dose"])
    if cap:
        notes.append(NOTES[cap[0]].format(*cap[1:]))
    if pl["level"] != "beginner" and prog["variant"] <= 45:
        notes.append(NOTES["short_sessions"])
    if pl["level"] == "advanced":
        notes.append(NOTES["advanced_scope"])
        fired.append(f"rows 29, 43: advanced ({'priority ' + a['priority'] if a.get('priority') else 'no priority'})")
    if pl["returning"]:
        notes.append(NOTES["returning"])
        fired.append("row 12: returning")
    if pl["advanced_check_week"] is not None:
        notes.append(NOTES["advanced_check"])
    if prog["goal"]:
        fired.append(f"row 28: goal {prog['goal']}")
    if older:
        notes.append(NOTES["older_tempo"])
        fired.append("row 44: 60+")
    if a["age"] == "16_17":
        warnings.append(WARNINGS["supervision"])
        fired.append("row 4: 16–17")
    injuries = a.get("injuries", [])
    if health or injuries:
        warnings.insert(0, DISCLAIMER)
    if health & STRONG_WARNING:
        warnings.append(WARNINGS["strong_medical"])
        fired.append("G120: strong warning")
    if "urine_leak" in health:
        warnings.append(WARNINGS["leak"])
        fired.append("row 3: leak path")
    if injuries:
        warnings += [WARNINGS["left_out_for_pain"], WARNINGS["stop_if_sharp"]]
        for i in injuries:
            active = i.get("red_flag") and not i.get("checked")
            if active:
                warnings.append(RED_FLAG.format(AREA_NAMES[i["area"]]))
            fired.append(f"rows 5–8: {i['area']}{' (red flag)' if active else ''}")
    prog["easy_week_every"] = EASY_WEEK_EVERY[pl["level"]]
    return {"outcome": "program", "program": prog, "placement": pl, "fired": fired, "notes": notes,
            "warnings": warnings, "days_asked": a["days"], "priority_asked": a.get("priority")}


# ---------------------------------------------------------------- profile.md / coaich.md

def _scalar(v):
    v = v.strip()
    if v.startswith(("[", "{")):
        return _flow(v)
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    low = v.lower()
    if low in ("true", "yes"):
        return True
    if low in ("false", "no"):
        return False
    if low in ("null", "~", ""):
        return None
    for t in (int, float):
        try:
            return t(v)
        except ValueError:
            pass
    return v


def _split_flow(s):
    parts, depth, cur, quote = [], 0, "", None
    for c in s:
        if quote:
            quote = None if c == quote else quote
        elif c in "\"'":
            quote = c
        elif c in "[{":
            depth += 1
        elif c in "]}":
            depth -= 1
        elif c == "," and depth == 0:
            parts.append(cur)
            cur = ""
            continue
        cur += c
    return [p for p in (parts + [cur]) if p.strip()]


def _flow(v):
    inner = v.strip()[1:-1]
    if v.strip().startswith("["):
        return [_scalar(x) for x in _split_flow(inner)]
    out = {}
    for x in _split_flow(inner):
        k, _, val = x.partition(":")
        out[k.strip()] = _scalar(val)
    return out


def _strip_comment(line):
    quote = None
    for i, c in enumerate(line):
        if quote:
            quote = None if c == quote else quote
        elif c in "\"'":
            quote = c
        elif c == "#" and (i == 0 or line[i - 1] == " "):
            return line[:i].rstrip()
    return line.rstrip()


def _block(rows, i, ind):
    if rows[i][1].startswith("-"):
        out = []
        while i < len(rows) and rows[i][0] == ind and rows[i][1].startswith("-"):
            item = rows[i][1][1:].strip()
            if not item:
                val, i = _block(rows, i + 1, rows[i + 1][0])
            elif re.match(r"^[\w-]+:(\s|$)", item):
                rows[i] = (ind + 2, item)
                val, i = _block(rows, i, ind + 2)
            else:
                val, i = _scalar(item), i + 1
            out.append(val)
        return out, i
    out = {}
    while i < len(rows) and rows[i][0] == ind and not rows[i][1].startswith("-"):
        k, _, v = rows[i][1].partition(":")
        i += 1
        if v.strip():
            out[k.strip()] = _scalar(v)
        elif i < len(rows) and (rows[i][0] > ind or rows[i][0] == ind and rows[i][1].startswith("-")):
            out[k.strip()], i = _block(rows, i, rows[i][0])
        else:
            out[k.strip()] = None
    return out, i


def front_matter(text):
    """The YAML header of a Markdown file (a small subset: maps, lists, flow [..] and {..}, scalars)."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    end = next((i for i, l in enumerate(lines[1:], 1) if l.strip() == "---"), None)
    if end is None:
        raise ValueError("the YAML header has no closing ---")
    rows = [(len(l) - len(l.lstrip(" ")), _strip_comment(l).strip()) for l in lines[1:end]]
    rows = [r for r in rows if r[1]]
    return _block(rows, 0, rows[0][0])[0] if rows else {}


# profile.md values (written by the onboard and safety skills) → the names used here.
PROFILE_AGE = {"under-16": "under_16", "16-17": "16_17", "18-59": "adult", "60+": "60_plus"}
PROFILE_HISTORY = {"never": "under_6_months", "6m-2y": "6_months_to_2_years", "over-2y": "over_2_years"}
PROFILE_LAST = {"last-3m": "last_3_months", "3-12m": "3_to_12_months", "over-1y": "over_a_year"}
PROFILE_HEALTH = {"pregnancy": "pregnancy_or_postpartum", "heart": "heart_or_circulation", "chest-pain": "chest_pain",
                  "fainting": "dizziness_or_fainting", "doctor-said-no": "doctor_said_no", "surgery": "recent_operation",
                  "other": "other_reason", "high-blood-pressure": "high_blood_pressure",
                  "osteoporosis": "osteoporosis_or_hernia", "hernia": "osteoporosis_or_hernia", "diabetes": "diabetes",
                  "joint": "bone_or_joint_problem", "leaking": "urine_leak"}
PROFILE_AREA = {"knee": "knee", "lower-back": "low_back", "low-back": "low_back", "low_back": "low_back",
                "shoulder": "shoulder", "elbow-wrist": "elbow_wrist", "elbow_wrist": "elbow_wrist", "hip": "hip",
                "other": "other", "somewhere-else": "other"}


def _pick(d, key, table, required=False):
    v = d.get(key)
    if v is None or v == "":
        if required:
            raise ValueError(f"profile.md needs '{key}' (one of: {', '.join(table)})")
        return None
    v = str(v)
    if v not in table:
        raise ValueError(f"'{key}: {v}' is not one of: {', '.join(table)}")
    return table[v]


def read_answers(folder):
    """coaich.md + profile.md → the answers decide() takes. Raises ValueError naming the bad key."""
    def header(name):
        path = os.path.join(folder, name)
        if not os.path.exists(path):
            return {}
        with open(path, encoding="utf-8") as f:
            return front_matter(f.read())
    settings, prof = header("coaich.md"), header("profile.md")
    if not prof:
        raise ValueError("profile.md is missing or has no YAML header: run /onboard first")
    health = {_pick({"h": h}, "h", PROFILE_HEALTH) for h in prof.get("health_items") or []}
    covers = {PROFILE_HEALTH.get(str(h), str(h)) for h in settings.get("safety_clearance_covers") or []}
    serious = {h for h in health if h not in NOT_SERIOUS}
    # A clearance counts with the exact sentence, and only for the stop items it covers (an empty list covers all).
    clearance = settings.get("safety_clearance_sentence")
    if covers and not serious <= covers:
        clearance = None
    injuries = []
    for p in prof.get("pain") or []:
        p = {"area": p} if isinstance(p, str) else p
        injuries.append({"area": _pick(p, "area", PROFILE_AREA, required=True), "red_flag": bool(p.get("red_flag")),
                         "checked": bool(p.get("checked"))})
    loads = prof.get("known_loads") or []
    lifts = {str(x.get("exercise")) for x in loads if isinstance(x, dict) and x.get("kg")}
    days, minutes = prof.get("days_per_week"), prof.get("minutes_per_session")
    if not isinstance(days, int) or not isinstance(minutes, int):
        raise ValueError("profile.md needs 'days_per_week' (2–6) and 'minutes_per_session' (30, 45, 60 or 75)")
    goal = prof.get("goal")
    if goal not in (None, *GOALS):
        raise ValueError(f"'goal: {goal}' is not one of: {', '.join(GOALS)}")
    priority = prof.get("priority")
    priority = None if priority in (None, "", "none") else _pick(
        prof, "priority", {k.replace("_", "-"): k for k in REGIONS})
    return {
        "acknowledged": bool(settings.get("safety_acknowledged")),
        "age": _pick(prof, "age_band", PROFILE_AGE) or "adult",
        "health": health, "clearance": clearance, "injuries": injuries,
        "history": _pick(prof, "history", PROFILE_HISTORY, required=True),
        "last_trained": _pick(prof, "last_trained", PROFILE_LAST),
        "known_loads": {"squat", "bench"} <= lifts,
        "days": days, "minutes": minutes,
        "chair_stand": prof.get("chair_stand"), "goal": goal, "priority": priority,
        "bench_safeties": bool(prof.get("bench_safeties")),
    }


# ---------------------------------------------------------------- outputs

def rebuild_week(prog):
    """The next week the prescription changes (beginner ramp ends at 5, the 60+ rules at 9), else None."""
    if prog["older"] and prog["week"] <= 8:
        return 9
    if prog["level"] == "beginner" and prog["week"] <= 4:
        return 5
    return None


# Default load step by tool (kg). Barbells go up by 5 kg from 60 kg on lower-body lifts and by 1.25 kg under 40 kg on
# upper-body lifts with fractional plates; machines learn their real step the first time (the engine's job).
LOAD_STEP_KG = {"barbell_lower": 2.5, "barbell_upper": 2.5, "dumbbell": 2, "machine": 5, "bodyweight": 0}


def tool(equipment, id_, lower_body):
    if ladder_of(id_):
        return "bodyweight"
    if id_ == "Weighted_Pull_Ups":
        return "dumbbell"
    if equipment in ("barbell", "e-z curl bar"):
        return "barbell_lower" if lower_body else "barbell_upper"
    return {"dumbbell": "dumbbell", "kettlebells": "dumbbell", "machine": "machine", "cable": "machine"}.get(equipment,
                                                                                                         "bodyweight")


def program_json(result, today):
    prog = copy.deepcopy({k: v for k, v in result["program"].items() if k != "swaps"})
    for n, r in enumerate(prog["routines"], 1):
        r["order"], r["minutes"] = n, pa.routine_minutes(r["exercises"])
        for s in r["exercises"]:
            ex = pa.CATALOGUE[s["exercise_id"]]
            s["tool"] = tool(ex.get("equipment"), s["exercise_id"], s["pattern"] in pa.LOWER_BODY)
            s["category"] = "spine" if s["exercise_id"] in pa.SPINE else "isolation" if s["pattern"] in pa.ISOLATION \
                else "compound"
            s.update(name=ex["name"], equipment=ex.get("equipment"), load_step_kg=LOAD_STEP_KG[s["tool"]],
                     reps_left=s.pop("rir"))
    every = EASY_WEEK_EVERY[prog["level"]]
    prog["easy_weeks"] = list(range(every, 53, every)) if every else []
    return {"schema": "coaich.program/0.1", "start": today, "name": program_name(prog), **prog,
            "rebuild_at_week": rebuild_week(prog), "placement": result["placement"], "notes": result["notes"],
            "warnings": result["warnings"], "rules_fired": result["fired"], "swaps": result["program"]["swaps"]}


def _rir(r):
    return str(r[0]) if r[0] == r[1] else f"{r[0]}–{r[1]}"


def _name(i):
    return pa.CATALOGUE[i]["name"]


def explain(result):
    """One reason per choice, in plain words."""
    prog, pl = result["program"], result["placement"]
    out = [placement_line(pl),
           f"{LAYOUT_NAMES[prog['layout']]}: you asked for {result['days_asked']} days"
           + (f", run as {prog['days']} (see the notes)" if result["days_asked"] != prog["days"] else "")
           + "; every muscle group is trained in at least 2 sessions a week (strength, and shorter sessions).",
           f"The {prog['variant']}-minute version: every session fits in your {prog['minutes']} minutes "
           f"(longest ≈ {max(pa.routine_minutes(r['exercises']) for r in prog['routines']):g} min: 8 min warm-up, "
           "about 3¼ min per compound set, 2 min per isolation or paired set)."]
    if prog["level"] == "beginner":
        out.append("Beginner: 2 sets per exercise in weeks 1–4, then 3; 2–3 reps left in the tank at first, then 1–2. "
                   "No planned easy week: one comes only when you stall or report joint pain.")
    else:
        bracket = "4–6" if prog["goal"] == "strength" else "6–10"
        out.append(f"Goal {prog['goal']}: the main lift of each day runs {bracket} reps; other compounds 8–12, "
                   f"isolations 10–20. An easy week every {EASY_WEEK_EVERY[prog['level']]}th week (fewer sets, lighter, "
                   "never a week off).")
    if prog["level"] == "advanced":
        out.append("Advanced: each day's main lift starts with one top set, then lighter back-off sets.")
    if result["priority_asked"] and not prog["priority"]:
        out.append(f"Priority {result['priority_asked'].replace('_', ' ')}: used from Advanced; until then every area "
                   "gets the same care.")
    if prog["priority"]:
        out.append(f"Priority {prog['priority'].replace('_', ' ')}: more sets on its exercises and it comes right "
                   "after the main lift, without breaking a gate or the time.")
    out.append("Spine-loading lifts (squats, deadlifts, standing presses, barbell rows) always stop 2 or more reps "
               "short of failure.")
    for s in prog["swaps"]:
        out.append(f"{s['routine']}: {_name(s['from'])} → {_name(s['to'])} ({s['why']}).")
    if prog["left_out"]:
        out.append("Left out for pain: " + ", ".join(sorted(set(prog["left_out"]))) + " slots.")
    return out


def current_block(result, today, checks, unexpected):
    prog = result["program"]
    name = program_name(prog)
    lines = ["<!-- coaich:program -->", f"## Program — {LAYOUT_NAMES[prog['layout']]} × {prog['minutes']} min ({name})", "",
             f"In force from {today} · week {prog['week']} · level {prog['level']}"
             + (f" · goal {prog['goal']}" if prog["goal"] else "") + " · file `plan/program.json`."]
    rw = rebuild_week(prog)
    if rw:
        lines.append(f"Rebuild at week {rw} (`program_build.py --week {rw}`): the sets or effort change then.")
    lines += ["", "### Why this program", ""] + [f"- {x}" for x in explain(result)]
    if result["warnings"]:
        lines += ["", "### Health", ""] + [f"- {w}" for w in result["warnings"]]
    if result["notes"]:
        lines += ["", "### Notes", ""] + [f"- {n}" for n in result["notes"]]
    lines += ["", "### Sessions (run in order, not by weekday)"]
    for r in prog["routines"]:
        lines += ["", f"#### {r['title']} (≈ {pa.routine_minutes(r['exercises']):g} min)", "",
                  "| # | Exercise | Sets × reps | Reps in reserve | Rest | Alternatives |", "|---|---|---|---|---|---|"]
        for n, s in enumerate(r["exercises"], 1):
            tag = " (top set first)" if s["top_set"] else " (warm-up ramp)" if s["warmup"] else ""
            pair = f" · pair {s['pair']}" if s["pair"] is not None else ""
            lines.append(f"| {n} | {_name(s['exercise_id'])}{tag}{pair} | {s['sets']} × {s['rep_range'][0]}–"
                         f"{s['rep_range'][1]} | {_rir(s['rir'])} | {s['rest_seconds']} s | "
                         + (", ".join(_name(x) for x in s["alternatives"]) or "—") + " |")
    every = EASY_WEEK_EVERY[prog["level"]]
    lines += ["", "### Easy weeks", "",
              (f"Every {every}th week, counted in sessions done ({prog['days']} sessions = a week): weeks "
               + ", ".join(str(w) for w in range(every, 4 * every + 1, every))
               + " … A third fewer sets, about 10 % lighter, 3–4 reps in reserve; nothing is graded.") if every
              else "None planned. One is triggered by 3+ exercises reduced within 14 days or joint pain on 2 sessions."]
    fails = [c for c in checks if not c["passed"] and not c["warn_only"]]
    lines += ["", "### Audit", "",
              f"Gates G1–G9: {'all pass' if not fails else 'pass, except the known misses below' if not unexpected else 'FAILED'}."]
    for c in fails:
        for m, v in c["misses"]:
            lines.append(f"- G{c['gate']} {m} {pa.fmt(v)}: {pa.known_reason(prog, c['gate'], (m, v))}")
    lines.append("<!-- /coaich:program -->")
    return "\n".join(lines) + "\n"


def write_current(folder, block):
    path = os.path.join(folder, "plan", "CURRENT.md")
    old = "# In force today\n\n"
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            old = f.read()
    m = re.search(r"<!-- coaich:program -->.*?<!-- /coaich:program -->\n?", old, re.S)
    new = old[:m.start()] + block + old[m.end():] if m else old.rstrip("\n") + "\n\n" + block
    with open(path, "w", encoding="utf-8") as f:
        f.write(new)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dir", required=True, help="athlete folder (holds coaich.md and profile.md)")
    ap.add_argument("--week", type=int, default=1, help="training week, counted in sessions done (default 1)")
    ap.add_argument("--today", default=datetime.date.today().isoformat(), help="date stamp (YYYY-MM-DD)")
    ap.add_argument("--dry-run", action="store_true", help="print program.json, write nothing")
    a = ap.parse_args(argv)
    try:
        answers = read_answers(a.dir)
    except ValueError as e:
        print(f"stop: {e}", file=sys.stderr)
        return 2
    result = decide(answers, a.week)
    if result["outcome"] != "program":
        print(f"stop ({result['outcome']}): {result['message']}" +
              (f" Items: {', '.join(result['items'])}." if result.get("items") else ""), file=sys.stderr)
        return 2
    prog = result["program"]
    checks = pa.audit(prog)
    unexpected = pa.unexpected_failures(prog, checks)
    doc = program_json(result, a.today)
    if a.dry_run:
        print(json.dumps(doc, ensure_ascii=False, indent=1))
        return 1 if unexpected else 0
    if unexpected:
        print("refused: the program fails the audit: " + "; ".join(unexpected), file=sys.stderr)
        return 1
    os.makedirs(os.path.join(a.dir, "plan"), exist_ok=True)
    with open(os.path.join(a.dir, "plan", "program.json"), "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=1)
        f.write("\n")
    write_current(a.dir, current_block(result, a.today, checks, unexpected))
    log = os.path.join(a.dir, "log.md")
    if not os.path.exists(log):
        with open(log, "w", encoding="utf-8") as f:
            f.write("# Log\n\nOne line per skill run.\n\n")
    with open(log, "a", encoding="utf-8") as f:
        f.write(f"- {a.today} · program-build · {doc['name']} ({prog['level']}, {prog['days']} days × "
                f"{prog['minutes']} min, week {prog['week']}), audit passed\n")
    print(f"wrote plan/program.json and plan/CURRENT.md: {doc['name']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
