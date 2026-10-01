"""Buchen darf die Bildschleife nicht anhalten.

Ohne das friert das Display bei x12 auf eine lahme Verbindung minutenlang
ein -- und der Fortschrittsring der Spezifikation ist gar nicht erst
darstellbar, weil zwischen den Aufrufen nie gezeichnet wird.
"""
import threading
import time
import unittest

from tests.helpers import FakeAPI, make_app


class LangsameAPI(FakeAPI):
    def __init__(self, verzoegerung=0.05, **kw):
        super().__init__(**kw)
        self.verzoegerung = verzoegerung

    def scan_out(self, barcode):
        time.sleep(self.verzoegerung)
        return super().scan_out(barcode)


class TestNebenlaeufigesBuchen(unittest.TestCase):
    def _warte(self, app, timeout=5.0):
        ende = time.time() + timeout
        while app.booking and time.time() < ende:
            time.sleep(0.005)

    def test_handle_barcode_kehrt_sofort_zurueck(self):
        app = make_app(LangsameAPI(verzoegerung=0.08), multiplier=4)
        t0 = time.perf_counter()
        app.handle_barcode("111")
        dauer = time.perf_counter() - t0
        self.assertLess(dauer, 0.05, "handle_barcode hat %.0f ms blockiert" % (dauer*1000))
        self._warte(app)
        self.assertEqual(app.log.latest.booked, 4)

    def test_fortschritt_ist_waehrenddessen_ablesbar(self):
        app = make_app(LangsameAPI(verzoegerung=0.05), multiplier=5)
        app.handle_barcode("111")
        gesehen = set()
        ende = time.time() + 3.0
        while app.booking and time.time() < ende:
            p = app.progress
            if p:
                gesehen.add(p)
            time.sleep(0.005)
        self._warte(app)
        self.assertTrue(gesehen, "waehrend des Buchens war kein Fortschritt ablesbar")
        self.assertTrue(all(g[1] == 5 for g in gesehen))
        self.assertLessEqual(max(g[0] for g in gesehen), 5)

    def test_schleife_animiert_waehrend_gebucht_wird(self):
        app = make_app(LangsameAPI(verzoegerung=0.05), multiplier=3)
        app.handle_barcode("111")
        self.assertTrue(app._advance(0.03, time.monotonic()),
                        "_advance meldet keine Bewegung, also wird nicht gezeichnet")
        self._warte(app)
        self.assertFalse(app._advance(0.03, time.monotonic()))

    def test_zweiter_scan_waehrend_einer_buchung_wird_ignoriert(self):
        app = make_app(LangsameAPI(verzoegerung=0.08), multiplier=3)
        app.handle_barcode("111")
        app.handle_barcode("222")
        self._warte(app)
        self.assertTrue(all(c[1] == "111" for c in app.api.calls),
                        "der zweite Scan hat sich dazwischengedraengt")

    def test_fortschritt_ist_nach_abschluss_weg(self):
        app = make_app(LangsameAPI(verzoegerung=0.02), multiplier=2)
        app.handle_barcode("111")
        self._warte(app)
        self.assertIsNone(app.progress)
        self.assertFalse(app.busy)
