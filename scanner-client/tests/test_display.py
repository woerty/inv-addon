"""Bildausgabe: der schnelle Weg muss dasselbe liefern wie der langsame."""
import unittest

import numpy as np
from PIL import Image

from scannerlib.display import to_rgb565_rotated
from scannerlib.theme import Theme


class TestRGB565(unittest.TestCase):
    def referenz(self, im, rot=90):
        """Der langsame, offensichtlich richtige Weg."""
        if rot:
            im = im.transpose(getattr(Image, "ROTATE_%d" % rot))
        a = np.array(im)
        r = (a[:, :, 0].astype(np.uint16) >> 3) << 11
        g = (a[:, :, 1].astype(np.uint16) >> 2) << 5
        b = a[:, :, 2].astype(np.uint16) >> 3
        return (r | g | b).astype(np.uint16).tobytes()

    def bild(self):
        rng = np.random.default_rng(1)
        return Image.fromarray(rng.integers(0, 256, (480, 640, 3), dtype=np.uint8))

    def test_gedreht_ist_byteidentisch_zur_referenz(self):
        im = self.bild()
        self.assertEqual(to_rgb565_rotated(im, 90), self.referenz(im, 90))

    def test_ungedreht_ist_byteidentisch(self):
        im = self.bild()
        self.assertEqual(to_rgb565_rotated(im, 0), self.referenz(im, 0))

    def test_laenge_passt_zum_framebuffer(self):
        im = Image.new("RGB", (640, 480), (1, 2, 3))
        self.assertEqual(len(to_rgb565_rotated(im, 90)), 480 * 640 * 2)

    def test_rueckfall_liefert_dasselbe_wie_der_schnelle_weg(self):
        # Faellt BGR;16 in Pillow 12 weg, muss der numpy-Zweig einspringen.
        im = self.bild()
        schnell = to_rgb565_rotated(im, 90)
        langsam = to_rgb565_rotated(im, 90, _force_fallback=True)
        self.assertEqual(schnell, langsam)


class TestTheme(unittest.TestCase):
    def test_skaliert_vom_entwurf_auf_die_breite(self):
        t = Theme(640)
        self.assertEqual(t.s(20), 40)      # Entwurf 320 -> 640 ist Faktor 2
        self.assertEqual(t.s(48), 96)      # Zeilenhoehe

    def test_schriftstufen_liegen_auf_der_leiter(self):
        t = Theme(640)
        self.assertEqual([t.font_xl.size, t.font_lg.size,
                          t.font_md.size, t.font_sm.size], [56, 40, 32, 26])

    def test_trefferflaechen_regel(self):
        t = Theme(640)
        self.assertGreaterEqual(t.ROW_H, 80)   # Fingerkuppe 90-112 px
        self.assertEqual(t.ROW_H, 96)
