"""anonymise.swift on a real Mac (Apple Vision + ImageIO): a generated picture with no face stops, and EXIF
orientation is applied before anything is measured or cut. Skipped off macOS. No real photos: flat colour blocks."""
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

from support import make_folder
import photos as ph
from test_photos import PROFILE, GPS_SENTINEL, seg, tiff_with_gps

RED, BLUE = (220, 30, 30), (30, 30, 220)


def png(width, height, colour_at):
    rows = b"".join(b"\x00" + b"".join(bytes(colour_at(x, y)) for x in range(width)) for y in range(height))
    chunk = lambda k, d: struct.pack(">I", len(d)) + k + d + struct.pack(">I", zlib.crc32(k + d))  # noqa: E731
    return ph.PNG_SIG + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(rows)) + chunk(b"IEND", b"")


def pixels(path, tmp):
    """(width, height, pixel(x, y) → (r, g, b)) of any image, decoded by sips into an uncompressed BMP."""
    bmp = Path(tmp) / "decoded.bmp"
    subprocess.run(["sips", "-s", "format", "bmp", str(path), "--out", str(bmp)], check=True, capture_output=True)
    d = bmp.read_bytes()
    off, w, h, bpp = struct.unpack_from("<I", d, 10)[0], *struct.unpack_from("<iiH", d, 18)[:2], struct.unpack_from("<H", d, 28)[0]
    stride, step = (w * bpp // 8 + 3) // 4 * 4, bpp // 8

    def at(x, y):
        row = (abs(h) - 1 - y) if h > 0 else y  # positive height = rows stored bottom-up
        b, g, r = d[off + row * stride + x * step: off + row * stride + x * step + 3]
        return r, g, b
    return w, abs(h), at


def near(c, want):
    return all(abs(a - b) < 40 for a, b in zip(c, want))


@unittest.skipUnless(sys.platform == "darwin" and shutil.which("swiftc") and shutil.which("sips"), "macOS only")
class VisionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vision = ph.find_detector()  # compiles anonymise.swift once into ~/Library/Caches/coaich

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="coaich-vision-")
        self.addCleanup(shutil.rmtree, self.tmp)

    def rotated_jpeg(self):
        """Stored 80 x 40, left half red, with EXIF orientation 6 (show turned 90° clockwise) and a GPS block:
        upright it is 40 x 80, red on top."""
        src = Path(self.tmp, "raw.png")
        src.write_bytes(png(80, 40, lambda x, y: RED if x < 40 else BLUE))
        jpg = Path(self.tmp, "raw.jpg")
        subprocess.run(["sips", "-s", "format", "jpeg", str(src), "--out", str(jpg)], check=True, capture_output=True)
        plain = ph.strip(jpg.read_bytes())
        jpg.write_bytes(plain[:2] + seg(0xE1, b"Exif\x00\x00" + tiff_with_gps(6)) + plain[2:])
        return jpg

    def test_detects_on_the_upright_image(self):
        det = self.vision.detect(self.rotated_jpeg())
        self.assertEqual((det["width"], det["height"]), (40, 80))
        self.assertEqual(det["faces"], [])

    def test_renders_upright_without_metadata(self):
        jpg = self.rotated_jpeg()
        out = Path(self.tmp, "out.jpg")
        self.vision.render(jpg, out, ["none"])
        data = out.read_bytes()
        self.assertNotIn(GPS_SENTINEL, data)
        self.assertNotIn(b"PHONECAM", data)
        self.assertFalse([m for m, s in ph._jpeg_parts(data) if m == 0xE1 and ph._orientation(s) not in (None, 1)])
        w, h, at = pixels(out, self.tmp)
        self.assertEqual((w, h), (40, 80))
        self.assertTrue(near(at(20, 10), RED) and near(at(20, 70), BLUE), (at(20, 10), at(20, 70)))
        self.vision.render(jpg, out, ["crop", 40])  # the cut is measured on the upright picture
        w, h, at = pixels(out, self.tmp)
        self.assertEqual((w, h), (40, 40))
        self.assertTrue(near(at(20, 5), BLUE), at(20, 5))
        self.vision.render(jpg, out, ["cover", 0, 0, 40, 20])
        self.assertTrue(near(pixels(out, self.tmp)[2](20, 10), (128, 128, 128)))

    def test_no_face_stops_and_writes_nothing(self):
        d = make_folder(self)
        Path(d, "profile.md").write_text(PROFILE.format(age="18-59", ed="no", opt="yes"), encoding="utf-8")
        src = Path(self.tmp, "blocks.png")
        src.write_bytes(png(60, 120, lambda x, y: RED if y < 40 else BLUE))
        with self.assertRaisesRegex(ph.Refused, "no face found"):
            ph.file_photos(d, "2030-01-06", {"front": str(src)})
        self.assertFalse(Path(d, "photos").exists())
        made = ph.file_photos(d, "2030-01-06", {"back": str(src)})  # a back view with no head features may pass
        self.assertEqual(made, ["photos/2030-01-06/back.jpg"])
        self.assertEqual(ph.metadata_left(Path(d, made[0]).read_bytes()), [])


if __name__ == "__main__":
    unittest.main()
