"""Fehlerfaelle, die stillschweigend falsche Daten erzeugen oder den
Prozess beenden."""
import unittest

from scannerlib.api import API
from tests.helpers import FakeAPI, make_app


class FakeResponse:
    def __init__(self, status, payload=None, raise_json=False):
        self.status_code = status
        self._payload = payload
        self._raise = raise_json

    def json(self):
        if self._raise:
            raise ValueError("kein JSON")
        return self._payload


class TestKeinDoppelbuchen(unittest.TestCase):
    """scan-in ist nicht idempotent. Eine Wiederholung nach einer bereits
    verarbeiteten Anfrage bucht ein zweites Mal."""

    def test_unlesbare_antwort_wird_nicht_wiederholt(self):
        aufrufe = []

        def methode(url, **kw):
            aufrufe.append(url)
            return FakeResponse(200, raise_json=True)

        api = API("http://x/api")
        status, data = api._retry_request(methode, "http://x/api/inventory/scan-in")
        self.assertEqual(len(aufrufe), 1, "bei unlesbarem JSON wurde wiederholt")
        self.assertEqual(status, 200)

    def test_serverfehler_wird_weiterhin_wiederholt(self):
        aufrufe = []

        def methode(url, **kw):
            aufrufe.append(url)
            return FakeResponse(500, {"detail": "kaputt"})

        API("http://x/api")._retry_request(methode, "http://x/api/y")
        self.assertEqual(len(aufrufe), 3)


class TestLeereLagerortliste(unittest.TestCase):
    def test_leere_liste_ist_kein_verbindungsfehler(self):
        class Leer(FakeAPI):
            def get_locations(self):
                return []
        app = make_app(Leer(), api_ok=False)
        app._refresh_locations()
        self.assertTrue(app.api_ok, "eine leere Liste wurde als Ausfall gewertet")
        self.assertEqual(app.locations, [])

    def test_ausfall_bleibt_ein_ausfall(self):
        class Weg(FakeAPI):
            def get_locations(self):
                return None
        app = make_app(Weg())
        app._refresh_locations()
        self.assertFalse(app.api_ok)

    def test_bei_leerer_liste_wird_nicht_endlos_nachgefragt(self):
        class Leer(FakeAPI):
            def __init__(self):
                super().__init__()
                self.abrufe = 0

            def get_locations(self):
                self.abrufe += 1
                return []
        app = make_app(Leer())
        app._refresh_locations()
        vorher = app.api.abrufe
        app._last_location_fetch = 0.0
        app._maybe_retry_locations()
        self.assertEqual(app.api.abrufe, vorher,
                         "eine bestaetigt leere Liste wird weiter abgefragt")


class TestStartmodus(unittest.TestCase):
    def test_einlagern_ohne_ort_fuehrt_in_die_ortswahl(self):
        app = make_app(FakeAPI(), mode="out")
        app.cfg = {"start_mode": "in"}
        app.locations = [{"id": 1, "name": "Ort 1"}]
        app._apply_start_mode()
        self.assertEqual(app.mode, "in")
        self.assertEqual(app.screen, "locations",
                         "ohne Ort wuerde ein Scan still auf 'Ohne Ort' buchen")


class TestSchleifeUeberlebtFehler(unittest.TestCase):
    def test_ein_fehler_beim_behandeln_beendet_nicht_den_prozess(self):
        app = make_app(FakeAPI())

        def kaputt(*a, **kw):
            raise RuntimeError("unerwartet")
        app.handle_touch = kaputt
        app._safe_handle(("touch_up", 10, 10))      # darf nicht durchschlagen
        self.assertIsNotNone(app.last_result)
        self.assertEqual(app.last_result["kind"], "err")
