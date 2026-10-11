#!/usr/bin/env python3
"""Progress photos (plugin/docs/athlete-folder.md): the safeguard gate, filing with metadata stripped, the ratings
file, changes between sets and the muscle-group priorities.

Usage:
  photos.py gate [--dir D]                                   may photos be used? JSON; exit 2 = no
  photos.py file --date YYYY-MM-DD POSE=PATH... [--replace]  copy photos into photos/DATE/, metadata stripped
  photos.py strip IN OUT                                     strip one JPEG/PNG (no athlete folder needed)
  photos.py sets [--dir D]                                   the dated photo sets and their poses, JSON
  photos.py rate --date D GROUP=RATING... [--confidence C] [--note GROUP TEXT]   write rows to photos/ratings.md
  photos.py bodyfat --date D --low L --high H                body-fat range → ratings.md + body.csv midpoint
  photos.py compare [--from D1] [--to D2]                    rating changes between two sets, JSON
  photos.py priorities [--date D] [--rating GROUP=RATING...] [--emphasis G,G]   ranked priorities, JSON

POSE is front, side or back, decided by looking at each image (never by file name or order). GROUP and RATING
ids are in references/muscle-rubric.md. Exit 2 = refused (gate, bad input). Python stdlib only.
"""
import argparse
import datetime
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import athlete_folder as af  # noqa: E402
import program_build as pb  # noqa: E402

POSES = ("front", "side", "back")
RATINGS_FILE = "photos/ratings.md"
BODY_FAT = "body-fat"
CONFIDENCE = ("high", "medium", "low")

# The rubric (references/muscle-rubric.md): group → (visual impact, program_build priority region).
GROUPS = {
    "calves": ("high", "calves"),
    "quads": ("medium", "quads"),
    "hamstrings": ("low", "glutes-hamstrings"),
    "glutes": ("low", "glutes-hamstrings"),
    "lats": ("high", "back"),
    "upper-back": ("medium", "back"),
    "traps": ("medium", "back"),
    "chest": ("medium", "chest"),
    "upper-chest": ("medium", "chest"),
    "front-side-delts": ("high", "shoulders"),
    "rear-delts": ("high", "shoulders"),
    "arms": ("high", "arms"),
}
RATINGS = ("strong", "adequate", "lagging", "severely-lagging")  # index = how far behind
IMPACTS = ("high", "medium", "low")
# rating × visual impact → priority 1, 2, 3, or 0 = maintain.
MATRIX = {
    "severely-lagging": {"high": 1, "medium": 1, "low": 2},
    "lagging": {"high": 2, "medium": 2, "low": 3},
    "adequate": {"high": 3, "medium": 0, "low": 0},
    "strong": {"high": 0, "medium": 0, "low": 0},
}
# Rough time to a visible change for a priority group, by level (our rule, not a study).
TIMELINE_WEEKS = {"beginner": "8–12", "intermediate": "12–20", "advanced": "20–36"}


class Refused(Exception):
    """A safeguard or an input check said no. The message is said to the user."""


# ---------------------------------------------------------------- gate

def _profile(folder):
    path = Path(folder) / "profile.md"
    return pb.front_matter(path.read_text(encoding="utf-8")) if path.exists() else {}


def gate(folder, photos=True):
    """The photo/physique safeguards (the shared gate, athlete_folder.gate) → {"allowed", "reasons"}.
    photos=False checks only what an ideal-physique analysis without photos needs (age, the eating-disorder answer,
    no wellbeing pause)."""
    reasons = af.gate(_profile(folder), "photos" if photos else "physique")
    return {"allowed": not reasons, "reasons": reasons}


def _require(folder, photos=True):
    g = gate(folder, photos)
    if not g["allowed"]:
        raise Refused("photo and physique features are off: " + ", ".join(g["reasons"]))


# ---------------------------------------------------------------- metadata

def _jpeg_parts(data):
    """A JPEG as [(marker, bytes)]: marker segments with their 0xFF + marker prefix, and (None, bytes) for the
    entropy-coded scan data. Stops at the first end-of-image: anything after it (a second image) is dropped."""
    if data[:2] != b"\xff\xd8":
        raise ValueError("not a JPEG")
    parts, i, n = [(0xD8, b"\xff\xd8")], 2, len(data)
    while True:
        if i >= n or data[i] != 0xFF:
            raise ValueError("damaged JPEG: no marker where one should be")
        while i < n and data[i] == 0xFF:  # fill bytes
            i += 1
        if i >= n:
            raise ValueError("damaged JPEG: ends inside a marker")
        m = data[i]
        i += 1
        if m == 0xD9:
            parts.append((m, b"\xff\xd9"))
            return parts
        if 0xD0 <= m <= 0xD7 or m == 0x01:
            parts.append((m, bytes([0xFF, m])))
            continue
        length = int.from_bytes(data[i:i + 2], "big")
        if length < 2 or i + length > n:
            raise ValueError("damaged JPEG: a segment runs past the end")
        parts.append((m, bytes([0xFF, m]) + data[i:i + length]))
        i += length
        if m == 0xDA:  # scan data runs to the next marker that is not a stuffed byte or a restart
            j = i
            while True:
                j = data.find(b"\xff", j)
                if j < 0 or j + 1 >= n:
                    raise ValueError("damaged JPEG: no end of image")
                nxt = data[j + 1]
                if nxt == 0xFF:
                    j += 1
                elif nxt == 0x00 or 0xD0 <= nxt <= 0xD7:
                    j += 2
                else:
                    break
            parts.append((None, data[i:j]))
            i = j


def _orientation(app1):
    """The EXIF orientation (1–8) from an APP1 segment, or None."""
    body = app1[4:]
    if not body.startswith(b"Exif\x00\x00"):
        return None
    t = body[6:]
    order = {b"II": "little", b"MM": "big"}.get(t[:2])
    if not order or len(t) < 8:
        return None
    ifd = int.from_bytes(t[4:8], order)
    if ifd + 2 > len(t):
        return None
    for k in range(int.from_bytes(t[ifd:ifd + 2], order)):
        e = t[ifd + 2 + 12 * k: ifd + 14 + 12 * k]
        if len(e) == 12 and int.from_bytes(e[:2], order) == 0x0112:
            v = int.from_bytes(e[8:10], order)
            return v if 1 <= v <= 8 else None
    return None


def _orientation_app1(v):
    """A minimal EXIF segment holding only the orientation, so a portrait photo still shows upright."""
    tiff = b"MM\x00\x2a\x00\x00\x00\x08" + (1).to_bytes(2, "big") + \
        (0x0112).to_bytes(2, "big") + (3).to_bytes(2, "big") + (1).to_bytes(4, "big") + v.to_bytes(2, "big") + \
        b"\x00\x00" + b"\x00\x00\x00\x00"
    body = b"Exif\x00\x00" + tiff
    return b"\xff\xe1" + (len(body) + 2).to_bytes(2, "big") + body


def _jpeg_keep(m, seg):
    """Segments that are not metadata: everything but APPn and comments, plus the JFIF header, the colour
    profile (ICC) and the Adobe colour-transform flag."""
    if m == 0xFE:
        return False
    if not 0xE0 <= m <= 0xEF:
        return True
    tag = seg[4:]
    return (m == 0xE0 and tag.startswith(b"JFIF\x00")) or (m == 0xE2 and tag.startswith(b"ICC_PROFILE\x00")) or \
        (m == 0xEE and tag.startswith(b"Adobe"))


def strip_jpeg(data):
    parts = _jpeg_parts(data)
    rot = next((o for m, s in parts if m == 0xE1 for o in [_orientation(s)] if o), None)
    out, placed = [], rot in (None, 1)
    for m, seg in parts:
        if m is not None and not _jpeg_keep(m, seg):
            continue
        if not placed and m not in (0xD8, 0xE0):
            out.append(_orientation_app1(rot))
            placed = True
        out.append(seg)
    return b"".join(out)


PNG_SIG = b"\x89PNG\r\n\x1a\n"
# Image data and how to draw it; every other chunk (text, EXIF, time, private chunks) is dropped.
PNG_KEEP = {b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS", b"gAMA", b"cHRM", b"sRGB", b"iCCP", b"sBIT", b"pHYs"}


def _png_chunks(data):
    if not data.startswith(PNG_SIG):
        raise ValueError("not a PNG")
    i, out = len(PNG_SIG), []
    while i + 8 <= len(data):
        length, kind = int.from_bytes(data[i:i + 4], "big"), data[i + 4:i + 8]
        end = i + 12 + length
        if end > len(data):
            raise ValueError("damaged PNG: a chunk runs past the end")
        out.append((kind, data[i:end]))
        i = end
        if kind == b"IEND":
            return out
    raise ValueError("damaged PNG: no IEND")


def strip_png(data):
    return PNG_SIG + b"".join(c for kind, c in _png_chunks(data) if kind in PNG_KEEP)


def kind(data):
    if data.startswith(b"\xff\xd8"):
        return "jpg"
    if data.startswith(PNG_SIG):
        return "png"
    raise Refused("only JPEG and PNG photos can be cleaned. Export the photo as JPEG first (on an iPhone: "
                  "Settings › Camera › Formats › Most Compatible, or share it as JPEG).")


def strip(data):
    """Image bytes without location, time, device or any other metadata. Orientation survives (JPEG)."""
    return strip_jpeg(data) if kind(data) == "jpg" else strip_png(data)


def metadata_left(data):
    """Names of the metadata blocks still in an image: [] when it is clean."""
    if kind(data) == "png":
        return [k.decode("latin-1") for k, _ in _png_chunks(data) if k not in PNG_KEEP]
    left = []
    for m, seg in _jpeg_parts(data):
        if m is None or _jpeg_keep(m, seg):
            continue
        if m == 0xE1 and seg == _orientation_app1(_orientation(seg) or 1):
            continue  # our orientation-only block
        left.append("COM" if m == 0xFE else f"APP{m - 0xE0}")
    return left


# ---------------------------------------------------------------- filing

def _date(s):
    try:
        return datetime.date.fromisoformat(s).isoformat()
    except (TypeError, ValueError):
        raise Refused(f"'{s}' is not a date (YYYY-MM-DD)")


def file_photos(folder, date, poses, replace=False):
    """poses = {pose: source path}. Copies each into photos/DATE/POSE.jpg|png without metadata. Returns the paths
    written, relative to the folder. Refuses if the gate is closed or a pose is already filed (unless replace)."""
    _require(folder)
    date = _date(date)
    if not poses:
        raise Refused("no photos given")
    bad = set(poses) - set(POSES)
    if bad:
        raise Refused(f"unknown pose {sorted(bad)}: use front, side or back")
    day = Path(folder) / "photos" / date
    clean = {}
    for pose, src in poses.items():  # read and clean all first: nothing is written if one fails
        try:
            raw = Path(src).read_bytes()
        except OSError as e:
            raise Refused(f"cannot read {src}: {e.strerror}")
        try:
            data = strip(raw)
        except ValueError as e:
            raise Refused(f"{src}: {e}")
        if metadata_left(data):
            raise Refused(f"{src}: metadata could not be removed")
        old = [p for p in day.glob(pose + ".*")] if day.exists() else []
        if old and not replace:
            raise Refused(f"{date} already has a {pose} photo; say so to replace it")
        clean[pose] = (data, kind(raw), old)
    day.mkdir(parents=True, exist_ok=True)
    written = []
    for pose, (data, ext, old) in clean.items():
        for p in old:
            p.unlink()
        out = day / f"{pose}.{ext}"
        out.write_bytes(data)
        written.append(str(out.relative_to(folder)))
    return written


def photo_sets(folder):
    root = Path(folder) / "photos"
    if not root.exists():
        return []
    out = []
    for d in sorted(p for p in root.iterdir() if p.is_dir() and re.fullmatch(r"\d{4}-\d{2}-\d{2}", p.name)):
        poses = sorted({p.stem for p in d.iterdir() if p.stem in POSES})
        out.append({"date": d.name, "poses": [p for p in POSES if p in poses]})
    return out


# ---------------------------------------------------------------- ratings.md

HEADER = """# Photo ratings

Muscle-group ratings from progress photos (rubric: the plugin's references/muscle-rubric.md) and the body-fat
range estimated from the same photos. Written by the physique skill through scripts/photos.py: one row per date
and group. A body-fat row is a rough visual range, never a measurement.

| date | group | rating | confidence | note |
|---|---|---|---|---|
"""
COLUMNS = ("date", "group", "rating", "confidence", "note")


def read_ratings(folder):
    path = Path(folder) / RATINGS_FILE
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and len(cells) == len(COLUMNS) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", cells[0]):
            rows.append(dict(zip(COLUMNS, cells)))
    return rows


def _order(r):
    g = r["group"]
    return r["date"], list(GROUPS).index(g) if g in GROUPS else len(GROUPS)


def write_ratings(folder, rows):
    """Upsert rows by (date, group). Returns the number of rows written or changed."""
    for r in rows:
        if r["group"] != BODY_FAT and r["group"] not in GROUPS:
            raise Refused(f"unknown group '{r['group']}': use one of {', '.join(GROUPS)}")
        if r["group"] != BODY_FAT and r["rating"] not in RATINGS:
            raise Refused(f"unknown rating '{r['rating']}': use one of {', '.join(RATINGS)}")
        if r.get("confidence", "") not in CONFIDENCE:
            raise Refused(f"confidence must be one of {', '.join(CONFIDENCE)}")
    table = {(r["date"], r["group"]): r for r in read_ratings(folder)}
    changed = 0
    for r in rows:
        clean = {c: " ".join(str(r.get(c) or "").replace("|", "/").split()) for c in COLUMNS}
        if table.get((clean["date"], clean["group"])) != clean:
            changed += 1
        table[(clean["date"], clean["group"])] = clean
    path = Path(folder) / RATINGS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["| " + " | ".join(r[c] for c in COLUMNS) + " |" for r in sorted(table.values(), key=_order)]
    tmp = path.with_suffix(".tmp")
    tmp.write_text(HEADER + "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    os.replace(tmp, path)
    return changed


def rate(folder, date, ratings, confidence, notes=None):
    _require(folder)
    date = _date(date)
    notes = notes or {}
    return write_ratings(folder, [{"date": date, "group": g, "rating": r, "confidence": confidence,
                                   "note": notes.get(g, "")} for g, r in ratings.items()])


def body_fat(folder, date, low, high):
    """A visual body-fat range → a ratings.md row and the midpoint in body.csv, in its own `photo-range` row
    (body.csv is keyed by date + source, so a scale or Apple Health reading on the same day stays as it is). The
    range must be at least 4 points wide. Returns the midpoint."""
    _require(folder)
    date = _date(date)
    if not 3 <= low < high <= 60:
        raise Refused("the range must be two numbers between 3 and 60, low first")
    if high - low < 4:
        raise Refused("a photo estimate is too rough for a range under 4 points: widen it")
    mid = round((low + high) / 2, 1)
    write_ratings(folder, [{"date": date, "group": BODY_FAT, "rating": f"{low:g}-{high:g}", "confidence": "low",
                            "note": f"visual estimate; midpoint {mid:g}"}])
    af.upsert_rows(folder, "data/body.csv", [{"date": date, "body_fat_pct": mid, "source": "photo-range"}])
    return mid


# ---------------------------------------------------------------- compare and priorities

def compare(folder, old=None, new=None):
    """Rating changes between two dated sets (default: the last two dates in ratings.md)."""
    rows = read_ratings(folder)
    dates = sorted({r["date"] for r in rows})
    new = new or (dates[-1] if dates else None)
    old = old or next((d for d in reversed(dates) if new and d < new), None)
    if not old or not new:
        raise Refused("comparing needs two rated dates in photos/ratings.md")
    by = {(r["date"], r["group"]): r for r in rows}
    out = []
    for g in (*GROUPS, BODY_FAT):
        a, b = by.get((old, g)), by.get((new, g))
        if not a or not b:
            continue
        if g == BODY_FAT:
            mids = [sum(map(float, x["rating"].split("-"))) / 2 for x in (a, b)]
            change = "about the same" if abs(mids[1] - mids[0]) < 2 else ("lower" if mids[1] < mids[0] else "higher")
        else:
            d = RATINGS.index(b["rating"]) - RATINGS.index(a["rating"])
            change = "better" if d < 0 else "worse" if d > 0 else "same"
        conf = min((a["confidence"], b["confidence"]), key=lambda c: -CONFIDENCE.index(c))
        out.append({"group": g, "old": a["rating"], "new": b["rating"], "change": change, "confidence": conf})
    return {"old": old, "new": new, "groups": out}


def _level(folder):
    try:
        return json.loads((Path(folder) / "plan" / "program.json").read_text(encoding="utf-8"))["level"]
    except (OSError, ValueError, KeyError):
        pass
    try:
        a = pb.read_answers(str(folder))
        return pb.place(a["history"], a.get("last_trained"), a.get("known_loads"))["level"]
    except (ValueError, KeyError):
        return None


def priorities(folder, ratings=None, date=None, emphasis=()):
    """Ranked muscle-group priorities. `ratings` (described, no photos) or the ratings.md rows of `date` (default:
    the latest). Each `emphasis` group (what the goal physique stresses) counts one step further behind.
    → {level, date, ranked, priority (advanced: one program_build region), long_term (others: regions), timeline}."""
    _require(folder, photos=ratings is None)
    if ratings is None:
        rows = [r for r in read_ratings(folder) if r["group"] in GROUPS]
        date = date or max((r["date"] for r in rows), default=None)
        ratings = {r["group"]: r["rating"] for r in rows if r["date"] == date}
        if not ratings:
            raise Refused("no muscle-group ratings to rank: rate a photo set first, or describe the groups")
    for g, r in ratings.items():
        if g not in GROUPS or r not in RATINGS:
            raise Refused(f"unknown group or rating: {g}={r}")
    bad = set(emphasis) - set(GROUPS)
    if bad:
        raise Refused(f"unknown emphasis group {sorted(bad)}")
    ranked = []
    for g, r in ratings.items():
        behind = RATINGS[min(RATINGS.index(r) + (g in emphasis), len(RATINGS) - 1)]
        impact, region = GROUPS[g]
        ranked.append({"group": g, "rating": r, "emphasis": g in emphasis, "impact": impact, "region": region,
                       "priority": MATRIX[behind][impact]})
    ranked.sort(key=lambda x: (x["priority"] or 9, IMPACTS.index(x["impact"]), list(GROUPS).index(x["group"])))
    regions = list(dict.fromkeys(x["region"] for x in ranked if x["priority"]))
    level = _level(folder)
    return {"level": level, "date": date, "ranked": ranked,
            "priority": (regions[0] if regions else "none") if level == "advanced" else None,
            "long_term": regions if level != "advanced" else regions[1:],
            "timeline_weeks": TIMELINE_WEEKS.get(level)}


# ---------------------------------------------------------------- CLI

def _pairs(items, what):
    out = {}
    for it in items or []:
        k, sep, v = it.partition("=")
        if not sep or not k or not v:
            raise Refused(f"'{it}' is not {what}")
        out[k.strip().lower()] = v.strip()
    return out


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("gate", "file", "sets", "rate", "bodyfat", "compare", "priorities"):
        sp = sub.add_parser(name)
        sp.add_argument("--dir")
    s = sub.choices
    s["file"].add_argument("--date", required=True)
    s["file"].add_argument("photos", nargs="+", metavar="POSE=PATH")
    s["file"].add_argument("--replace", action="store_true")
    st = sub.add_parser("strip")
    st.add_argument("src")
    st.add_argument("dst")
    s["rate"].add_argument("--date", required=True)
    s["rate"].add_argument("ratings", nargs="+", metavar="GROUP=RATING")
    s["rate"].add_argument("--confidence", default="medium", choices=CONFIDENCE)
    s["rate"].add_argument("--note", nargs=2, action="append", metavar=("GROUP", "TEXT"))
    s["bodyfat"].add_argument("--date", required=True)
    s["bodyfat"].add_argument("--low", type=float, required=True)
    s["bodyfat"].add_argument("--high", type=float, required=True)
    s["compare"].add_argument("--from", dest="old")
    s["compare"].add_argument("--to", dest="new")
    s["priorities"].add_argument("--date")
    s["priorities"].add_argument("--rating", action="append", metavar="GROUP=RATING")
    s["priorities"].add_argument("--emphasis", default="")
    a = p.parse_args(argv)
    try:
        if a.cmd == "strip":
            data = strip(Path(a.src).read_bytes())
            Path(a.dst).write_bytes(data)
            print(f"wrote {a.dst} without metadata")
            return 0
        folder = af.find(a.dir)
        if a.cmd == "gate":
            g = gate(folder)
            print(json.dumps(g))
            return 0 if g["allowed"] else 2
        if a.cmd == "file":
            made = file_photos(folder, a.date, _pairs(a.photos, "POSE=PATH"), a.replace)
            af.append_log(folder, "physique", f"filed {len(made)} photos for {a.date} (metadata stripped)")
            print("\n".join(made))
        elif a.cmd == "sets":
            print(json.dumps(photo_sets(folder)))
        elif a.cmd == "rate":
            n = rate(folder, a.date, _pairs(a.ratings, "GROUP=RATING"), a.confidence,
                     {g.lower(): t for g, t in a.note or []})
            print(f"photos/ratings.md: {n} row(s) written for {a.date}")
        elif a.cmd == "bodyfat":
            mid = body_fat(folder, a.date, a.low, a.high)
            print(f"body fat about {a.low:g}–{a.high:g} % (midpoint {mid:g}) → photos/ratings.md and data/body.csv "
                  "(its own photo-range row)")
        elif a.cmd == "compare":
            print(json.dumps(compare(folder, a.old, a.new), ensure_ascii=False))
        else:
            rated = _pairs(a.rating, "GROUP=RATING") or None
            emph = [e.strip().lower() for e in a.emphasis.split(",") if e.strip()]
            print(json.dumps(priorities(folder, rated, a.date, emph), ensure_ascii=False))
    except Refused as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    except (FileNotFoundError, ValueError) as e:
        print(e, file=sys.stderr)
        return 2 if isinstance(e, ValueError) else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
