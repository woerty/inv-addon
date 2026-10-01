"""Verlauf muss scrollen, sonst sind 17 von 20 Eintraegen unerreichbar."""
import unittest

from PIL import Image, ImageDraw

from scannerlib.screens import Screens
from scannerlib.scroll import ScrollView
from scannerlib.theme import Theme
from tests.helpers import FakeAPI, make_app


class TestVerlaufScrollt(unittest.TestCase):
    def setUp(self):
        self.t = Theme(640)
        self.t.height = 480
        self.s = Screens(self.t)
        self.d = ImageDraw.Draw(Image.new("RGB", (640, 480)))

    def _eintraege(self, n):
        app = make_app(FakeAPI())
        for i in range(n):
            app.log.add(str(i), "Artikel %d" % i, "out", at=float(i))
        return app.log.entries

    def test_ohne_scrollen_waeren_die_meisten_unerreichbar(self):
        sichtbar = (self.t.height - self.t.HEADER_H) // self.t.ROW_H
        self.assertLess(sichtbar, 20, "Annahme der Pruefung stimmt nicht mehr")

    def test_letzter_eintrag_ist_durch_scrollen_erreichbar(self):
        eintraege = self._eintraege(20)
        y0 = self.t.HEADER_H
        sv = ScrollView(view_h=self.t.height - y0,
                        content_h=len(eintraege) * self.t.ROW_H)
        sv.offset = sv.max_offset               # ganz nach unten
        rects = {}
        self.s.history(self.d, {"mode": "out", "entries": eintraege, "now": 100.0,
                                "api_ok": True, "scroll": sv, "scrolling": False}, rects)
        self.assertIsNotNone(rects["hrows"][len(eintraege) - 1],
                             "der aelteste Eintrag bleibt unerreichbar")

    def test_oben_ist_der_neueste_sichtbar(self):
        eintraege = self._eintraege(20)
        y0 = self.t.HEADER_H
        sv = ScrollView(view_h=self.t.height - y0,
                        content_h=len(eintraege) * self.t.ROW_H)
        rects = {}
        self.s.history(self.d, {"mode": "out", "entries": eintraege, "now": 100.0,
                                "api_ok": True, "scroll": sv, "scrolling": False}, rects)
        self.assertIsNotNone(rects["hrows"][0])

    def test_kurzer_verlauf_scrollt_nicht(self):
        eintraege = self._eintraege(2)
        y0 = self.t.HEADER_H
        sv = ScrollView(view_h=self.t.height - y0,
                        content_h=len(eintraege) * self.t.ROW_H)
        self.assertEqual(sv.max_offset, 0)


class TestGetrennteScrollstaende(unittest.TestCase):
    def test_lagerort_und_verlauf_merken_sich_getrennt(self):
        # Das Doppel muss genug Orte liefern, sonst ist die Liste kuerzer als
        # das Sichtfenster und das Klemmen auf 0 waere korrekt.
        class VieleOrte(FakeAPI):
            def get_locations(self):
                return [{"id": i, "name": "Ort %d" % i} for i in range(1, 10)]
        app = make_app(VieleOrte())
        app.locations = VieleOrte().get_locations()
        for i in range(20):
            app.log.add(str(i), "A%d" % i, "out", at=float(i))
        app._open_locations()
        app.scroll_loc.offset = 200.0
        app._open_history()
        app.scroll_hist.offset = 400.0
        app._open_locations()
        self.assertEqual(app.scroll_loc.offset, 200.0)
        self.assertEqual(app.scroll_hist.offset, 400.0)
