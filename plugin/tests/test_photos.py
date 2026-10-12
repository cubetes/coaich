"""photos.py: safeguard gate, filing, metadata stripping (GPS), ratings round-trip, compare, priorities.
No real photos: every image is a tiny generated placeholder."""
import contextlib
import io
import json
import os
import struct
import tempfile
import shutil
import unittest
import zlib
from pathlib import Path
from unittest import mock

from support import make_folder, run
import athlete_folder as af
import photos as ph

PROFILE = """---
profile: 0.1
age_band: {age}
history: over-2y
last_trained: last-3m
days_per_week: 4
minutes_per_session: 60
eating_disorder_history: {ed}
photos_opt_in: {opt}
---
# Profile
"""
GPS_SENTINEL = b"N41LAT"  # stands in for coordinates inside the GPS block


def tiff_with_gps(orientation=6):
    """Big-endian TIFF: IFD0 = orientation + GPS pointer + camera make; GPS IFD with one ASCII value."""
    make = b"PHONECAM\x00"
    ifd0 = 8
    n0 = 3
    gps_ifd = ifd0 + 2 + 12 * n0 + 4
    gps_val = gps_ifd + 2 + 12 + 4
    make_off = gps_val + len(GPS_SENTINEL) + 1
    t = b"MM\x00\x2a" + struct.pack(">I", ifd0)
    t += struct.pack(">H", n0)
    t += struct.pack(">HHIHH", 0x0112, 3, 1, orientation, 0)
    t += struct.pack(">HHII", 0x8825, 4, 1, gps_ifd)
    t += struct.pack(">HHII", 0x010F, 2, len(make), make_off)
    t += struct.pack(">I", 0)
    t += struct.pack(">H", 1) + struct.pack(">HHII", 0x0002, 2, len(GPS_SENTINEL) + 1, gps_val) + struct.pack(">I", 0)
    t += GPS_SENTINEL + b"\x00" + make
    return t


def seg(marker, body):
    return bytes([0xFF, marker]) + struct.pack(">H", len(body) + 2) + body


# Structural stand-ins: not decodable pictures, but every segment the stripper must keep or drop.
DQT = seg(0xDB, b"\x00" + bytes(range(64)))
SOF = seg(0xC0, b"\x08\x00\x02\x00\x02\x01\x01\x11\x00")
DHT = seg(0xC4, b"\x00" + b"\x01" + b"\x00" * 15 + b"\x00")
SOS = seg(0xDA, b"\x01\x01\x00\x00\x3f\x00")
SCAN = b"\x12\xff\x00\x34\xff\xd0\x56\xff\xff\xd1\x78"  # stuffed byte, restart markers, a fill byte


def placeholder_jpeg(orientation=6):
    head = b"\xff\xd8" + seg(0xE0, b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00")
    exif = seg(0xE1, b"Exif\x00\x00" + tiff_with_gps(orientation))
    xmp = seg(0xE1, b"http://ns.adobe.com/xap/1.0/\x00<x:xmpmeta>GPSLatitude</x:xmpmeta>")
    icc = seg(0xE2, b"ICC_PROFILE\x00\x01\x01" + b"colour")
    com = seg(0xFE, b"taken at home")
    body = DQT + SOF + DHT + SOS + SCAN + b"\xff\xd9"
    gain_map = b"\xff\xd8" + seg(0xE1, b"Exif\x00\x00" + tiff_with_gps()) + b"\xff\xd9"  # a second image after EOI
    return head + exif + xmp + icc + com + body + gain_map, icc, body


def png_chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def placeholder_png():
    ihdr = png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    idat = png_chunk(b"IDAT", zlib.compress(b"\x00\x80\x80\x80"))
    meta = png_chunk(b"tEXt", b"Location\x00" + GPS_SENTINEL) + png_chunk(b"eXIf", tiff_with_gps()) + \
        png_chunk(b"iTXt", b"XML:com.adobe.xmp\x00\x00\x00\x00\x00<x:xmpmeta/>") + png_chunk(b"tIME", b"\x07\xee\x01\x01\x00\x00\x00")
    return ph.PNG_SIG + ihdr + meta + idat + png_chunk(b"IEND", b""), ihdr, idat


class Base(unittest.TestCase):
    def folder(self, age="18-59", ed="no", opt="yes"):
        d = make_folder(self)
        Path(d, "profile.md").write_text(PROFILE.format(age=age, ed=ed, opt=opt), encoding="utf-8")
        return d

    def images(self, d=None):
        """The user's originals, outside the athlete folder (where they keep their camera roll)."""
        d = d or tempfile.mkdtemp(prefix="coaich-originals-")
        self.addCleanup(shutil.rmtree, d, True)
        jpg = placeholder_jpeg()[0].replace(SCAN, ORIGINAL + SCAN)
        png, _, _ = placeholder_png()
        for name, data in (("a.jpg", jpg), ("b.png", png), ("c.jpg", jpg)):
            Path(d, name).write_bytes(data)
        return {"front": os.path.join(d, "a.jpg"), "side": os.path.join(d, "b.png"), "back": os.path.join(d, "c.jpg")}


ORIGINAL = b"ORIGINALPIXELS"  # only in the originals' image data: never in the athlete folder
# One face, high in a 1000 x 2000 standing photo; shoulders well below the chin.
FACE = [400, 200, 200, 240]
POINTS = {"nose": [500, 330], "left_eye": [460, 290], "right_eye": [540, 290], "neck": [500, 600],
          "left_shoulder": [380, 610], "right_shoulder": [620, 605]}
BACK_POINTS = {"neck": [500, 600], "left_shoulder": [620, 610], "right_shoulder": [380, 610],  # left/right swap from behind
               "left_ear": [560, 300], "right_ear": [440, 300]}


class FakeDetector:
    """Stands in for Apple Vision / OpenCV. Its output image still carries EXIF + GPS, so the tests prove that filing
    strips whatever a detector leaves in."""
    name = "fake"

    def __init__(self, faces=(FACE,), points=None, by_src=None):
        self.findings = {"width": 1000, "height": 2000, "faces": [list(f) for f in faces],
                         "points": POINTS if points is None else points}
        self.by_src = by_src or {}
        self.ops = []

    def detect(self, src):
        return self.by_src.get(src, self.findings)

    def render(self, src, dst, op):
        self.ops.append(op)
        Path(dst).write_bytes(placeholder_jpeg(orientation=1)[0])


class StripTest(unittest.TestCase):
    def test_jpeg_loses_exif_gps_xmp_comment_and_trailing_image(self):
        data, icc, body = placeholder_jpeg()
        self.assertIn(GPS_SENTINEL, data)
        out = ph.strip(data)
        for gone in (GPS_SENTINEL, b"PHONECAM", b"<x:xmpmeta", b"taken at home"):
            self.assertNotIn(gone, out)
        self.assertEqual(ph.metadata_left(out), [])
        self.assertEqual(ph.metadata_left(data), ["APP1", "APP1", "COM"])
        self.assertIn(icc, out)  # colour profile kept
        self.assertTrue(out.endswith(body))  # image segments and scan data byte for byte, nothing after EOI

    def test_jpeg_keeps_only_the_orientation(self):
        out = ph.strip(placeholder_jpeg(orientation=6)[0])
        app1 = [s for m, s in ph._jpeg_parts(out) if m == 0xE1]
        self.assertEqual(len(app1), 1)
        self.assertEqual(ph._orientation(app1[0]), 6)
        upright = ph.strip(placeholder_jpeg(orientation=1)[0])
        self.assertFalse([m for m, _ in ph._jpeg_parts(upright) if m == 0xE1])

    def test_png_loses_text_exif_xmp_and_time(self):
        data, ihdr, idat = placeholder_png()
        out = ph.strip(data)
        self.assertNotIn(GPS_SENTINEL, out)
        self.assertEqual(ph.metadata_left(out), [])
        self.assertEqual(out, ph.PNG_SIG + ihdr + idat + png_chunk(b"IEND", b""))
        self.assertEqual(zlib.decompress(out[8 + len(ihdr) + 8:8 + len(ihdr) + len(idat) - 4]), b"\x00\x80\x80\x80")

    def test_stripped_files_pass_the_repo_metadata_check(self):
        meta = (b"Exif\x00\x00", b"eXIf", b"tEXt", b"iTXt", b"zTXt", b"<x:xmpmeta", b"XMP ")
        png = ph.strip(placeholder_png()[0])
        self.assertFalse([m for m in meta if m in png])
        jpg = ph.strip(placeholder_jpeg(orientation=1)[0])
        self.assertFalse([m for m in meta if m in jpg])

    def test_other_formats_and_damage_are_refused(self):
        with self.assertRaisesRegex(ph.Refused, "JPEG"):
            ph.strip(b"\x00\x00\x00\x18ftypheic")
        with self.assertRaises(ValueError):
            ph.strip(placeholder_jpeg()[0][:40])


class GateTest(Base):
    def test_open_for_an_adult_who_opted_in(self):
        self.assertEqual(ph.gate(self.folder()), {"allowed": True, "reasons": []})

    def test_each_safeguard_closes_it(self):
        cases = {("16-17", "no", "yes"): "age", ("under-16", "no", "yes"): "age",
                 ("18-59", "yes", "yes"): "eating-disorder-history", ("18-59", "", "yes"): "eating-disorder-unanswered",
                 ("60+", "no", "no"): "no-photo-opt-in", ("18-59", "no", ""): "no-photo-opt-in",
                 ("", "no", "yes"): "age-unanswered", ("18-59", "prefer-not-to-say", "yes"): "eating-disorder-history"}
        for (age, ed, opt), reason in cases.items():
            g = ph.gate(self.folder(age, ed, opt))
            self.assertFalse(g["allowed"], (age, ed, opt))
            self.assertIn(reason, g["reasons"])

    def test_wellbeing_pause_closes_photos_and_described_priorities(self):
        d = self.folder()
        af.set_header(d, "profile.md", "wellbeing_pause", "2030-01-20")
        self.assertEqual(ph.gate(d), {"allowed": False, "reasons": ["wellbeing-pause"]})
        with self.assertRaisesRegex(ph.Refused, "wellbeing-pause"):
            ph.priorities(d, {"calves": "lagging"})

    def test_closed_gate_refuses_every_write(self):
        d = self.folder(ed="yes")
        imgs = self.images()
        with self.assertRaisesRegex(ph.Refused, "eating-disorder-history"):
            ph.file_photos(d, "2030-01-06", imgs)
        with self.assertRaises(ph.Refused):
            ph.rate(d, "2030-01-06", {"calves": "lagging"}, "medium")
        with self.assertRaises(ph.Refused):
            ph.body_fat(d, "2030-01-06", 15, 19)
        with self.assertRaises(ph.Refused):
            ph.priorities(d, {"calves": "lagging"})
        self.assertFalse(Path(d, "photos").exists())
        self.assertFalse(Path(d, "data", "body.csv").exists())

    def test_described_priorities_need_no_photo_opt_in(self):
        d = self.folder(opt="no")
        self.assertEqual(ph.priorities(d, {"calves": "lagging"})["ranked"][0]["group"], "calves")
        with self.assertRaises(ph.Refused):
            ph.priorities(d)  # from photo ratings: opt-in needed

    def test_cli_gate_exit_code(self):
        d = self.folder(age="16-17")
        r = run("photos.py", "gate", "--dir", d, ok=False)
        self.assertEqual(r.returncode, 2)
        self.assertIn("age", json.loads(r.stdout)["reasons"])


class FilingTest(Base):
    def test_files_by_pose_and_date_face_removed_without_metadata(self):
        d = self.folder()
        imgs = self.images()
        fake = FakeDetector(by_src={imgs["back"]: {"width": 1000, "height": 2000, "faces": [], "points": BACK_POINTS}})
        made = ph.file_photos(d, "2030-01-06", imgs, detector=fake)
        self.assertEqual(sorted(made), ["photos/2030-01-06/back.jpg", "photos/2030-01-06/front.jpg",
                                        "photos/2030-01-06/side.jpg"])
        self.assertEqual(fake.ops, [["crop", 512], ["crop", 540], ["cover", 410, 0, 590, 576]])
        for rel in made:
            data = Path(d, rel).read_bytes()
            self.assertNotIn(GPS_SENTINEL, data)
            self.assertEqual(ph.metadata_left(data), [])
        self.assertEqual(ph.photo_sets(d), [{"date": "2030-01-06", "poses": ["front", "side", "back"]}])

    def test_the_original_is_never_copied_into_the_folder(self):
        d = self.folder()
        imgs = self.images()
        ph.file_photos(d, "2030-01-06", {"front": imgs["front"]}, detector=FakeDetector())
        for f in Path(d).rglob("*"):
            if f.is_file():
                self.assertNotIn(ORIGINAL, f.read_bytes(), f)
        self.assertIn(ORIGINAL, Path(imgs["front"]).read_bytes())  # the user's own file is left as it was

    def test_blur_from_the_settings_file(self):
        d = self.folder()
        with open(Path(d, "coaich.md"), "a", encoding="utf-8") as f:
            f.write("photo_anonymise: blur\n")
        fake = FakeDetector()
        ph.file_photos(d, "2030-01-06", {"front": self.images()["front"]}, detector=fake)
        self.assertEqual(fake.ops, [["cover", 330, 56, 670, 512]])
        ph.file_photos(d, "2030-01-06", {"front": self.images()["front"]}, replace=True, mode="crop", detector=fake)
        self.assertEqual(fake.ops[-1], ["crop", 512])  # the command line wins over the setting

    def test_a_face_that_cannot_be_removed_writes_nothing(self):
        d = self.folder()
        imgs = self.images()
        two = FakeDetector(by_src={imgs["side"]: {"width": 1000, "height": 2000, "faces": [FACE, [100, 200, 90, 100]],
                                                   "points": {}}})
        with self.assertRaisesRegex(ph.Refused, "2 faces found"):
            ph.file_photos(d, "2030-01-06", imgs, detector=two)
        with self.assertRaisesRegex(ph.Refused, "no face found"):
            ph.file_photos(d, "2030-01-06", imgs, detector=FakeDetector(faces=(), points={}))
        self.assertFalse(Path(d, "photos").exists())

    def test_no_detector_stops_unless_the_user_cropped_it(self):
        d = self.folder()
        imgs = self.images()
        with mock.patch.object(ph, "find_detector", lambda: None):
            with self.assertRaisesRegex(ph.Refused, "no face detector"):
                ph.file_photos(d, "2030-01-06", {"front": imgs["front"]})
            self.assertFalse(Path(d, "photos").exists())
            made = ph.file_photos(d, "2030-01-06", {"front": imgs["side"]}, user_cropped=True)
        self.assertEqual(made, ["photos/2030-01-06/front.png"])
        self.assertEqual(ph.metadata_left(Path(d, made[0]).read_bytes()), [])

    def test_refuses_to_overwrite_unless_asked(self):
        d = self.folder()
        imgs = self.images()
        fake = FakeDetector()
        ph.file_photos(d, "2030-01-06", {"front": imgs["front"]}, detector=fake)
        with self.assertRaisesRegex(ph.Refused, "already has a front"):
            ph.file_photos(d, "2030-01-06", {"front": imgs["side"]}, detector=fake)
        ph.file_photos(d, "2030-01-06", {"front": imgs["side"]}, replace=True, detector=fake)
        self.assertEqual([p.name for p in Path(d, "photos", "2030-01-06").iterdir()], ["front.jpg"])

    def test_bad_input_writes_nothing(self):
        d = self.folder()
        imgs = self.images()
        Path(d, "x.heic").write_bytes(b"\x00\x00\x00\x18ftypheic")
        fake = FakeDetector()
        for poses in ({"front": imgs["front"], "side": os.path.join(d, "x.heic")}, {"pose-4": imgs["front"]}):
            with self.assertRaises(ph.Refused):
                ph.file_photos(d, "2030-01-06", poses, detector=fake)
        with self.assertRaisesRegex(ph.Refused, "not a date"):
            ph.file_photos(d, "06/01/2030", {"front": imgs["front"]}, detector=fake)
        with self.assertRaisesRegex(ph.Refused, "anonymise mode"):
            ph.file_photos(d, "2030-01-06", {"front": imgs["front"]}, mode="pixelate", detector=fake)
        self.assertFalse(Path(d, "photos").exists())
        self.assertEqual(fake.ops, [])

    def test_cli_files_and_logs(self):
        d = self.folder()
        imgs = self.images()
        fake = FakeDetector()
        with mock.patch.object(ph, "find_detector", lambda: fake), contextlib.redirect_stdout(io.StringIO()):
            code = ph.main(["file", "--dir", d, "--date", "2030-01-06", "--anonymise", "blur",
                            f"front={imgs['front']}", f"side={imgs['side']}"])
        self.assertEqual(code, 0)
        self.assertEqual([op[0] for op in fake.ops], ["cover", "cover"])
        self.assertIn("· physique · filed 2 photos for 2030-01-06 (face removed", Path(d, "log.md").read_text(encoding="utf-8"))


class PlanTest(unittest.TestCase):
    """Where the cut goes, from the detector's findings (pixels of the upright image, origin top-left)."""

    def det(self, faces=(FACE,), points=None):
        return {"width": 1000, "height": 2000, "faces": [list(f) for f in faces],
                "points": POINTS if points is None else points}

    def test_crop_line_just_below_the_chin_above_the_shoulders(self):
        # face box bottom 440 + 0.3 x 240 = 512; shoulders start at 605, so 512 < 605 - 72
        self.assertEqual(ph.anonymise_plan(self.det(), "front"), ["crop", 512])
        with self.assertRaisesRegex(ph.Refused, "neck is found"):  # profile: the face box ends above the jaw
            ph.anonymise_plan(self.det(points={}), "side")

    def test_a_head_point_below_the_box_moves_the_line_down(self):
        pts = dict(POINTS, nose=[500, 450])  # a tilted head: the nose sits under Vision's box
        self.assertEqual(ph.anonymise_plan(self.det(points=pts), "front"), ["crop", 522])

    def test_never_cuts_the_shoulders(self):
        pts = dict(POINTS, left_shoulder=[380, 520])  # 512 > 520 - 72: the cut would take the traps
        with self.assertRaisesRegex(ph.Refused, "too close to the shoulders"):
            ph.anonymise_plan(self.det(points=pts), "front")

    def test_blur_covers_face_ears_and_hair_down_to_the_same_line(self):
        self.assertEqual(ph.anonymise_plan(self.det(), "front", "blur"), ["cover", 330, 56, 670, 512])
        edge = ph.anonymise_plan(self.det(faces=([0, 20, 200, 240],), points={}), "front", "blur")
        self.assertEqual(edge, ["cover", 0, 0, 270, 332])  # clamped to the picture

    def test_stops_on_several_faces_or_none(self):
        with self.assertRaisesRegex(ph.Refused, "2 faces"):
            ph.anonymise_plan(self.det(faces=(FACE, [100, 100, 80, 90])), "front")
        for pose in ("front", "side"):
            with self.assertRaisesRegex(ph.Refused, "no face found"):
                ph.anonymise_plan(self.det(faces=(), points={}), pose)

    def test_one_head_found_twice_is_one_face_cut_below_the_lower_chin(self):
        # the real side-photo case: two boxes on the same head, the second lower
        self.assertEqual(ph.merge_faces([[436, 261, 153, 153], [448, 330, 135, 135]]), [[436, 261, 153, 204]])
        self.assertEqual(ph.merge_faces([[0, 0, 100, 100], [500, 0, 100, 100]]), [[0, 0, 100, 100], [500, 0, 100, 100]])
        twice = ph.anonymise_plan(self.det(faces=(FACE, [FACE[0] + 10, FACE[1] + 10, FACE[2] - 20, FACE[3] - 20])), "front")
        once = ph.anonymise_plan(self.det(faces=(FACE,)), "front")
        self.assertEqual(twice[0], "crop")
        self.assertGreaterEqual(twice[1], once[1])  # never cuts higher than for the single box

    def test_a_low_face_is_not_trusted(self):
        with self.assertRaisesRegex(ph.Refused, "not where a head should be"):
            ph.anonymise_plan(self.det(faces=([400, 1500, 200, 240],), points={}), "front")

    def test_back_view_covers_the_head_and_never_cuts(self):
        # a column between the ears, wider of 0.35 × shoulders or 1.5 × ear spread, down to 0.1 × shoulders above
        # the neck: arms raised beside the head (back double biceps) stay
        self.assertEqual(ph.anonymise_plan(self.det(faces=(), points=BACK_POINTS), "back"), ["cover", 410, 0, 590, 576])
        no_ears = {k: v for k, v in BACK_POINTS.items() if "ear" not in k}
        self.assertEqual(ph.anonymise_plan(self.det(faces=(), points=no_ears), "back"), ["cover", 416, 0, 584, 576])
        for missing in ("neck", "left_shoulder"):
            with self.assertRaisesRegex(ph.Refused, "could not be located"):
                pts = {k: v for k, v in BACK_POINTS.items() if k != missing}
                ph.anonymise_plan(self.det(faces=(), points=pts), "back")
        for face_point in ("nose", "left_eye", "right_eye"):
            with self.assertRaisesRegex(ph.Refused, "could not be outlined"):
                ph.anonymise_plan(self.det(faces=(), points=dict(BACK_POINTS, **{face_point: [500, 300]})), "back")
        # a face in a back view is covered, not cut, whatever the mode
        self.assertEqual(ph.anonymise_plan(self.det(), "back", "crop"), ["cover", 330, 56, 670, 512])

    def test_user_cropped_passes_only_with_no_face_left(self):
        self.assertEqual(ph.anonymise_plan(self.det(faces=(), points={}), "front", user_cropped=True), ["none"])
        self.assertEqual(ph.anonymise_plan(self.det(), "front", user_cropped=True), ["crop", 512])

    def test_overlap_merges_one_face_seen_twice(self):
        self.assertGreater(ph._overlap([0, 0, 100, 100], [10, 10, 80, 80]), 0.5)
        self.assertEqual(ph._overlap([0, 0, 10, 10], [50, 50, 10, 10]), 0)


class RatingsTest(Base):
    def test_round_trip_and_upsert(self):
        d = self.folder()
        ph.rate(d, "2030-01-06", {"calves": "lagging", "arms": "adequate"}, "medium", {"calves": "left a bit | behind"})
        ph.rate(d, "2030-01-06", {"calves": "severely-lagging"}, "high")
        rows = ph.read_ratings(d)
        self.assertEqual([(r["group"], r["rating"], r["confidence"]) for r in rows],
                         [("calves", "severely-lagging", "high"), ("arms", "adequate", "medium")])
        self.assertEqual(rows[0]["note"], "")
        ph.rate(d, "2030-01-06", {"arms": "adequate"}, "medium", {"arms": "a / b"})
        self.assertEqual(ph.read_ratings(d)[1]["note"], "a / b")
        text = Path(d, "photos", "ratings.md").read_text(encoding="utf-8")
        self.assertTrue(text.startswith("# Photo ratings"))

    def test_unknown_group_or_rating_is_refused(self):
        d = self.folder()
        for bad in ({"abs": "strong"}, {"calves": "weak"}):
            with self.assertRaises(ph.Refused):
                ph.rate(d, "2030-01-06", bad, "medium")
        with self.assertRaises(ph.Refused):
            ph.rate(d, "2030-01-06", {"calves": "strong"}, "certain")

    def test_body_fat_range_midpoint_and_source(self):
        d = self.folder()
        self.assertEqual(ph.body_fat(d, "2030-01-06", 15, 19), 17.0)
        body = af.read_rows(d, "data/body.csv")
        self.assertEqual(body, [{"date": "2030-01-06", "weight_kg": "", "waist_cm": "", "body_fat_pct": "17",
                                 "source": "photo-range"}])
        bf = [r for r in ph.read_ratings(d) if r["group"] == "body-fat"][0]
        self.assertEqual((bf["rating"], bf["confidence"]), ("15-19", "low"))
        for low, high in ((15, 17), (19, 15), (1, 9)):
            with self.assertRaises(ph.Refused):
                ph.body_fat(d, "2030-01-07", low, high)

    def test_body_fat_gets_its_own_row_beside_a_scale_reading(self):
        d = self.folder()
        af.upsert_rows(d, "data/body.csv", [{"date": "2030-01-06", "weight_kg": 80, "body_fat_pct": 18,
                                             "source": "scale"}])
        self.assertEqual(ph.body_fat(d, "2030-01-06", 15, 19), 17.0)
        ph.body_fat(d, "2030-01-06", 14, 18)  # a second estimate the same day replaces the first, not the scale's
        rows = {r["source"]: r for r in af.read_rows(d, "data/body.csv")}
        self.assertEqual(sorted(rows), ["photo-range", "scale"])
        self.assertEqual((rows["scale"]["weight_kg"], rows["scale"]["body_fat_pct"]), ("80", "18"))
        self.assertEqual((rows["photo-range"]["weight_kg"], rows["photo-range"]["body_fat_pct"]), ("", "16"))

    def test_compare_two_sets(self):
        d = self.folder()
        ph.rate(d, "2030-01-06", {"calves": "lagging", "arms": "adequate", "lats": "adequate"}, "high")
        ph.rate(d, "2030-02-03", {"calves": "adequate", "arms": "lagging", "lats": "adequate"}, "low")
        ph.body_fat(d, "2030-01-06", 16, 20)
        ph.body_fat(d, "2030-02-03", 13, 17)
        c = ph.compare(d)
        self.assertEqual((c["old"], c["new"]), ("2030-01-06", "2030-02-03"))
        got = {g["group"]: (g["change"], g["confidence"]) for g in c["groups"]}
        self.assertEqual(got, {"calves": ("better", "low"), "arms": ("worse", "low"), "lats": ("same", "low"),
                               "body-fat": ("lower", "low")})
        with self.assertRaises(ph.Refused):
            ph.compare(self.folder())


class PrioritiesTest(Base):
    def test_matrix_ranking_and_emphasis(self):
        d = self.folder()
        p = ph.priorities(d, {"calves": "lagging", "quads": "severely-lagging", "glutes": "lagging",
                              "chest": "adequate", "arms": "adequate", "lats": "strong"})
        self.assertEqual([(x["group"], x["priority"]) for x in p["ranked"]],
                         [("quads", 1), ("calves", 2), ("arms", 3), ("glutes", 3), ("lats", 0), ("chest", 0)])
        p = ph.priorities(d, {"chest": "adequate", "lats": "strong"}, emphasis=["chest"])
        self.assertEqual(p["ranked"][0], {"group": "chest", "rating": "adequate", "emphasis": True,
                                          "impact": "medium", "region": "chest", "priority": 2})

    def test_advanced_gets_one_region_others_a_long_term_note(self):
        d = self.folder()  # over 2 years, training now, no known loads → intermediate
        rated = {"rear-delts": "lagging", "calves": "severely-lagging"}
        p = ph.priorities(d, rated)
        self.assertEqual((p["level"], p["priority"], p["long_term"]), ("intermediate", None, ["calves", "shoulders"]))
        Path(d, "plan").mkdir()
        Path(d, "plan", "program.json").write_text('{"level": "advanced"}', encoding="utf-8")
        p = ph.priorities(d, rated)
        self.assertEqual((p["priority"], p["long_term"], p["timeline_weeks"]), ("calves", ["shoulders"], "20–36"))
        self.assertEqual(ph.priorities(d, {"lats": "strong"})["priority"], "none")

    def test_regions_are_program_build_priorities(self):
        import program_build as pb
        self.assertEqual({r for _, r in ph.GROUPS.values()}, {k.replace("_", "-") for k in pb.REGIONS})

    def test_from_the_latest_rated_set(self):
        d = self.folder()
        ph.rate(d, "2030-01-06", {"arms": "lagging"}, "medium")
        ph.rate(d, "2030-02-03", {"calves": "lagging"}, "medium")
        ph.body_fat(d, "2030-02-03", 15, 19)
        p = ph.priorities(d)
        self.assertEqual((p["date"], [x["group"] for x in p["ranked"]]), ("2030-02-03", ["calves"]))


if __name__ == "__main__":
    unittest.main()
