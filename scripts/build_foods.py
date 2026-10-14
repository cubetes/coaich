#!/usr/bin/env python3
"""Rebuild data/foods.csv from USDA FoodData Central (public domain). Maintainers only.

Usage: FDC_API_KEY=<key> python3 build_foods.py [--out data/foods.csv]

The food list (our ids, names, meal groups, "contains" tags, piece weights) lives in FOODS below; every number
in foods.csv comes from the FDC record named by its fdc_id. Needs the network and a free FDC key
(https://fdc.nal.usda.gov/api-key-signup; DEMO_KEY works for a single run). The plugin itself never calls FDC.
Python stdlib only.
"""
import argparse
import csv
import json
import os
import sys
import urllib.request

API = "https://api.nal.usda.gov/fdc/v1/foods"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "foods.csv")
COLUMNS = ["id", "name", "group", "state", "kcal_100", "protein_100", "carbs_100", "fat_100", "fibre_100",
           "piece_g", "contains", "fdc_id", "fdc_data_type", "fdc_description"]
ENERGY, PROTEIN, FAT, CARB_BY_DIFF, FIBRE = 1008, 1003, 1004, 1005, 1079

# id, name, group, state, piece_g (grams per piece, blank if weighed), contains (our tags), fdc_id.
# groups: protein | starch | fruit | veg | fat | drink. "contains" drives diet and allergy filters (nutrition.py);
# oats carry `gluten` because they are often cross-contaminated (our rule).
FOODS = [
    ("chicken_breast", "Chicken breast", "protein", "cooked", "", "poultry", 171477),
    ("turkey_breast", "Turkey breast", "protein", "cooked", "", "poultry", 171496),
    ("beef_mince_90", "Beef mince, 90 % lean", "protein", "cooked", "", "meat", 171794),
    ("pork_loin", "Pork loin, lean", "protein", "cooked", "", "meat", 168254),
    ("salmon", "Salmon", "protein", "cooked", "", "fish", 175168),
    ("tuna_canned", "Tuna, canned in water", "protein", "drained", "", "fish", 171986),
    ("cod", "Cod", "protein", "cooked", "", "fish", 171956),
    ("shrimp", "Shrimp", "protein", "cooked", "", "shellfish", 175180),
    ("egg", "Egg", "protein", "boiled", "50", "egg", 173424),
    ("egg_white", "Egg white", "protein", "raw", "33", "egg", 172183),
    ("greek_yogurt", "Greek yogurt, plain, low-fat", "protein", "as sold", "", "milk", 170903),
    ("cottage_cheese", "Cottage cheese, 2 %", "protein", "as sold", "", "milk", 172182),
    ("whey", "Whey protein powder", "protein", "powder", "", "milk", 173180),
    ("tofu", "Tofu, firm", "protein", "raw", "", "soy", 172475),
    ("tempeh", "Tempeh", "protein", "raw", "", "soy", 174272),
    ("edamame", "Edamame", "protein", "cooked", "", "soy", 168411),
    ("lentils", "Lentils", "protein", "cooked", "", "", 172421),
    ("chickpeas", "Chickpeas, canned", "protein", "drained", "", "", 173800),
    ("black_beans", "Black beans", "protein", "cooked", "", "", 173735),
    ("milk", "Milk, 2 %", "drink", "as sold", "", "milk", 171267),
    ("soy_milk", "Soy milk, unsweetened", "drink", "as sold", "", "soy", 175215),
    ("oats", "Oats", "starch", "dry", "", "gluten", 173904),
    ("rice_white", "White rice", "starch", "cooked", "", "", 168878),
    ("rice_brown", "Brown rice", "starch", "cooked", "", "", 169704),
    ("pasta", "Pasta", "starch", "cooked", "", "gluten", 169737),
    ("bread_wholewheat", "Whole-wheat bread", "starch", "as sold", "32", "gluten", 172688),
    ("potato", "Potato, baked with skin", "starch", "cooked", "", "", 170093),
    ("sweet_potato", "Sweet potato, baked", "starch", "cooked", "", "", 168483),
    ("quinoa", "Quinoa", "starch", "cooked", "", "", 168917),
    ("banana", "Banana", "fruit", "raw", "118", "", 173944),
    ("apple", "Apple", "fruit", "raw", "180", "", 171688),
    ("orange", "Orange", "fruit", "raw", "140", "", 169097),
    ("blueberries", "Blueberries", "fruit", "raw", "", "", 171711),
    ("broccoli", "Broccoli", "veg", "cooked", "", "", 169967),
    ("green_beans", "Green beans", "veg", "cooked", "", "", 169141),
    ("spinach", "Spinach", "veg", "raw", "", "", 168462),
    ("carrot", "Carrot", "veg", "raw", "", "", 170393),
    ("tomato", "Tomato", "veg", "raw", "", "", 170457),
    ("red_pepper", "Red pepper", "veg", "raw", "", "", 170108),
    ("olive_oil", "Olive oil", "fat", "as sold", "", "", 171413),
    ("avocado", "Avocado", "fat", "raw", "", "", 171705),
    ("almonds", "Almonds", "fat", "raw", "", "tree-nut", 170567),
    ("walnuts", "Walnuts", "fat", "raw", "", "tree-nut", 170187),
    ("peanut_butter", "Peanut butter", "fat", "as sold", "", "peanut", 172470),
    ("chia", "Chia seeds", "fat", "dry", "", "", 170554),
]


def fetch(ids, key):
    body = json.dumps({"fdcIds": ids, "format": "full"}).encode()
    req = urllib.request.Request(f"{API}?api_key={key}", data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return {f["fdcId"]: f for f in json.load(r)}


def per_100(record):
    amounts = {}
    for n in record.get("foodNutrients", []):
        nid = (n.get("nutrient") or {}).get("id")
        if nid is not None and n.get("amount") is not None:
            amounts[nid] = float(n["amount"])
    fibre = amounts.get(FIBRE, 0.0)
    carbs = max(0.0, amounts.get(CARB_BY_DIFF, 0.0) - fibre)  # available carbohydrate
    missing = [n for n in (ENERGY, PROTEIN, FAT) if n not in amounts]
    if missing:
        raise ValueError(f"FDC {record['fdcId']}: missing nutrient ids {missing}")
    return amounts[ENERGY], amounts[PROTEIN], carbs, amounts[FAT], fibre


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default=OUT)
    a = ap.parse_args(argv)
    key = os.environ.get("FDC_API_KEY", "DEMO_KEY")
    ids = [f[-1] for f in FOODS]
    records = {}
    for i in range(0, len(ids), 20):
        records.update(fetch(ids[i:i + 20], key))
    with open(a.out, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(COLUMNS)
        for fid, name, group, state, piece, contains, fdc in FOODS:
            rec = records[fdc]
            kcal, p, c, f, fib = per_100(rec)
            w.writerow([fid, name, group, state, f"{kcal:g}", f"{p:g}", f"{round(c, 2):g}", f"{f:g}", f"{fib:g}",
                        piece, contains, fdc, rec.get("dataType", ""), rec.get("description", "")])
    print(f"wrote {len(FOODS)} foods to {a.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
