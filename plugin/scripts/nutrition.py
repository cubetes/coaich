#!/usr/bin/env python3
"""Nutrition targets, a simple meal plan and the food table, with the CoAIch safeguards enforced in code.

Usage:
  nutrition.py plan  --dir D [--phase maintain|gain|lose] [--rate PCT] [--intake KCAL] [--meals 3|4|5]
                     [--prefer ID,..] [--exclude ID,..] [--today YYYY-MM-DD] [--dry-run] [--json]
  nutrition.py trend --dir D [--intake KCAL] [--today YYYY-MM-DD] [--json | --line]
  nutrition.py foods [TEXT] [--diet omnivore|pescatarian|vegetarian|vegan] [--avoid TAG,..] [--group G]

`plan` reads coaich.md, profile.md (the nutrition answers onboard writes) and, with the user's consent,
data/body.csv; works out maintenance (from the weight trend when it is good enough, else Mifflin-St Jeor x an
activity factor), the phase target, protein, fat and carbs, and a one-day meal plan from data/foods.csv; then
writes plan/nutrition.md, the nutrition block of plan/CURRENT.md and a log line. `trend` only reports the weight
trend (`--line`: the weekly review's one line against the phase's band). `foods` looks foods up. Every rule and its source: references/nutrition.md. Every number a skill shows
comes from here: skills never do nutrition arithmetic.

Exit 0 = done, 2 = a missing or bad answer (named on stderr), 3 = a safeguard said no (its wording on stdout).
When a safeguard switches nutrition off (age, eating-disorder answer, pregnancy), plan/nutrition.md is rewritten
to say so, so old targets never stay in force. Python 3.9+ stdlib only.
"""
import argparse
import csv
import datetime
import json
import math
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import athlete_folder as af  # noqa: E402
from program_build import front_matter, write_current  # noqa: E402

FOODS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "foods.csv")
KCAL_PER_KG = 7700.0  # energy in 1 kg of body-weight change (Wishnofsky rule; Hall 2008 says lower when lean)
ACTIVITY = {"sedentary": 1.2, "light": 1.375, "moderate": 1.55, "very": 1.725, "extra": 1.9}
PHASES = ("maintain", "gain", "lose")
SEXES = ("male", "female", "unspecified")
DIETS = {"omnivore": set(), "pescatarian": {"meat", "poultry"},
         "vegetarian": {"meat", "poultry", "fish", "shellfish"},
         "vegan": {"meat", "poultry", "fish", "shellfish", "egg", "milk"}}
ALLERGY_TAGS = {"milk", "egg", "fish", "shellfish", "peanut", "tree-nut", "soy", "gluten", "sesame"}

# Our rules (references/nutrition.md has the evidence behind each number).
LOSS_DEFAULT_PCT, GAIN_DEFAULT_PCT, GAIN_CAP_PCT = 0.5, 0.25, 0.5
# Body-fat bands -> weekly loss cap (% of body weight). Upper bounds of "lean" and "moderate" by sex.
BF_BANDS = {"male": (15.0, 25.0), "female": (23.0, 33.0)}
LOSS_CAP = {"lean": 0.7, "moderate": 1.0, "higher": 1.5}
MIN_BMI_LOSE = 18.5
TREND_MIN_DAYS, TREND_MIN_WEIGHINS, TREND_MAX_SE_KCAL = 14, 8, 200.0
PLAN_KCAL_TOL, PLAN_PROTEIN_MIN = 0.05, 0.95

LAWYER = "*Draft wording: lawyer review pending. This is general wellness information, not medical advice.*"
WORDING = {
    "experimental-off": (
        "Nutrition is experimental and switched off: its safety texts haven't had a legal review yet. To switch it "
        "on, set `experimental: on` in coaich.md (or ask me to). Your training plan is not affected."),
    "age": "Nutrition targets are for ages 18 and over. Your training plan is not affected.",
    "eating-disorder": (
        "Thanks for telling me. Because of this, CoAIch won't set calorie targets or plan a fat-loss phase. "
        "A doctor or a registered dietitian who works with eating disorders can help you set up eating that "
        "supports your training. If you are struggling right now, contact your doctor or a local eating-disorder "
        "helpline. Your training plan is not affected."),
    "wellbeing-pause": (
        "From what you've told me, I've paused calorie targets, fat-loss phases and photo reviews. That isn't a "
        "judgement: food and body worries are worth talking through with someone qualified, like your doctor or a "
        "registered dietitian. If you are struggling right now, contact your doctor or a local helpline. Your "
        "training plan is not affected. When you want the pause lifted, tell me so in your own words."),
    "pregnancy": (
        "You told me you're pregnant or gave birth less than 3 months ago. CoAIch won't set calorie targets now: "
        "your doctor or midwife is the right person for what and how much to eat. Your training plan follows the "
        "medical check."),
    "bmi": (
        "Your body mass index is below 18.5, so CoAIch won't plan a fat-loss phase. We can plan to maintain or "
        "to gain instead. If you are worried about your weight, talk to a doctor."),
    "consent": "Weight tracking is off (your choice in profile.md), so there is no weight trend to read.",
}


class Missing(ValueError):
    """A missing or bad answer. Exit 2."""


class Safeguard(Exception):
    """A safeguard said no. `off` = nutrition is switched off (nutrition.md is rewritten). Exit 3."""

    def __init__(self, code, off):
        super().__init__(WORDING[code])
        self.code, self.off = code, off


# ---------------------------------------------------------------- reading the folder

def header(folder, name):
    path = os.path.join(folder, name)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return front_matter(f.read())


def yes(v):
    return v is True or str(v).strip().lower() in ("yes", "true", "y")


def answered(v):
    return v is not None and v != "" and v != []


def as_list(v):
    if not answered(v):
        return []
    return [str(x).strip().lower() for x in (v if isinstance(v, list) else str(v).split(",")) if str(x).strip()]


def parse_height(v):
    """cm from `178`, `178 cm`, `5 ft 10 in`, `5'10"` or `70 in`."""
    s = str(v).strip().lower()
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:ft|')\s*(\d+(?:\.\d+)?)?\s*(?:in|\"|'')?", s)
    if m:
        return (float(m.group(1)) * 12 + float(m.group(2) or 0)) * 2.54
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(cm|in|\")?", s)
    if not m:
        raise Missing(f"'height: {v}' is not a height (e.g. 178 cm or 5 ft 10 in)")
    return float(m.group(1)) * (2.54 if m.group(2) in ("in", '"') else 1)


def parse_weight(v):
    """kg from `80`, `80 kg` or `176 lb`."""
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(kg|lb|lbs)?", str(v).strip().lower())
    if not m:
        raise Missing(f"'weight: {v}' is not a weight (e.g. 80 kg or 176 lb)")
    return float(m.group(1)) * (0.45359237 if m.group(2) in ("lb", "lbs") else 1)


def weigh_ins(folder, today):
    """[(date, kg, body_fat_pct or None)] from data/body.csv up to today, oldest first: one weight per date and the
    body fat of that date, each from the preferred source (athlete_folder.body_series: by hand, scale, Apple Health,
    then a photo range), plus the dates that have only a body-fat value (kg None)."""
    fat = dict(af.body_series(folder, "body_fat_pct"))
    kg = dict(af.body_series(folder, "weight_kg"))
    out = [(datetime.date.fromisoformat(d), kg.get(d), fat.get(d)) for d in sorted(set(kg) | set(fat))]
    return [p for p in out if p[0] <= today]


def previous_plan(folder):
    return header(folder, "plan/nutrition.md")


# ---------------------------------------------------------------- the maths (pure)

def mifflin(weight, height_cm, age, sex):
    """Resting energy (kcal/day), Mifflin-St Jeor 1990. `unspecified`: the midpoint of the two constants."""
    return 10 * weight + 6.25 * height_cm - 5 * age + {"male": 5, "female": -161, "unspecified": -78}[sex]


def bmi(weight, height_cm):
    return weight / (height_cm / 100) ** 2


def bf_band(bf, sex):
    """lean | moderate | higher, or None when body fat is unknown. `unspecified` uses the stricter female bands."""
    if bf is None:
        return None
    lean, moderate = BF_BANDS["male" if sex == "male" else "female"]
    return "lean" if bf < lean else "moderate" if bf < moderate else "higher"


def loss_cap(bf, sex):
    """Weekly loss cap (% of body weight) and its band. Unknown body fat gets the lean cap."""
    band = bf_band(bf, sex)
    return LOSS_CAP[band or "lean"], band or "unknown"


def linreg(xs, ys):
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx == 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    res = sum((y - (my + slope * (x - mx))) ** 2 for x, y in zip(xs, ys))
    se = math.sqrt(res / (n - 2) / sxx) if n > 2 else 0.0
    return slope, se


def trend(points, since, until, intake=None):
    """Weight trend over [since, until] by least squares. With `intake` (kcal/day eaten on average), also
    maintenance = intake - slope x 7700. `usable` = long and tight enough to replace the formula (our rule)."""
    pts = [(d, w) for d, w, _ in points if since <= d <= until and w is not None]
    out = {"since": since.isoformat(), "until": until.isoformat(), "weigh_ins": len(pts), "usable": False}
    if len(pts) < 2:
        out["why"] = "fewer than 2 weigh-ins in the window"
        return out
    span = (pts[-1][0] - pts[0][0]).days
    fit = linreg([(d - pts[0][0]).days for d, _ in pts], [w for _, w in pts])
    if fit is None:
        out["why"] = "all weigh-ins on one day"
        return out
    slope, se = fit
    mean_w = sum(w for _, w in pts) / len(pts)
    out.update(days=span, kg_per_week=slope * 7, pct_per_week=slope * 7 / mean_w * 100,
               se_kcal=se * KCAL_PER_KG)
    if intake is not None:
        out["intake_kcal"] = intake
        out["maintenance_kcal"] = intake - slope * KCAL_PER_KG
    if span < TREND_MIN_DAYS or len(pts) < TREND_MIN_WEIGHINS:
        out["why"] = f"needs {TREND_MIN_DAYS}+ days and {TREND_MIN_WEIGHINS}+ weigh-ins (has {span} days, {len(pts)})"
    elif out["se_kcal"] > TREND_MAX_SE_KCAL:
        out["why"] = f"too noisy (±{out['se_kcal']:.0f} kcal; needs ±{TREND_MAX_SE_KCAL:.0f} or less)"
    elif intake is None:
        out["why"] = "no intake to compare with (no plan in force and no --intake)"
    else:
        out["usable"] = True
    return out


def round10(x):
    return int(math.floor(x / 10 + 0.5) * 10)


def targets(weight, height_cm, age, sex, activity, phase, bf=None, rate=None, maintenance=None):
    """Daily kcal, protein, fat and carbs with every step and every safeguard applied. Raises Safeguard('bmi')."""
    steps, notes = [], []
    b = bmi(weight, height_cm)
    if phase == "lose" and b < MIN_BMI_LOSE:
        raise Safeguard("bmi", off=False)
    rest = mifflin(weight, height_cm, age, sex)
    steps.append(("Resting energy (Mifflin-St Jeor)", f"10×{weight:.1f} + 6.25×{height_cm:.0f} − 5×{age} "
                  f"{ {'male': '+ 5', 'female': '− 161', 'unspecified': '− 78'}[sex] }", rest))
    if maintenance is None:
        maintenance = rest * ACTIVITY[activity]
        steps.append(("Maintenance (estimate)", f"resting × {ACTIVITY[activity]} ({activity})", maintenance))
        source = "formula"
    else:
        steps.append(("Maintenance (your weight trend)", "average intake − weight change × 7700", maintenance))
        source = "weight-trend"
    cap, band = loss_cap(bf, sex)
    if phase == "lose":
        asked = LOSS_DEFAULT_PCT if rate is None else rate
        rate_pct = min(asked, cap)
        if asked > cap:
            notes.append(f"You asked for {asked:g} % a week; the cap " + (
                "while your body fat is unknown" if band == "unknown" else f"for your body fat ({band})")
                + f" is {cap:g} %, so we use {cap:g} %.")
    elif phase == "gain":
        asked = GAIN_DEFAULT_PCT if rate is None else rate
        rate_pct = min(asked, GAIN_CAP_PCT)
        if asked > GAIN_CAP_PCT:
            notes.append(f"You asked for {asked:g} % a week; we gain at most {GAIN_CAP_PCT:g} %, so we use it.")
    else:
        rate_pct = 0.0
    sign = {"lose": -1, "gain": 1, "maintain": 0}[phase]
    delta = sign * rate_pct / 100 * weight * KCAL_PER_KG / 7
    steps.append((f"Phase {phase}", f"{sign * rate_pct:+g} % of {weight:.1f} kg a week × 7700 / 7", delta))
    # Rounded up when losing, so rounding never makes the loss faster than the rate.
    kcal = int(math.ceil((maintenance + delta) / 10) * 10) if phase == "lose" else round10(maintenance + delta)
    how = "maintenance + phase, to 10 kcal"
    if kcal < rest:
        kcal, how = int(math.ceil(rest / 10) * 10), "raised to your resting needs (the floor)"
        rate_pct = max(0.0, (maintenance - kcal) * 7 / KCAL_PER_KG / weight * 100) if phase == "lose" else rate_pct
        notes.append(f"Calories never go below your estimated resting needs ({rest:.0f} kcal), so the target is "
                     f"{kcal} kcal (about {rate_pct:.2f} % a week).")
    steps.append(("Calories", how, kcal))
    if phase == "lose" and bf is not None:
        ffm = weight * (1 - bf / 100)
        protein = 2.3 * ffm
        steps.append(("Protein", f"2.3 g × {ffm:.1f} kg lean mass ({bf:g} % body fat)", protein))
    else:
        per_kg = 2.0 if phase == "lose" else 1.8
        basis = min(weight, 30 * (height_cm / 100) ** 2)
        protein = per_kg * basis
        how = f"{per_kg} g × {basis:.1f} kg" + (" (weight at BMI 30)" if basis < weight else "")
        steps.append(("Protein", how, protein))
    fat = max(0.25 * kcal / 9, 0.5 * weight)
    steps.append(("Fat", f"25 % of calories, at least 0.5 g × {weight:.1f} kg", fat))
    carbs = (kcal - 4 * protein - 9 * fat) / 4
    steps.append(("Carbs", "the calories left ÷ 4", carbs))
    if carbs < 0:
        raise Missing("protein and fat already exceed the calories: check weight, height and activity")
    return {"phase": phase, "rate_pct_week": round(rate_pct, 2), "kcal": kcal, "protein_g": round(protein),
            "fat_g": round(fat), "carbs_g": round(carbs), "resting_kcal": round(rest),
            "maintenance_kcal": round(maintenance), "maintenance_source": source, "bmi": round(b, 1),
            "loss_cap_pct_week": cap, "body_fat_band": band,
            "steps": [{"step": s, "how": h, "value": round(v)} for s, h, v in steps], "notes": notes}


def phase_band(phase, rate, cap):
    """The weekly change (% of body weight, signed) that counts as on track for the plan in force (our rule): lose
    = from half the planned rate to the loss cap; gain = from half the planned rate to the gain cap; maintain =
    within ±0.25 %."""
    if phase == "lose":
        return -cap, -rate / 2
    if phase == "gain":
        return rate / 2, GAIN_CAP_PCT
    return -0.25, 0.25


def weekly_line(tr, prev):
    """One line for the weekly review: the 4-week weight trend against the band of the plan in force. It never
    says "eat less": a slower loss is only reported, and the nutrition skill corrects calories at a check-in."""
    if tr.get("kg_per_week") is None or tr["days"] < TREND_MIN_DAYS or tr["weigh_ins"] < TREND_MIN_WEIGHINS:
        return (f"Weight trend: not enough weigh-ins yet ({tr['weigh_ins']} over {tr.get('days', 0)} days; needs "
                f"{TREND_MIN_WEIGHINS} over {TREND_MIN_DAYS}+ days).")
    phase, rate = str(prev["phase"]), float(prev.get("rate_pct_week") or 0)
    # Compared as shown, to 0.01 %, so the verdict never contradicts the printed numbers.
    lo, hi = (round(x, 2) for x in phase_band(phase, rate, float(prev.get("loss_cap_pct_week") or LOSS_CAP["lean"])))
    pct = round(tr["pct_per_week"], 2)
    if lo <= pct <= hi:
        verdict = "on track"
    elif pct < lo:
        verdict = "losing faster than the safe cap: eat more" if phase == "lose" else "eat more"
    else:
        verdict = {"lose": "slower than planned", "gain": "faster than planned"}.get(phase, "drifting up")
    return (f"Weight trend, 4 weeks to {tr['until']}: {tr['kg_per_week']:+.2f} kg a week ({pct:+.2f} %), "
            f"{tr['weigh_ins']} weigh-ins; {phase} band {lo:+.2f} to {hi:+.2f} % → {verdict}.")


def trend_line(folder, today):
    """weekly_line for the plan in force over the 4 weeks up to today, or None when no plan is on. The caller has
    passed the gate and the weight-tracking consent."""
    prev = previous_plan(folder)
    if prev.get("status") != "on":
        return None
    return weekly_line(trend(weigh_ins(folder, today), today - datetime.timedelta(days=28), today), prev)


# ---------------------------------------------------------------- foods and the meal plan

def load_foods(path=FOODS):
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        for k in ("kcal_100", "protein_100", "carbs_100", "fat_100", "fibre_100"):
            r[k] = float(r[k])
        r["piece_g"] = float(r["piece_g"]) if r["piece_g"] else None
        r["tags"] = set(filter(None, r["contains"].split(";")))
    return {r["id"]: r for r in rows}


def allowed(foods, diet="omnivore", avoid=()):
    """Food ids left after the diet and the avoid list (allergy tags, food ids, or words in the name)."""
    if diet not in DIETS:
        raise Missing(f"'diet: {diet}' is not one of: {', '.join(DIETS)}")
    bad = DIETS[diet] | {a for a in avoid if a in ALLERGY_TAGS}
    words = [a for a in avoid if a not in ALLERGY_TAGS]
    return {i for i, f in foods.items()
            if not f["tags"] & bad and i not in words and not any(w in f["name"].lower() for w in words)}


BREAKFAST = {"protein": ["greek_yogurt", "egg", "cottage_cheese", "egg_white", "tofu", "tempeh", "edamame"],
             "starch": ["oats", "bread_wholewheat", "quinoa", "potato"],
             "fruit": ["banana", "blueberries", "apple", "orange"],
             "fat": ["almonds", "peanut_butter", "walnuts", "chia", "avocado", "olive_oil"]}
MAIN = {"protein": ["chicken_breast", "salmon", "beef_mince_90", "turkey_breast", "tuna_canned", "pork_loin", "cod",
                    "shrimp", "tofu", "tempeh", "lentils", "chickpeas", "black_beans", "egg"],
        "starch": ["rice_white", "potato", "pasta", "rice_brown", "sweet_potato", "quinoa"],
        "veg": ["broccoli", "green_beans", "carrot", "red_pepper", "spinach", "tomato"],
        "fat": ["olive_oil", "avocado"]}
SNACK = {"protein": ["cottage_cheese", "greek_yogurt", "edamame", "whey", "tofu", "chickpeas", "egg"],
         "fruit": ["apple", "orange", "banana", "blueberries"],
         "fat": ["walnuts", "almonds", "peanut_butter", "chia"]}
LAYOUTS = {3: [("Breakfast", 0.30, BREAKFAST), ("Lunch", 0.35, MAIN), ("Dinner", 0.35, MAIN)],
           4: [("Breakfast", 0.25, BREAKFAST), ("Lunch", 0.30, MAIN), ("Snack", 0.15, SNACK),
               ("Dinner", 0.30, MAIN)],
           5: [("Breakfast", 0.20, BREAKFAST), ("Snack 1", 0.15, SNACK), ("Lunch", 0.25, MAIN),
               ("Snack 2", 0.15, SNACK), ("Dinner", 0.25, MAIN)]}
FIXED_G = {"veg": 150.0, "fruit": 125.0}  # a portion of vegetables; fruit is one piece, or 125 g when weighed


def macros(food, grams):
    k = grams / 100
    return {"kcal": food["kcal_100"] * k, "protein": food["protein_100"] * k, "carbs": food["carbs_100"] * k,
            "fat": food["fat_100"] * k}


def portion(food, grams):
    """Round to 5 g, or to whole pieces for foods eaten by the piece (at least one)."""
    if food["piece_g"]:
        return max(1, round(grams / food["piece_g"])) * food["piece_g"] if grams > 0 else 0.0
    return 5 * round(grams / 5)


def solve_meal(chosen, foods, target):
    """Grams for a meal's protein, fat and starch foods so it meets `target` protein, fat and calories, around the
    fixed vegetable/fruit portion. Each food is sized on its own number in turn until the portions settle. The
    starch closes the calories (food energy as USDA states it), so carbs land near, not exactly on, their target."""
    grams = {slot: (foods[i]["piece_g"] or FIXED_G[slot]) if slot in FIXED_G else 0.0 for slot, i in chosen.items()}
    main = {"protein": "protein", "fat": "fat", "starch": "kcal"}
    for _ in range(30):
        for slot, macro in main.items():
            if slot not in chosen:
                continue
            f = foods[chosen[slot]]
            others = sum(macros(foods[chosen[s]], g)[macro] for s, g in grams.items() if s != slot)
            density = f[f"{macro}_100"] / 100
            grams[slot] = max(0.0, (target[macro] - others) / density) if density else 0.0
    return {slot: portion(foods[chosen[slot]], g) for slot, g in grams.items()}


def meal_plan(t, foods, ok, n_meals=4, prefer=()):
    """One day of meals for targets `t`, from the allowed food ids `ok`. Foods are picked in a fixed order
    (`prefer` first), each used once a day while there is a choice; the last meal takes what is left of the day."""
    day = {"kcal": t["kcal"], "protein": t["protein_g"], "fat": t["fat_g"]}
    used, meals, got = set(), [], {"kcal": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0}
    layout = LAYOUTS[n_meals]
    for n, (name, share, slots) in enumerate(layout):
        chosen = {}
        for slot, order in slots.items():
            cands = [i for i in list(prefer) + order if i in ok and i in order]
            if not cands:
                continue
            fresh = [i for i in cands if i not in used]
            chosen[slot] = (fresh or cands)[0]
            used.add(chosen[slot])
        last = n == len(layout) - 1
        target = {m: max(0.0, day[m] - got[m]) if last else day[m] * share for m in day}
        grams = solve_meal(chosen, foods, target)
        items = [{"food": chosen[s], "name": foods[chosen[s]]["name"], "grams": g, **macros(foods[chosen[s]], g)}
                 for s, g in grams.items() if g > 0]
        for it in items:
            for m in got:
                got[m] += it[m]
        meals.append({"meal": name, "items": items})
    gap = {"kcal_pct": (got["kcal"] - t["kcal"]) / t["kcal"] * 100,
           "protein_pct": (got["protein"] - t["protein_g"]) / t["protein_g"] * 100}
    on_target = abs(gap["kcal_pct"]) <= PLAN_KCAL_TOL * 100 and got["protein"] >= PLAN_PROTEIN_MIN * t["protein_g"]
    return {"meals": meals, "total": got, "gap": gap, "on_target": on_target}


# ---------------------------------------------------------------- the gate and the plan

def gate(settings, prof):
    """Safeguards that switch nutrition off (the shared gate, athlete_folder.gate), in its order. Raises Missing
    or Safeguard(off=True)."""
    if not settings.get("safety_acknowledged"):
        raise Missing("the safety intake has not been done: run the safety skill (or /onboard) first")
    for reason in af.gate(prof, "nutrition", settings.get("experimental")):
        if reason == "eating-disorder-unanswered":
            raise Missing("profile.md needs 'eating_disorder_history' (no | yes | prefer-not-to-say)")
        if reason != "age-unanswered":  # an unanswered age is asked below (age_years)
            raise Safeguard("eating-disorder" if reason == "eating-disorder-history" else reason, off=True)


def inputs(folder, today):
    settings, prof = header(folder, "coaich.md"), header(folder, "profile.md")
    if not prof:
        raise Missing("profile.md is missing or has no YAML header: run /onboard first")
    gate(settings, prof)
    for key, allowed_values in (("sex", SEXES), ("activity", ACTIVITY), ("nutrition_phase", PHASES)):
        if str(prof.get(key)) not in allowed_values:
            raise Missing(f"profile.md needs '{key}' (one of: {', '.join(allowed_values)})")
    age = prof.get("age_years")
    if not isinstance(age, int) or not 18 <= age <= 110:
        raise Missing("profile.md needs 'age_years' (a whole number, 18 or over)")
    if not answered(prof.get("height")):
        raise Missing("profile.md needs 'height' (e.g. 178 cm or 5 ft 10 in)")
    consent = yes(prof.get("weight_tracking"))
    points = weigh_ins(folder, today) if consent else []
    return settings, prof, consent, points


def current_weight(prof, points):
    """(kg, how): the mean of the weigh-ins in the 7 days up to the latest one, else profile `weight`."""
    points = [p for p in points if p[1] is not None]
    if points:
        last = points[-1][0]
        week = [w for d, w, _ in points if (last - d).days < 7]
        return sum(week) / len(week), f"mean of {len(week)} weigh-ins up to {last.isoformat()}"
    if not answered(prof.get("weight")):
        raise Missing("profile.md needs 'weight' (e.g. 80 kg), or weigh-ins in data/body.csv")
    return parse_weight(prof["weight"]), "profile.md"


def body_fat(prof, points):
    for _, _, bf in reversed(points):
        if bf is not None:
            return bf
    v = prof.get("body_fat_pct")
    if isinstance(v, (int, float)):
        return float(v)
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*(?:-|–|to)\s*(\d+(?:\.\d+)?)\s*%?\s*", str(v or ""))
    return (float(m.group(1)) + float(m.group(2))) / 2 if m else None  # a range counts as its midpoint


def trend_for(folder, points, today, intake=None):
    prev = previous_plan(folder)
    since = today - datetime.timedelta(days=28)
    if intake is None and prev.get("status") == "on" and prev.get("kcal"):
        intake = float(prev["kcal"])
        since = max(since, datetime.date.fromisoformat(str(prev["since"])))
    return trend(points, since, today, intake)


def run_plan(folder, today, phase=None, rate=None, intake=None, n_meals=4, prefer=(), exclude=()):
    settings, prof, consent, points = inputs(folder, today)
    phase = phase or prof["nutrition_phase"]
    if phase not in PHASES:
        raise Missing(f"phase '{phase}' is not one of: {', '.join(PHASES)}")
    if rate is None and isinstance(prof.get("rate_pct_week"), (int, float)):
        rate = float(prof["rate_pct_week"])
    weight, weight_how = current_weight(prof, points)
    bf = body_fat(prof, points)
    tr = trend_for(folder, points, today, intake) if consent else None
    t = targets(weight, parse_height(prof["height"]), prof["age_years"], prof["sex"], prof["activity"], phase,
                bf=bf, rate=rate, maintenance=tr["maintenance_kcal"] if tr and tr["usable"] else None)
    t.update(weight_kg=round(weight, 1), weight_how=weight_how, body_fat_pct=bf, trend=tr)
    if tr and tr.get("pct_per_week") is not None and phase == "lose" and -tr["pct_per_week"] > t["loss_cap_pct_week"]:
        t["notes"].append(f"You have been losing {-tr['pct_per_week']:.2f} % a week, faster than the "
                          f"{t['loss_cap_pct_week']:g} % cap. Eat more: these targets are the new floor.")
    foods = load_foods()
    diet = str(prof.get("diet") or "omnivore")
    ok = allowed(foods, diet, as_list(prof.get("allergies")) + as_list(prof.get("foods_avoid")) + list(exclude))
    t["meal_plan"] = meal_plan(t, foods, ok, n_meals, prefer)
    t["diet"], t["avoid"] = diet, as_list(prof.get("allergies")) + as_list(prof.get("foods_avoid"))
    return t


# ---------------------------------------------------------------- writing

def fmt(n):
    return f"{round(n):,}"


def render(t, today):
    fm = ["---", "nutrition: 0.2", "status: on", f"since: {today.isoformat()}", f"phase: {t['phase']}",
          f"rate_pct_week: {t['rate_pct_week']:g}", f"kcal: {t['kcal']}", f"protein_g: {t['protein_g']}",
          f"fat_g: {t['fat_g']}", f"carbs_g: {t['carbs_g']}", f"maintenance_kcal: {t['maintenance_kcal']}",
          f"maintenance_source: {t['maintenance_source']}", f"resting_kcal: {t['resting_kcal']}",
          f"weight_kg: {t['weight_kg']}", f"loss_cap_pct_week: {t['loss_cap_pct_week']:g}", "---"]
    rate = {"lose": f"lose about {t['rate_pct_week']:g} % of body weight a week",
            "gain": f"gain about {t['rate_pct_week']:g} % of body weight a week", "maintain": "keep weight steady"}
    out = fm + ["# Nutrition", "", LAWYER, "", f"In force from {today.isoformat()}. Phase **{t['phase']}**: "
                f"{rate[t['phase']]}.", "", "## Daily targets", "",
                "| Calories | Protein | Fat | Carbs |", "|---|---|---|---|",
                f"| {fmt(t['kcal'])} kcal | {t['protein_g']} g | {t['fat_g']} g | {t['carbs_g']} g |", "",
                "## How we got these numbers", "", "| Step | How | Value |", "|---|---|---|"]
    out += [f"| {s['step']} | {s['how']} | {fmt(s['value'])} |" for s in t["steps"]]
    out += ["", f"Weight {t['weight_kg']} kg ({t['weight_how']}). Body fat: "
            + (f"{t['body_fat_pct']:g} % ({t['body_fat_band']})" if t["body_fat_pct"] is not None else
               "unknown (a range from a scale or photos lets the weekly loss cap go above 0.7 %)")
            + f". Loss cap for you: {t['loss_cap_pct_week']:g} % a week."]
    tr = t.get("trend")
    if tr and tr.get("kg_per_week") is not None:
        out.append(f"Weight trend {tr['since']} → {tr['until']}: {tr['kg_per_week']:+.2f} kg a week "
                   f"({tr['pct_per_week']:+.2f} %), {tr['weigh_ins']} weigh-ins"
                   + ("; used for maintenance." if tr["usable"] else f"; not used: {tr['why']}."))
    if t["notes"]:
        out += ["", "## Safeguards applied", ""] + [f"- {n}" for n in t["notes"]]
    mp = t["meal_plan"]
    out += ["", "## A day of meals", "", f"Diet: {t['diet']}" + (f"; avoiding: {', '.join(t['avoid'])}"
            if t["avoid"] else "") + ". Allergy tags are ours: always check labels.", "",
            "| Meal | Food | Amount | Protein | Carbs | Fat | kcal |", "|---|---|---|---|---|---|---|"]
    for m in mp["meals"]:
        for i, it in enumerate(m["items"]):
            out.append(f"| {m['meal'] if i == 0 else ''} | {it['name']} | {fmt(it['grams'])} g | "
                       f"{fmt(it['protein'])} | {fmt(it['carbs'])} | {fmt(it['fat'])} | {fmt(it['kcal'])} |")
    tot = mp["total"]
    out.append(f"| **Total** | | | **{fmt(tot['protein'])}** | **{fmt(tot['carbs'])}** | **{fmt(tot['fat'])}** | "
               f"**{fmt(tot['kcal'])}** |")
    out += ["", f"Against the targets: calories {mp['gap']['kcal_pct']:+.1f} %, protein {mp['gap']['protein_pct']:+.1f} %"
            + (" (on target)." if mp["on_target"] else
               ": off target. Swap a food or rerun with other `--prefer` foods."),
            "", "Food values: USDA FoodData Central (public domain), per `plugin/data/SOURCE.md`."]
    return "\n".join(out) + "\n"


def render_off(code, today):
    return "\n".join(["---", "nutrition: 0.2", "status: off", f"reason: {code}", f"since: {today.isoformat()}",
                      "---", "# Nutrition", "", LAWYER, "", "Calorie targets are off.", "", WORDING[code], ""])


def current_block(t, today):
    if t is None:
        return None
    return ("<!-- coaich:nutrition -->\n## Nutrition\n\n"
            + (f"Off ({t}) from {today.isoformat()}: no calorie targets. File `plan/nutrition.md`.\n"
               if isinstance(t, str) else
               f"Phase {t['phase']} ({t['rate_pct_week']:g} % a week) · {fmt(t['kcal'])} kcal · protein "
               f"{t['protein_g']} g · fat {t['fat_g']} g · carbs {t['carbs_g']} g · from {today.isoformat()} · "
               "file `plan/nutrition.md`.\n")
            + "<!-- /coaich:nutrition -->\n")


def write(folder, text, block):
    os.makedirs(os.path.join(folder, "plan"), exist_ok=True)
    with open(os.path.join(folder, "plan", "nutrition.md"), "w", encoding="utf-8") as f:
        f.write(text)
    write_current(folder, block, tag="nutrition")


# ---------------------------------------------------------------- command line

def ids(s):
    return [x.strip() for x in s.split(",") if x.strip()] if s else []


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("--dir", required=True)
    p.add_argument("--phase", choices=PHASES, help="default: nutrition_phase in profile.md")
    p.add_argument("--rate", type=float, help="% of body weight a week (lose: capped by body fat; gain: ≤ 0.5)")
    p.add_argument("--intake", type=float, help="average kcal/day actually eaten (default: the plan in force)")
    p.add_argument("--meals", type=int, choices=sorted(LAYOUTS), default=4)
    p.add_argument("--prefer", help="food ids to pick first, comma-separated")
    p.add_argument("--exclude", help="food ids or words to leave out, comma-separated")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--today", default=datetime.date.today().isoformat())
    t = sub.add_parser("trend")
    t.add_argument("--dir", required=True)
    t.add_argument("--intake", type=float)
    t.add_argument("--json", action="store_true")
    t.add_argument("--line", action="store_true", help="one line: the 4-week trend against the phase's band")
    t.add_argument("--today", default=datetime.date.today().isoformat())
    f = sub.add_parser("foods")
    f.add_argument("text", nargs="?", default="")
    f.add_argument("--diet", default="omnivore")
    f.add_argument("--avoid")
    f.add_argument("--group")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "foods":
            return cmd_foods(a)
        today = datetime.date.fromisoformat(a.today)
        if a.cmd == "trend":
            return cmd_trend(a, today)
        return cmd_plan(a, today)
    except Missing as e:
        print(f"stop: {e}", file=sys.stderr)
        return 2


def cmd_plan(a, today):
    try:
        t = run_plan(a.dir, today, a.phase, a.rate, a.intake, a.meals, ids(a.prefer), ids(a.exclude))
    except Safeguard as s:
        print(json.dumps({"safeguard": s.code, "off": s.off, "wording": str(s)}) if a.json else str(s))
        if not a.dry_run:
            if s.off:
                write(a.dir, render_off(s.code, today), current_block(s.code, today))
            af.append_log(a.dir, "nutrition", f"safeguard {s.code}: " + ("targets off" if s.off else "refused"),
                          today.isoformat())
        return 3
    if a.json:
        print(json.dumps(t, default=str, ensure_ascii=False, indent=1))
    else:
        print(render(t, today), end="")
    if not a.dry_run:
        write(a.dir, render(t, today), current_block(t, today))
        af.append_log(a.dir, "nutrition", f"{t['phase']} {t['rate_pct_week']:g} %/wk: {t['kcal']} kcal, "
                      f"P {t['protein_g']} g, F {t['fat_g']} g, C {t['carbs_g']} g "
                      f"(maintenance {t['maintenance_kcal']}, {t['maintenance_source']})", today.isoformat())
    return 0


def cmd_trend(a, today):
    prof = header(a.dir, "profile.md")
    try:
        gate(header(a.dir, "coaich.md"), prof)
        if not yes(prof.get("weight_tracking")):
            raise Safeguard("consent", off=False)
    except Safeguard as s:
        print(str(s))
        return 3
    if a.line:
        line = trend_line(a.dir, today)
        print(line or "No nutrition plan in force: no weight-trend line.")
        return 0 if line else 3
    tr = trend_for(a.dir, weigh_ins(a.dir, today), today, a.intake)
    if a.json:
        print(json.dumps(tr, indent=1))
    elif tr.get("kg_per_week") is None:
        print(f"No trend {tr['since']} → {tr['until']}: {tr['why']}.")
    else:
        print(f"Weight trend {tr['since']} → {tr['until']} ({tr['weigh_ins']} weigh-ins): "
              f"{tr['kg_per_week']:+.2f} kg a week ({tr['pct_per_week']:+.2f} % of body weight).")
        if "maintenance_kcal" in tr:
            print(f"Maintenance ≈ {fmt(tr['maintenance_kcal'])} kcal (±{tr['se_kcal']:.0f}), "
                  + ("good enough to use." if tr["usable"] else f"not used: {tr['why']}."))
    return 0


def cmd_foods(a):
    foods = load_foods()
    ok = allowed(foods, a.diet, ids(a.avoid))
    words = a.text.lower().split()
    rows = [f for i, f in foods.items() if i in ok and (not a.group or f["group"] == a.group)
            and all(w in (i + " " + f["name"]).lower() for w in words)]
    print("| id | Food | State | kcal | Protein | Carbs | Fat | Fibre | Contains | USDA FDC |")
    print("|---|---|---|---|---|---|---|---|---|---|")
    for f in rows:
        print(f"| {f['id']} | {f['name']} | {f['state']} | {f['kcal_100']:g} | {f['protein_100']:g} | "
              f"{f['carbs_100']:g} | {f['fat_100']:g} | {f['fibre_100']:g} | {f['contains'] or '—'} | {f['fdc_id']} |")
    print(f"\nPer 100 g. {len(rows)} foods.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
