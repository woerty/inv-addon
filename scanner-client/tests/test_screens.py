"""Zeichenhelfer der Bildschirme."""
import unittest

from PIL import Image, ImageDraw

from scannerlib.screens import ellipsize
from scannerlib.theme import Theme


class TestKuerzen(unittest.TestCase):
    def setUp(self):
        self.t = Theme(640)
        self.d = ImageDraw.Draw(Image.new("RGB", (640, 480)))

    def test_langer_name_wird_gekuerzt_nicht_umgebrochen(self):
        # Pruefschwerpunkt 5: eine zweite Zeile sprengt die Kartenhoehe
        name = "Bio-Vollmilch frisch laenger haltbar 3,5 Prozent Fett 1 Liter"
        g = ellipsize(self.d, name, self.t.font_md, max_px=390)
        self.assertLess(len(g), len(name))
        self.assertTrue(g.endswith("…"))
        self.assertNotIn("\n", g)
        self.assertLessEqual(self.d.textlength(g, font=self.t.font_md), 390)

    def test_kurzer_name_bleibt_unveraendert(self):
        self.assertEqual(ellipsize(self.d, "Obst", self.t.font_md, 390), "Obst")

    def test_sehr_schmale_breite_liefert_trotzdem_etwas_kurzes(self):
        g = ellipsize(self.d, "Vitrinenschrank", self.t.font_md, max_px=10)
        self.assertLessEqual(len(g), 2)
        self.assertNotIn("\n", g)
