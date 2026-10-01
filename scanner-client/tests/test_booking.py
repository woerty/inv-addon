"""Buchen, Gegenbuchung, Multiplikator, Leerlauf-Ruecksprung."""
import unittest

from tests.helpers import FakeAPI, make_app


class TestBuchen(unittest.TestCase):
    def test_einzelbuchung_landet_im_verlauf(self):
        app = make_app(FakeAPI())
        e = app.book("111", count=1)
        self.assertEqual(e.booked, 1)
        self.assertFalse(e.partial)
        self.assertIs(app.log.latest, e)

    def test_achtfach_setzt_acht_aufrufe_ab(self):
        app = make_app(FakeAPI())
        e = app.book("111", count=8)
        self.assertEqual(e.booked, 8)
        self.assertEqual(len(app.api.calls), 8)

    def test_teilerfolg_wird_ehrlich_vermerkt(self):
        # Pruefschwerpunkt 3: der vierte von acht Aufrufen scheitert
        app = make_app(FakeAPI(fail_at=4))
        e = app.book("111", count=8)
        self.assertEqual(e.booked, 3)
        self.assertEqual(e.count, 8)
        self.assertTrue(e.partial)
        self.assertFalse(app.api_ok)

    def test_multiplikator_faellt_auch_bei_abbruch_zurueck(self):
        app = make_app(FakeAPI(fail_at=2), multiplier=8)
        app.book("111", count=app.multiplier)
        self.assertEqual(app.multiplier, 1)

    def test_unbekannter_barcode_kommt_nicht_in_den_verlauf(self):
        class NotFound(FakeAPI):
            def scan_out(self, barcode):
                self.calls.append(("out", barcode))
                return (404, {"status": "not_found", "barcode": barcode})
        app = make_app(NotFound())
        app.book("999", count=1)
        self.assertEqual(app.log.entries, [])
        self.assertEqual(app.last_result["kind"], "warn")


class TestRueckgaengig(unittest.TestCase):
    def test_undo_bucht_gegen(self):
        app = make_app(FakeAPI())
        e = app.book("111", count=1)
        app.undo(e)
        self.assertEqual([c[0] for c in app.api.calls], ["out", "in"])
        self.assertEqual(app.log.entries, [])

    def test_undo_einer_mehrfachmenge_bucht_so_oft_zurueck_wie_gebucht(self):
        app = make_app(FakeAPI())
        e = app.book("111", count=5)
        app.undo(e)
        self.assertEqual(len([c for c in app.api.calls if c[0] == "in"]), 5)

    def test_undo_eines_geloeschten_artikels_meldet_verlorenen_ort(self):
        # Pruefschwerpunkt 2
        app = make_app(FakeAPI(deleted_on_scan_out=True))
        e = app.book("111", count=1)
        app.undo(e)
        self.assertTrue(e.location_lost)
        self.assertIn("Lagerort", app.last_result["meta"])


class TestZustandszeile(unittest.TestCase):
    def test_fehlender_scanner_geht_vor_fehlender_verbindung(self):
        app = make_app(FakeAPI(), scanner_connected=False, api_ok=False)
        self.assertIn("Scanner", app.state_text())

    def test_fehlende_verbindung_wird_gemeldet(self):
        app = make_app(FakeAPI(), api_ok=False)
        self.assertIn("Verbindung", app.state_text())

    def test_normalfall_nennt_den_modus(self):
        self.assertIn("Auslagern", make_app(FakeAPI()).state_text())


class TestLeerlauf(unittest.TestCase):
    def test_ruecksprung_setzt_alles_zurueck(self):
        app = make_app(FakeAPI(), mode="in", multiplier=8,
                       location={"id": 1, "name": "Küche oben"})
        self.assertTrue(app._check_idle(now=601.0))
        self.assertEqual(app.mode, "out")
        self.assertIsNone(app.location)
        self.assertEqual(app.multiplier, 1)

    def test_vor_ablauf_passiert_nichts(self):
        app = make_app(FakeAPI(), mode="in")
        self.assertFalse(app._check_idle(now=599.0))
        self.assertEqual(app.mode, "in")

    def test_abschaltbar(self):
        app = make_app(FakeAPI(), mode="in", idle_reset_s=0)
        self.assertFalse(app._check_idle(now=99999.0))
        self.assertEqual(app.mode, "in")
