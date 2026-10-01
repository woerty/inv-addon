"""Scroll-Physik: reine Mathematik, deshalb ohne Geraet pruefbar."""
import unittest

from scannerlib.scroll import ScrollView


class TestScrollView(unittest.TestCase):
    def sv(self, content=960, view=348):
        return ScrollView(view_h=view, content_h=content)

    def test_offset_startet_bei_null(self):
        self.assertEqual(self.sv().offset, 0)

    def test_max_offset_ist_inhalt_minus_sicht(self):
        self.assertEqual(self.sv().max_offset, 960 - 348)

    def test_kurze_liste_laesst_sich_nicht_scrollen(self):
        # Pruefschwerpunkt 1: API war beim Start weg, nur "Ohne Ort" in der Liste
        s = self.sv(content=96, view=348)
        self.assertEqual(s.max_offset, 0)
        s.on_down(300); s.on_move(100); s.on_up()
        for _ in range(60):
            s.advance(1 / 30)
        self.assertEqual(s.offset, 0)

    def test_tipp_unter_schwelle_scrollt_nicht(self):
        s = self.sv()
        s.on_down(200)
        self.assertFalse(s.on_move(190))
        self.assertEqual(s.offset, 0)
        s.on_up()
        self.assertFalse(s.was_drag)

    def test_wisch_ueber_schwelle_scrollt(self):
        s = self.sv()
        s.on_down(300)
        self.assertTrue(s.on_move(200))
        self.assertGreater(s.offset, 0)
        s.on_up()
        self.assertTrue(s.was_drag)

    def test_ueberziehen_wird_gedaempft(self):
        s = self.sv()
        s.on_down(100); s.on_move(400)
        self.assertLess(s.visual_offset, 0)
        self.assertGreater(s.visual_offset, -s.damp)

    def test_feder_kehrt_zum_rand_zurueck(self):
        s = self.sv()
        s.on_down(100); s.on_move(400); s.on_up()
        for _ in range(120):
            s.advance(1 / 30)
        self.assertEqual(s.offset, 0)
        self.assertFalse(s.advance(1 / 30))

    def test_gleiten_klingt_ab_und_endet(self):
        s = self.sv()
        s.on_down(400, now=0.00)
        for i, y in enumerate((350, 300, 250, 200), start=1):
            s.on_move(y, now=i * 0.02)
        s.on_up(now=0.08)
        self.assertTrue(s.advance(1 / 30))
        for _ in range(300):
            if not s.advance(1 / 30):
                break
        else:
            self.fail("Gleiten endet nicht")
        self.assertLessEqual(s.offset, s.max_offset)
        self.assertGreaterEqual(s.offset, 0)

    def test_beruehrung_stoppt_das_gleiten(self):
        # Pruefschwerpunkt 4: Finger faesst in die gleitende Liste
        s = self.sv()
        s.on_down(400, now=0.00)
        for i, y in enumerate((350, 300, 250, 200), start=1):
            s.on_move(y, now=i * 0.02)
        s.on_up(now=0.08)
        s.advance(1 / 30)
        bewegt = s.offset
        s.on_down(200, now=0.20)
        self.assertEqual(s.velocity, 0)
        self.assertEqual(s.offset, bewegt)

    def test_inhaltshoehe_nachtraeglich_setzen_klemmt_offset(self):
        s = self.sv()
        s.offset = 600.0
        s.set_content_h(192)          # Liste wurde kuerzer
        self.assertEqual(s.offset, 0)
