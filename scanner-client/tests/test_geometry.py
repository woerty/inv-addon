"""Trefferflaechen aller Bildschirme.

Diese Pruefung haette C1 (Mengenraster ueber fremden Flaechen) und die zu
kleinen Knoepfe von vornherein verhindert -- von Hand nachgemessen wurde
beides falsch beurteilt.
"""
import unittest

from PIL import Image, ImageDraw

from scannerlib.scanlog import ScanLog
from scannerlib.screens import Screens
from scannerlib.scroll import ScrollView
from scannerlib.theme import Theme

MIN_PX = 80          # Fingerkuppe 90-112 px, Spezifikation: mindestens 80


def _flach(rects):
    """Alle Rechtecke, auch die aus Listen, mit sprechendem Namen."""
    out = []
    for k, v in rects.items():
        if isinstance(v, list):
            out.extend(("%s[%d]" % (k, i), r) for i, r in enumerate(v) if r)
        elif v:
            out.append((k, v))
    return out


def _ueberlappt(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


class Basis(unittest.TestCase):
    def setUp(self):
        self.t = Theme(640)
        self.t.height = 480
        self.s = Screens(self.t)
        self.img = Image.new("RGB", (640, 480))
        self.d = ImageDraw.Draw(self.img)
        self.orte = [{"id": None, "name": "Ohne Ort"}] + [
            {"id": i, "name": "Ort %d" % i} for i in range(1, 10)]

    def _state(self, **kw):
        y0 = self.t.HEADER_H
        log = ScanLog()
        log.add("1", "Milch", "out", at=0.0)
        st = {"mode": "out", "location": None, "status": "Bereit", "multiplier": 1,
              "api_ok": True, "card_bg": None, "selected_id": None,
              "result": {"name": "Milch", "meta": "noch 3", "kind": "ok",
                         "undoable": True},
              "items": self.orte, "scrolling": False, "entries": log.entries,
              "now": 1.0,
              "scroll": ScrollView(view_h=self.t.height - y0,
                                   content_h=len(self.orte) * self.t.ROW_H)}
        st.update(kw)
        return st

    def alle_bildschirme(self):
        for name, zeichnen in (
                ("scan", lambda r: self.s.scan(self.d, self._state(), r)),
                ("scan_in", lambda r: self.s.scan(
                    self.d, self._state(mode="in",
                                        location={"id": 1, "name": "Ort 1"}), r)),
                ("locations", lambda r: self.s.locations(self.d, self._state(), r)),
                ("history", lambda r: self.s.history(self.d, self._state(), r))):
            rects = {}
            zeichnen(rects)
            yield name, rects
        rects = {}
        self.s.scan(self.d, self._state(), rects)
        rects = {}                       # wie render() es fuer MULT macht
        self.s.multiplier_sheet(self.d, rects)
        yield "mult", rects


class TestTrefferflaechen(Basis):
    def test_keine_flaeche_ist_zu_klein(self):
        zu_klein = []
        for name, rects in self.alle_bildschirme():
            for k, r in _flach(rects):
                w, h = r[2] - r[0], r[3] - r[1]
                # Teilweise herausgescrollte Listenzeilen sind ein Nebeneffekt
                # des Scrollens, keine Entwurfsentscheidung -- sie sind unten
                # und oben zwangslaeufig angeschnitten.
                if k.startswith("rows[") and h < self.t.ROW_H:
                    continue
                if min(w, h) < MIN_PX:
                    zu_klein.append("%s.%s %dx%d" % (name, k, w, h))
        self.assertEqual(zu_klein, [], "zu kleine Trefferflaechen: " + ", ".join(zu_klein))

    def test_keine_zwei_flaechen_ueberlappen(self):
        kollisionen = []
        for name, rects in self.alle_bildschirme():
            flach = _flach(rects)
            for i, (ka, ra) in enumerate(flach):
                for kb, rb in flach[i + 1:]:
                    if _ueberlappt(ra, rb):
                        kollisionen.append("%s: %s / %s" % (name, ka, kb))
        self.assertEqual(kollisionen, [], "ueberlappend: " + ", ".join(kollisionen))

    def test_flaechen_liegen_im_bild(self):
        draussen = []
        for name, rects in self.alle_bildschirme():
            for k, r in _flach(rects):
                if r[0] < 0 or r[1] < 0 or r[2] > 640 or r[3] > 480:
                    draussen.append("%s.%s %s" % (name, k, r))
        self.assertEqual(draussen, [])
