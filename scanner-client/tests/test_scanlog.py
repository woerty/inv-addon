"""Verlauf der letzten Scans: Zusammenfassung, Ringpuffer, Ruecknahme."""
import unittest

from scannerlib.scanlog import ScanLog


class TestScanLog(unittest.TestCase):
    def test_leer_am_anfang(self):
        self.assertEqual(ScanLog().entries, [])
        self.assertIsNone(ScanLog().latest)

    def test_gleiche_artikel_direkt_nacheinander_werden_gezaehlt(self):
        log = ScanLog()
        log.add("111", "Milch", "out", at=1.0)
        log.add("111", "Milch", "out", at=2.0)
        self.assertEqual(len(log.entries), 1)
        self.assertEqual(log.entries[0].count, 2)

    def test_dazwischen_ein_anderer_artikel_trennt(self):
        log = ScanLog()
        log.add("111", "Milch", "out", at=1.0)
        log.add("222", "Gouda", "out", at=2.0)
        log.add("111", "Milch", "out", at=3.0)
        self.assertEqual([e.count for e in log.entries], [1, 1, 1])
        self.assertEqual(log.entries[0].barcode, "111")   # neueste zuerst

    def test_andere_richtung_trennt(self):
        log = ScanLog()
        log.add("111", "Milch", "out", at=1.0)
        log.add("111", "Milch", "in", at=2.0)
        self.assertEqual(len(log.entries), 2)

    def test_mehrfachmenge_zaehlt_korrekt(self):
        e = ScanLog().add("111", "Milch", "out", count=8, at=1.0)
        self.assertEqual(e.count, 8)
        self.assertEqual(e.booked, 8)
        self.assertFalse(e.partial)

    def test_teilbuchung_wird_nicht_zusammengefasst(self):
        # Pruefschwerpunkt 3: ein abgebrochener Eintrag darf nicht stillschweigend
        # mit dem naechsten verschmelzen -- sonst geht die Teilmenge verloren.
        log = ScanLog()
        log.add("111", "Milch", "out", count=8, booked=3, at=1.0)
        log.add("111", "Milch", "out", count=1, at=2.0)
        self.assertEqual(len(log.entries), 2)
        self.assertTrue(log.entries[1].partial)

    def test_ringpuffer_laeuft_ueber(self):
        log = ScanLog(limit=3)
        for i in range(5):
            log.add(str(i), "Artikel %d" % i, "out", at=float(i))
        self.assertEqual(len(log.entries), 3)
        self.assertEqual(log.entries[0].barcode, "4")

    def test_entfernen_nimmt_den_eintrag_raus(self):
        log = ScanLog()
        e = log.add("111", "Milch", "out", at=1.0)
        log.remove(e)
        self.assertEqual(log.entries, [])

    def test_entfernen_eines_fremden_eintrags_schadet_nicht(self):
        log = ScanLog()
        e = log.add("111", "Milch", "out", at=1.0)
        log.remove(e)
        log.remove(e)                      # zweimal zuruecknehmen
        self.assertEqual(log.entries, [])
