# Scanner-UI Neugestaltung — Umsetzungsplan

> **Für agentische Bearbeiter:** ERFORDERLICHE UNTER-SKILL: `superpowers:subagent-driven-development`
> (empfohlen) oder `superpowers:executing-plans`, um diesen Plan Aufgabe für Aufgabe
> umzusetzen. Schritte benutzen Kästchen (`- [ ]`) zur Verfolgung.

**Ziel:** Die Oberfläche des Barcode-Terminals auf das 640×480-Panel neu bauen — mit
Bildschleife, Momentum-Scrollen, Rückgängig, Verlauf, ×N-Multiplikator und Rücksprung
nach Leerlauf.

**Architektur:** Die blockierende Ereignisschleife wird zur Bildschleife mit 30 fps, die
nur zeichnet, solange etwas in Bewegung ist. Die heutige Einzeldatei `scanner.py` wird zu
einem schlanken Einstiegspunkt plus Paket `scannerlib/`, damit Scroll-Physik und
Scan-Protokoll ohne Display testbar sind.

**Technik:** Python 3.13, PIL (Pillow 11.1.0), numpy 2.2.4, evdev, requests — alles bereits
auf dem Gerät. Tests mit `unittest` aus der Standardbibliothek; **kein pytest** (nicht
installiert, und eine neue Abhängigkeit lohnt für zwei Testdateien nicht).

**Spec:** `docs/superpowers/specs/2026-10-01-scanner-ui-redesign-design.md`

## Globale Randbedingungen

Aus der Spezifikation, wörtlich. Sie gelten für **jede** Aufgabe:

- Bildschirm **640 × 480** quer; Framebuffer `/dev/fb0` ist **480 × 640** hochkant,
  16 bit. Gezeichnet wird quer, gedreht wird erst beim Schreiben.
- Trefferflächen **mindestens 80 px**, Listenzeilen **96 px**.
- Schriftleiter **56 / 40 / 32 / 26 px**. Symbole dürfen davon abweichen: ×N 36, ☰ 30,
  ← 28, ✓ 22. Jede andere Textgröße unter 32 px braucht eine Begründung.
- Farben nur aus der Palette der Spezifikation, Abschnitt *Farben*.
- Grundabstand 8 px, Ränder 16 px, Eckenradius 12 px (Karten) bzw. 8 px (Knöpfe).
- Bildrate **30 fps** während Animationen, **kein Zeichnen im Ruhezustand**.
- Touch-Umrechnung bleibt wie heute: normieren, `touch_swap_xy`, `touch_flip_x`.
- Die API wird **nicht** geändert. Mengen und Rücknahmen entstehen durch wiederholte
  bzw. gegenläufige Aufrufe.
- Zielgerät: `dstn@scanner.local`, `sudo` ohne Passwort, Dienst `scanner.service`.

## Prüfschwerpunkte

Fälle, die die Spezifikation voraussetzt, die aber leicht durchrutschen. Jede Zeile
bekommt ihren Test in der Aufgabe, der der Code gehört:

1. **Leere Lagerortliste** — die API war beim Start nicht erreichbar. Die Liste enthält
   dann nur „Ohne Ort", `maxOff()` ist 0, und Scrollen darf weder federn noch rechnen
   (Division durch die Inhaltshöhe). → Aufgabe 2.
2. **Rückgängig eines gelöschten Artikels** — war es das letzte Exemplar, legt die
   Gegenbuchung ihn neu an und der Lagerort fehlt. Das muss angezeigt werden, nicht
   stillschweigend passieren. → Aufgabe 8.
3. **×N bricht in der Mitte ab** — nach n von N Aufrufen schlägt einer fehl. Der
   Verlaufseintrag muss die **tatsächlich** gebuchte Menge tragen, nicht N. → Aufgabe 8.
4. **Berührung während einer laufenden Animation** — der Finger fasst in eine gleitende
   Liste. Der Schwung muss sofort enden und das Ziehen ohne Sprung übernehmen. → Aufgabe 2.
5. **Produktname länger als die Karte** — muss gekürzt werden, nie umbrechen; eine zweite
   Zeile sprengt die Kartenhöhe. → Aufgabe 6.

---

## Aufgabe 1: Paketstruktur, ohne Verhaltensänderung

Reiner Umzug. Am Ende läuft dasselbe wie vorher, nur in Modulen. Das zuerst, weil jede
folgende Aufgabe sonst in einer 900-Zeilen-Datei editiert.

**Dateien:**
- Anlegen: `scannerlib/__init__.py`, `config.py`, `api.py`, `display.py`, `inputs.py`
- Ändern: `scanner.py` → schlanker Einstiegspunkt
- Sichern: `scanner.py` → `scanner.py.vor-ui` auf dem Gerät

**Schnittstellen:**
- Liefert: `scannerlib.config.load_config() -> dict`,
  `scannerlib.api.API(base_url, token)`,
  `scannerlib.display.Display(fb_device, width, height, backlight_path, timeout, rotate)`,
  `scannerlib.inputs.barcode_reader(path, q)`, `scannerlib.inputs.touch_reader(path, q, cfg)`

- [ ] **Schritt 1: Verzeichnis anlegen und Bestand sichern**

```bash
ssh dstn@scanner.local 'cp ~/scanner.py ~/scanner.py.vor-ui && mkdir -p ~/scannerlib ~/tests && touch ~/scannerlib/__init__.py'
```

- [ ] **Schritt 2: Module herausschneiden**

`config.py` bekommt `DEFAULT_CONFIG` und `load_config`. `api.py` die Klasse `API`.
`display.py` die Klasse `Display`. `inputs.py` die Funktionen `barcode_reader` und
`touch_reader` samt `SCANCODES`. Jede Datei nur mit den Importen, die sie braucht.

- [ ] **Schritt 3: `scanner.py` auf den Einstiegspunkt eindampfen**

```python
#!/usr/bin/env python3
"""Barcode-Scanner-Client. Die Logik liegt in scannerlib/."""
import sys
from scannerlib.config import load_config
from scannerlib.app import App

def main():
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except (AttributeError, OSError):
        pass
    App(load_config()).run()

if __name__ == "__main__":
    main()
```

- [ ] **Schritt 4: Prüfen, dass nichts kaputtging**

```bash
ssh dstn@scanner.local 'python3 -c "import scannerlib.config, scannerlib.api, scannerlib.display, scannerlib.inputs; print(\"Importe ok\")"
sudo systemctl restart scanner && sleep 4 && systemctl is-active scanner'
```
Erwartet: `Importe ok`, danach `active`. Display zeigt unverändert den alten Scan-Bildschirm.

- [ ] **Schritt 5: Festhalten**

```bash
git add -A && git commit -m "refactor(scanner): Logik in scannerlib/ aufteilen"
```

---

## Aufgabe 2: ScrollView — die Scroll-Physik

Reine Mathematik, keine Ein-/Ausgabe. Testgetrieben, weil man Scrollgefühl sonst nur
erfühlt statt prüft.

**Dateien:**
- Anlegen: `scannerlib/scroll.py`, `tests/test_scroll.py`

**Schnittstellen:**
- Liefert: `ScrollView(view_h: int, content_h: int, friction=3.0, spring=12.0, damp=None, drag_threshold=25)`
  mit `offset: float`, `on_down(y)`, `on_move(y) -> bool`, `on_up()`,
  `advance(dt: float) -> bool`, `visual_offset: float`, `is_dragging: bool`,
  `was_drag: bool`, `set_content_h(h)`

- [ ] **Schritt 1: Fehlschlagende Tests schreiben**

```python
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
        # Pruefschwerpunkt 1: leere Lagerortliste, nur "Ohne Ort"
        s = self.sv(content=96, view=348)
        self.assertEqual(s.max_offset, 0)
        s.on_down(300); s.on_move(100); s.on_up()
        for _ in range(60):
            s.advance(1/30)
        self.assertEqual(s.offset, 0)

    def test_tipp_unter_schwelle_scrollt_nicht(self):
        s = self.sv()
        s.on_down(200)
        self.assertFalse(s.on_move(190))      # 10 px, unter 25
        self.assertEqual(s.offset, 0)
        s.on_up()
        self.assertFalse(s.was_drag)

    def test_wisch_ueber_schwelle_scrollt(self):
        s = self.sv()
        s.on_down(300)
        self.assertTrue(s.on_move(200))       # 100 px
        self.assertGreater(s.offset, 0)
        s.on_up()
        self.assertTrue(s.was_drag)

    def test_ueberziehen_wird_gedaempft(self):
        s = self.sv()
        s.on_down(100); s.on_move(400)        # weit ueber den oberen Rand
        self.assertLess(s.visual_offset, 0)           # sichtbar ueberzogen
        self.assertGreater(s.visual_offset, -s.damp)  # aber nie weiter als die Daempfungsweite

    def test_feder_kehrt_zum_rand_zurueck(self):
        s = self.sv()
        s.on_down(100); s.on_move(400); s.on_up()
        for _ in range(120):
            s.advance(1/30)
        self.assertEqual(s.offset, 0)
        self.assertFalse(s.advance(1/30))     # nichts mehr in Bewegung

    def test_gleiten_klingt_ab_und_endet(self):
        s = self.sv()
        s.on_down(400)
        for y in (350, 300, 250, 200):
            s.on_move(y)
        s.on_up()
        self.assertTrue(s.advance(1/30))      # bewegt sich
        for _ in range(300):
            if not s.advance(1/30):
                break
        else:
            self.fail("Gleiten endet nicht")
        self.assertLessEqual(s.offset, s.max_offset)
        self.assertGreaterEqual(s.offset, 0)

    def test_beruehrung_stoppt_das_gleiten(self):
        # Pruefschwerpunkt 4: Finger faesst in die gleitende Liste
        s = self.sv()
        s.on_down(400)
        for y in (350, 300, 250, 200):
            s.on_move(y)
        s.on_up()
        s.advance(1/30)
        bewegt = s.offset
        s.on_down(200)
        self.assertEqual(s.velocity, 0)
        self.assertEqual(s.offset, bewegt)    # kein Sprung
```

- [ ] **Schritt 2: Tests laufen lassen, Fehlschlag bestätigen**

```bash
ssh dstn@scanner.local 'cd ~ && python3 -m unittest tests.test_scroll -v'
```
Erwartet: `ModuleNotFoundError: No module named 'scannerlib.scroll'`

- [ ] **Schritt 3: `scannerlib/scroll.py` schreiben**

```python
"""Scroll-Physik: Momentum und Rubberbanding, ohne Ein-/Ausgabe.

Alle Konstanten sind benannt, weil sie am echten Geraet nachjustiert werden.
"""
import math


class ScrollView:
    def __init__(self, view_h, content_h, friction=3.0, spring=12.0,
                 damp=None, drag_threshold=25, min_velocity=20.0):
        self.view_h = view_h
        self.content_h = content_h
        self.friction = friction          # 1/s, Abklingen des Schwungs
        self.spring = spring              # 1/s, Haerte der Randfeder
        self.damp = damp if damp is not None else view_h
        self.drag_threshold = drag_threshold
        self.min_velocity = min_velocity

        self.offset = 0.0
        self.velocity = 0.0
        self.is_dragging = False
        self.was_drag = False
        self._y0 = 0.0
        self._off0 = 0.0
        self._started = False
        self._samples = []

    @property
    def max_offset(self):
        return max(0, self.content_h - self.view_h)

    def set_content_h(self, h):
        self.content_h = h
        self.offset = max(0, min(self.offset, self.max_offset))

    def _damped(self, over):
        """Je weiter ueber den Rand, desto zaeher. Nie weiter als damp."""
        d = self.damp
        return d * (1 - 1 / (over / d + 1))

    @property
    def visual_offset(self):
        if self.offset < 0:
            return -self._damped(-self.offset)
        m = self.max_offset
        if self.offset > m:
            return m + self._damped(self.offset - m)
        return self.offset

    def on_down(self, y, now=0.0):
        self.is_dragging = True
        self._started = False
        self.was_drag = False
        self._y0 = y
        self._off0 = self.offset
        self.velocity = 0.0          # Beruehrung stoppt das Gleiten sofort
        self._samples = [(y, now)]

    def on_move(self, y, now=0.0):
        """True, wenn sich der Inhalt bewegt hat."""
        if not self.is_dragging or self.max_offset <= 0:
            return False
        dy = self._y0 - y
        if not self._started:
            if abs(dy) < self.drag_threshold:
                return False
            self._started = True
            self._y0 = y
            self._off0 = self.offset
            dy = 0
        self.offset = self._off0 + dy
        self._samples.append((y, now))
        while len(self._samples) > 2 and now - self._samples[0][1] > 0.1:
            self._samples.pop(0)
        return True

    def on_up(self, now=0.0):
        if not self.is_dragging:
            return
        self.is_dragging = False
        self.was_drag = self._started
        if self._started and len(self._samples) > 1:
            (ya, ta), (yb, tb) = self._samples[0], self._samples[-1]
            dt = tb - ta
            self.velocity = (ya - yb) / dt if dt > 0.004 else 0.0
            self.velocity = max(-4000.0, min(4000.0, self.velocity))
        self.offset = self.visual_offset

    def advance(self, dt):
        """Einen Zeitschritt weiter. True, solange etwas in Bewegung ist."""
        if self.is_dragging or self.max_offset <= 0:
            return False
        m = self.max_offset
        moving = False

        if abs(self.velocity) > self.min_velocity:
            self.offset += self.velocity * dt
            self.velocity *= math.exp(-self.friction * dt)
            moving = True
            if self.offset < 0 or self.offset > m:
                self.offset = max(-self.damp, min(m + self.damp, self.offset))
                self.velocity *= 0.5
        else:
            self.velocity = 0.0

        target = 0 if self.offset < 0 else (m if self.offset > m else None)
        if target is not None:
            self.offset += (target - self.offset) * (1 - math.exp(-self.spring * dt))
            if abs(target - self.offset) < 0.5:
                self.offset = float(target)
                self.velocity = 0.0
            else:
                moving = True
        return moving
```

- [ ] **Schritt 4: Tests laufen lassen, Erfolg bestätigen**

```bash
ssh dstn@scanner.local 'cd ~ && python3 -m unittest tests.test_scroll -v'
```
Erwartet: alle Tests PASS.

- [ ] **Schritt 5: Festhalten**

```bash
git add scannerlib/scroll.py tests/test_scroll.py
git commit -m "feat(scanner): Scroll-Physik mit Momentum und Rubberbanding"
```

---

## Aufgabe 3: ScanLog — Verlauf und Zusammenfassung

**Dateien:**
- Anlegen: `scannerlib/scanlog.py`, `tests/test_scanlog.py`

**Schnittstellen:**
- Liefert: `ScanEntry(barcode, name, mode, count, at, booked, location_lost=False)`,
  `ScanLog(limit=20)` mit `add(barcode, name, mode, count=1, at=None) -> ScanEntry`,
  `entries -> list[ScanEntry]` (neueste zuerst), `remove(entry)`, `latest`

- [ ] **Schritt 1: Fehlschlagende Tests schreiben**

```python
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
        log = ScanLog()
        e = log.add("111", "Milch", "out", count=8, at=1.0)
        self.assertEqual(e.count, 8)

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
```

- [ ] **Schritt 2: Tests laufen lassen, Fehlschlag bestätigen**

```bash
ssh dstn@scanner.local 'cd ~ && python3 -m unittest tests.test_scanlog -v'
```
Erwartet: `ModuleNotFoundError: No module named 'scannerlib.scanlog'`

- [ ] **Schritt 3: `scannerlib/scanlog.py` schreiben**

```python
"""Verlauf der letzten Scans, mit Zusammenfassung gleicher Artikel."""
import time
from dataclasses import dataclass, field


@dataclass
class ScanEntry:
    barcode: str
    name: str
    mode: str            # "out" oder "in"
    count: int = 1
    at: float = field(default_factory=time.monotonic)
    booked: int = 0      # tatsaechlich gebucht; kann bei Abbruch < count sein
    location_lost: bool = False

    @property
    def partial(self):
        return self.booked < self.count


class ScanLog:
    def __init__(self, limit=20):
        self.limit = limit
        self._entries = []          # aelteste zuerst

    @property
    def entries(self):
        return list(reversed(self._entries))

    @property
    def latest(self):
        return self._entries[-1] if self._entries else None

    def add(self, barcode, name, mode, count=1, at=None, booked=None):
        at = time.monotonic() if at is None else at
        booked = count if booked is None else booked
        last = self._entries[-1] if self._entries else None
        # Nur direkt aufeinanderfolgende, gleiche Scans zusammenfassen --
        # sonst verfaelscht ein dazwischenliegender Scan die Reihenfolge.
        if last is not None and last.barcode == barcode and last.mode == mode \
                and not last.partial:
            last.count += count
            last.booked += booked
            last.at = at
            return last
        entry = ScanEntry(barcode, name, mode, count, at, booked)
        self._entries.append(entry)
        if len(self._entries) > self.limit:
            self._entries.pop(0)
        return entry

    def remove(self, entry):
        if entry in self._entries:
            self._entries.remove(entry)
```

- [ ] **Schritt 4: Tests laufen lassen, Erfolg bestätigen**

```bash
ssh dstn@scanner.local 'cd ~ && python3 -m unittest tests.test_scanlog -v'
```
Erwartet: alle PASS.

- [ ] **Schritt 5: Festhalten**

```bash
git add scannerlib/scanlog.py tests/test_scanlog.py
git commit -m "feat(scanner): Verlauf der letzten Scans mit Zusammenfassung"
```

---

## Aufgabe 4: Theme und schnelle Bildausgabe

**Dateien:**
- Anlegen: `scannerlib/theme.py`
- Ändern: `scannerlib/display.py`
- Anlegen: `tests/test_display.py`

**Schnittstellen:**
- Liefert: `Theme(width)` mit `.s(v)` (logisch → Pixel), `.font_xl/.lg/.md/.sm`,
  `.icon(size)`, Farben als Großbuchstaben-Attribute
- Liefert: `Display.to_rgb565(img) -> bytes` (statisch, prüfbar ohne Gerät)

- [ ] **Schritt 1: Fehlschlagenden Test schreiben**

```python
import unittest
import numpy as np
from PIL import Image
from scannerlib.display import to_rgb565_rotated

class TestRGB565(unittest.TestCase):
    def referenz(self, im):
        a = np.array(im.transpose(Image.ROTATE_90))
        r = (a[:, :, 0].astype(np.uint16) >> 3) << 11
        g = (a[:, :, 1].astype(np.uint16) >> 2) << 5
        b = a[:, :, 2].astype(np.uint16) >> 3
        return (r | g | b).astype(np.uint16).tobytes()

    def test_schneller_weg_ist_byteidentisch(self):
        rng = np.random.default_rng(1)
        im = Image.fromarray(rng.integers(0, 256, (480, 640, 3), dtype=np.uint8))
        self.assertEqual(to_rgb565_rotated(im, 90), self.referenz(im))

    def test_laenge_passt_zum_framebuffer(self):
        im = Image.new("RGB", (640, 480), (1, 2, 3))
        self.assertEqual(len(to_rgb565_rotated(im, 90)), 480 * 640 * 2)
```

- [ ] **Schritt 2: Test laufen lassen, Fehlschlag bestätigen**

```bash
ssh dstn@scanner.local 'cd ~ && python3 -m unittest tests.test_display -v'
```
Erwartet: `ImportError: cannot import name 'to_rgb565_rotated'`

- [ ] **Schritt 3: In `display.py` einbauen**

```python
def to_rgb565_rotated(img, rotate):
    """Querbild -> Bytes fuer den hochkanten Framebuffer.

    Gemessen auf dem Pi 3A+: der PIL-Weg kostet 8,3 ms, der numpy-Weg 15,4 ms.
    Beide liefern dieselben Bytes. BGR;16 ist in Pillow als veraltet markiert
    und soll in Version 12 entfallen -- faellt es weg, wird es langsamer,
    nicht kaputt.
    """
    try:
        buf = np.frombuffer(img.convert("BGR;16").tobytes(), dtype=np.uint16)
        buf = buf.reshape(img.height, img.width)
    except (ValueError, KeyError, OSError):
        a = np.asarray(img)
        r = (a[:, :, 0].astype(np.uint16) >> 3) << 11
        g = (a[:, :, 1].astype(np.uint16) >> 2) << 5
        b = a[:, :, 2].astype(np.uint16) >> 3
        buf = r | g | b
    if rotate == 90:
        buf = np.rot90(buf)
    elif rotate == 180:
        buf = np.rot90(buf, 2)
    elif rotate == 270:
        buf = np.rot90(buf, 3)
    return np.ascontiguousarray(buf).tobytes()
```

`Display.flush` ruft das auf und schreibt in einen **offen gehaltenen** Dateizeiger
(`open(fb, "wb", buffering=0)` einmal im Konstruktor, `seek(0)` vor jedem Schreiben),
statt die Datei pro Bild zu öffnen.

- [ ] **Schritt 4: `scannerlib/theme.py` anlegen**

Farben und Schriftstufen wörtlich aus der Spezifikation, Abschnitte *Farben* und *Schrift*.
`Theme.s(v)` skaliert von der Entwurfsbreite 320 auf die tatsächliche Breite.

- [ ] **Schritt 5: Tests laufen lassen, Erfolg bestätigen**

```bash
ssh dstn@scanner.local 'cd ~ && python3 -m unittest discover tests -v'
```
Erwartet: alle PASS.

- [ ] **Schritt 6: Festhalten**

```bash
git add scannerlib/theme.py scannerlib/display.py tests/test_display.py
git commit -m "perf(scanner): RGB565 ueber PIL mit numpy-Rueckfall, Framebuffer offen halten"
```

---

## Aufgabe 5: Bildschleife

Hier wird die Hauptschleife umgebaut. Danach läuft die alte Oberfläche weiter, aber auf
der neuen Schleife — kein sichtbarer Unterschied, wohl aber die Grundlage für alles Weitere.

**Dateien:**
- Anlegen: `scannerlib/app.py` (aus dem Rest der alten `scanner.py`)

**Schnittstellen:**
- Liefert: `App(cfg)` mit `run()`, `invalidate()`, `_advance(dt) -> bool`

- [ ] **Schritt 1: Schleife schreiben**

```python
FPS = 30
FRAME = 1.0 / FPS

def run(self):
    self._start_threads()
    self._dirty = True
    last = time.monotonic()
    while True:
        now = time.monotonic()
        dt = now - last
        last = now

        self._drain_input()                 # alles Wartende, nicht blockierend
        animating = self._advance(dt)       # Physik, Zeitgeber, Leerlauf

        if self._dirty or animating:
            self._render()
            self._dirty = False

        rest = FRAME - (time.monotonic() - now)
        if rest > 0:
            time.sleep(rest)
        elif not animating:
            # Im Ruhezustand nicht heisslaufen: auf das naechste Ereignis warten
            self._wait_for_event(timeout=0.25)
```

`_drain_input` holt mit `queue.get_nowait()` in einer Schleife, bis `queue.Empty`.
`_wait_for_event` ist ein `queue.get(timeout=…)`, dessen Ergebnis zurückgelegt wird.

Dazu die drei Methoden, die spätere Aufgaben benutzen:

```python
def invalidate(self):
    """Naechstes Bild neu zeichnen. Ersetzt die direkten render()-Aufrufe,
    die bisher ueberall als Nebenwirkung verstreut waren."""
    self._dirty = True

def state_text(self):
    """Die Zeile unter der Modusleiste. Reihenfolge ist Absicht: ein
    fehlender Scanner ist dringender als eine fehlende Verbindung."""
    if not self.scanner_connected:
        return "Scanner nicht verbunden"
    if not self.api_ok:
        return "Keine Verbindung"
    if self.busy:
        return "Scanne…"
    return "Bereit zum " + ("Auslagern" if self.mode == "out" else "Einlagern")

def _check_idle(self, now=None):
    """Nach idle_reset_s ohne Beruehrung und ohne Scan zurueck auf Auslagern."""
    if not self.idle_reset_s:
        return False
    now = time.monotonic() if now is None else now
    if now - self.last_activity < self.idle_reset_s:
        return False
    self.mode = "out"
    self.location = None
    self.multiplier = 1
    self.last_result = None
    self.last_activity = now
    self.invalidate()
    return True
```

- [ ] **Schritt 2: `threading.Timer` ersetzen**

Ergebnis-Rücksprung und Backlight-Abschaltung werden zu Ablaufzeitpunkten, die `_advance`
prüft. Damit verschwinden zwei Threads, die bisher nebenläufig gezeichnet haben.

- [ ] **Schritt 3: Bildrate am Gerät messen**

```bash
ssh dstn@scanner.local 'sudo systemctl restart scanner && sleep 10 && journalctl -u scanner -n 5 --no-pager'
```
`App` protokolliert einmal pro Sekunde während Animationen die gemessene Bildrate.
Erwartet: **≥ 28 fps**. Darunter: in der Spezifikation, Abschnitt *Risiken*, nachsehen.

- [ ] **Schritt 4: Festhalten**

```bash
git add scannerlib/app.py && git commit -m "refactor(scanner): Ereignisschleife zur Bildschleife mit 30 fps"
```

---

## Aufgabe 6: Scan-Bildschirm

**Dateien:**
- Anlegen: `scannerlib/screens.py`

**Schnittstellen:**
- Liefert: `ScanScreen(theme, state)` mit `render(draw, img)`, `hit(px, py) -> str | None`

- [ ] **Schritt 1: Kopfzeile zeichnen** — Modusleiste nimmt den Restplatz, Verlauf-Knopf
      96 px, Verbindungspunkt unten links bei (16, H−30). Maße aus der Spezifikation,
      Abschnitt *Aufteilung der Kopfzeile*.

- [ ] **Schritt 2: Ergebniskarte** — zwei Spalten, Rückgängig über die volle Höhe,
      172 px breit, Karte mindestens 128 px hoch.

- [ ] **Schritt 3: `ellipsize` in `screens.py` anlegen**

```python
def ellipsize(draw, text, font, max_px):
    """Kuerzt mit Auslassungspunkten. Nie umbrechen -- eine zweite Zeile
    sprengt die Kartenhoehe (Spezifikation, Abschnitt Ergebniskarte)."""
    if draw.textlength(text, font=font) <= max_px:
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if draw.textlength(text[:mid] + "…", font=font) <= max_px:
            lo = mid
        else:
            hi = mid - 1
    return text[:lo] + "…"
```

- [ ] **Schritt 4: Test für lange Namen** (Prüfschwerpunkt 5)

```python
import unittest
from PIL import Image, ImageDraw
from scannerlib.theme import Theme
from scannerlib.screens import ellipsize

class TestKuerzen(unittest.TestCase):
    def setUp(self):
        self.t = Theme(640)
        self.d = ImageDraw.Draw(Image.new("RGB", (640, 480)))

    def test_langer_name_wird_gekuerzt_nicht_umgebrochen(self):
        name = "Bio-Vollmilch frisch laenger haltbar 3,5 Prozent Fett 1 Liter"
        g = ellipsize(self.d, name, self.t.font_md, max_px=390)
        self.assertLess(len(g), len(name))
        self.assertTrue(g.endswith("…"))
        self.assertNotIn("\n", g)
        self.assertLessEqual(self.d.textlength(g, font=self.t.font_md), 390)

    def test_kurzer_name_bleibt_unveraendert(self):
        self.assertEqual(ellipsize(self.d, "Obst", self.t.font_md, 390), "Obst")
```

- [ ] **Schritt 5: Navigation verdrahten** — die Tabelle aus der Spezifikation, Abschnitt
      *Navigation*, eins zu eins. `hit()` liefert eine Kennung (`"mode_out"`, `"mode_in"`,
      `"hist"`, `"undo"`, `"mult"`, `"loc"`), `App` entscheidet daraus den Übergang. Der
      Zurück-Pfeil erscheint nur auf Lagerort und Verlauf, nie auf der Scan-Ansicht.

- [ ] **Schritt 6: Am Gerät ansehen**

```bash
ssh dstn@scanner.local 'sudo python3 - <<EOF
import numpy as np
from PIL import Image
a=np.frombuffer(open("/dev/fb0","rb").read(480*640*2),dtype=np.uint16).reshape(640,480)
r=(((a>>11)&0x1F).astype(np.uint8))<<3; g=(((a>>5)&0x3F).astype(np.uint8))<<2; b=((a&0x1F).astype(np.uint8))<<3
Image.fromarray(np.dstack([r,g,b])).transpose(Image.ROTATE_270).save("/tmp/schirm.png")
EOF'
scp dstn@scanner.local:/tmp/schirm.png .
```
Bild ansehen und mit dem Entwurf vergleichen.

- [ ] **Schritt 7: Festhalten**

---

## Aufgabe 7: Lagerort- und Verlauf-Bildschirm

**Dateien:**
- Ändern: `scannerlib/screens.py`

- [ ] **Schritt 1: Lagerortliste an `ScrollView` hängen** — Sichthöhe 480 − 72 − 60 = 348,
      Zeilenhöhe 96. Gezeichnet wird mit `visual_offset`, nicht mit `offset`.

- [ ] **Schritt 2: Scrollbalken** — 4 px breit, rechts, nur während der Bewegung sichtbar,
      Höhe proportional zum sichtbaren Anteil.

- [ ] **Schritt 3: Zeilenauswahl nur, wenn nicht gewischt wurde** — `was_drag` prüfen,
      sonst wählt jeder Wisch beim Loslassen eine Zeile aus.

- [ ] **Schritt 4: Verlauf-Bildschirm** — Zeilen 96 px, Name gekürzt, Menge in Akzentfarbe,
      Zeitangabe rechts, Rückgängig-Knopf 72 × 64 px.

- [ ] **Schritt 5: Am Gerät ansehen und festhalten**

---

## Aufgabe 8: Rückgängig, ×N und Rücksprung

**Dateien:**
- Ändern: `scannerlib/app.py`, `scannerlib/api.py`

**Schnittstellen:**
- Liefert: `App.book(barcode, count=1) -> ScanEntry` (führt N Aufrufe aus, legt den
  Verlaufseintrag an und gibt ihn zurück; `entry.booked` ist die tatsächlich gebuchte
  Zahl), `App.undo(entry) -> None`, `App.api_ok: bool`, `App.scanner_connected: bool`

- [ ] **Schritt 1: Testdoppel anlegen** (`tests/helpers.py`)

```python
"""Testdoppel fuer die API. Kein Netz, kein Display."""
from scannerlib.app import App


class FakeAPI:
    def __init__(self, fail_at=None, deleted_on_scan_out=False):
        self.fail_at = fail_at          # 1-basiert: der wievielte Aufruf scheitert
        self.deleted_on_scan_out = deleted_on_scan_out
        self.calls = []

    def get_locations(self):
        return [{"id": 1, "name": "Küche oben"}]

    def _maybe_fail(self):
        if self.fail_at is not None and len(self.calls) == self.fail_at:
            return (None, "Verbindung abgebrochen")
        return None

    def scan_out(self, barcode):
        self.calls.append(("out", barcode))
        fail = self._maybe_fail()
        if fail:
            return fail
        return (200, {"status": "ok", "name": "Milch", "barcode": barcode,
                      "remaining_quantity": 0 if self.deleted_on_scan_out else 3,
                      "deleted": self.deleted_on_scan_out})

    def scan_in(self, barcode, storage_location_id=None):
        self.calls.append(("in", barcode))
        fail = self._maybe_fail()
        if fail:
            return fail
        return (200, {"status": "ok", "name": "Milch", "barcode": barcode,
                      "quantity": 1, "storage_location": None,
                      "created": self.deleted_on_scan_out})


class FakeDisplay:
    """Zeichnet ins Leere -- die Buchungslogik braucht kein Bild."""
    width, height = 640, 480
    def flush(self, img): pass
    def wake(self): return False
    def new_frame(self):
        from PIL import Image
        return Image.new("RGB", (640, 480))


def make_app(api):
    app = App.__new__(App)          # ohne __init__, kein Geraet noetig
    app.api = api
    app.display = FakeDisplay()
    app.mode = "out"
    app.location = None
    app.multiplier = 1
    app.api_ok = True
    app.scanner_connected = True
    app.last_result = None
    from scannerlib.scanlog import ScanLog
    app.log = ScanLog()
    app._dirty = False
    return app
```

- [ ] **Schritt 2: Tests für die Gegenbuchung schreiben** (Prüfschwerpunkte 2 und 3)

```python
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
        self.assertFalse(app.api_ok)          # Verbindungspunkt wird rot

    def test_multiplikator_faellt_auch_bei_abbruch_zurueck(self):
        app = make_app(FakeAPI(fail_at=2))
        app.multiplier = 8
        app.book("111", count=app.multiplier)
        self.assertEqual(app.multiplier, 1)

    def test_undo_bucht_gegen(self):
        app = make_app(FakeAPI())
        e = app.book("111", count=1)          # ein scan_out
        app.undo(e)
        self.assertEqual([c[0] for c in app.api.calls], ["out", "in"])
        self.assertEqual(app.log.entries, [])

    def test_undo_eines_geloeschten_artikels_meldet_verlorenen_ort(self):
        # Pruefschwerpunkt 2
        app = make_app(FakeAPI(deleted_on_scan_out=True))
        e = app.book("111", count=1)
        app.undo(e)
        self.assertTrue(app.last_result.location_lost)
```

- [ ] **Schritt 3: Tests laufen lassen, Fehlschlag bestätigen**

```bash
ssh dstn@scanner.local 'cd ~ && python3 -m unittest tests.test_booking -v'
```
Erwartet: `AttributeError: 'App' object has no attribute 'book'`

- [ ] **Schritt 4: `App.book` umsetzen**

```python
def book(self, barcode, count=1):
    """Setzt count Aufrufe nacheinander ab und legt den Verlaufseintrag an.

    Die API kennt keine Menge, deshalb die Schleife. Bricht ein Aufruf ab,
    endet sie -- der Eintrag traegt dann die tatsaechlich gebuchte Zahl,
    nicht die gewuenschte.
    """
    booked, status, data, name = 0, None, None, barcode
    for i in range(count):
        if self.mode == "out":
            status, data = self.api.scan_out(barcode)
        else:
            loc = self.location["id"] if self.location else None
            status, data = self.api.scan_in(barcode, loc)
        if status != 200:
            break
        booked += 1
        if isinstance(data, dict):
            name = data.get("name", barcode)
        self.invalidate()           # Fortschrittsring weiterdrehen
    self.api_ok = status is not None
    entry = self.log.add(barcode, name, self.mode, count=count, booked=booked)
    self.last_result = entry
    self.multiplier = 1             # faellt immer zurueck, auch bei Abbruch
    self.invalidate()
    return entry
```

- [ ] **Schritt 5: `App.undo` umsetzen**

```python
def undo(self, entry):
    """Gegenbuchung: ein scan_in hebt ein scan_out auf und umgekehrt.

    Keine echte Ruecknahme -- zwischen Scan und Ruecknahme kann jemand ueber
    die Weboberflaeche eingegriffen haben. War es das letzte Exemplar und der
    Artikel wurde geloescht, legt die Gegenbuchung ihn neu an und der
    Lagerort fehlt; das wird angezeigt, nicht verschwiegen.
    """
    lost = False
    for _ in range(entry.booked):
        if entry.mode == "out":
            status, data = self.api.scan_in(entry.barcode)
            if status == 200 and isinstance(data, dict) and data.get("created"):
                lost = True
        else:
            status, data = self.api.scan_out(entry.barcode)
        if status != 200:
            self.api_ok = False
            break
    self.log.remove(entry)
    entry.location_lost = lost
    self.last_result = entry
    self.invalidate()
```

- [ ] **Schritt 6: Tests laufen lassen, Erfolg bestätigen**

```bash
ssh dstn@scanner.local 'cd ~ && python3 -m unittest tests.test_booking -v'
```
Erwartet: alle sechs PASS.

- [ ] **Schritt 7: Multiplikator-Auswahl** — ×1 bis ×12 als 4×3-Raster, Kacheln 96 × 80 px,
      Raster 420 × 264 px mittig über dem Bildschirm. Ist N > 1, steht der Knopf in
      Akzentfarbe. Maße aus der Spezifikation, Abschnitt *Multiplikator ×N*.

- [ ] **Schritt 8: Verbindungsstatus** — `api_ok` speist den Punkt unten links: grün nach
      erfolgreichem Abruf, rot nach einem fehlgeschlagenen. Gespeist wird er aus den
      ohnehin stattfindenden Aufrufen plus dem Lagerort-Nachladen, **kein eigener
      Abfragetakt**. Zustandszeile zeigt dann „Keine Verbindung" statt „Bereit".

- [ ] **Schritt 9: Scanner-Erkennung** — `inputs.barcode_reader` meldet über die
      Warteschlange `("scanner", False)`, wenn das Gerät fehlt, und `("scanner", True)`
      beim Öffnen. `App.scanner_connected` steuert daraus die Zustandszeile
      („Scanner nicht verbunden"). Behebt, dass am 27.09. zwanzig Stunden lang „Bereit"
      stand, während gar kein Scanner angeschlossen war.

```python
def test_zustandszeile_meldet_fehlenden_scanner(self):
    app = make_app(FakeAPI())
    app.scanner_connected = False
    self.assertIn("Scanner", app.state_text())
    app.scanner_connected = True
    app.api_ok = False
    self.assertIn("Verbindung", app.state_text())
```

- [ ] **Schritt 10: Rücksprung nach Leerlauf** — `idle_reset_minutes` in `scanner.conf`,
      Vorgabe 10, `0` schaltet ab. `_advance` prüft die Zeit seit der letzten Berührung
      und dem letzten Scan. Setzt Modus auf `out`, verwirft die Lagerortwahl, Multiplikator
      auf ×1, Ergebniskarte leeren.

```python
def test_rücksprung_setzt_alles_zurueck(self):
    app = make_app(FakeAPI())
    app.mode, app.multiplier = "in", 8
    app.location = {"id": 1, "name": "Küche oben"}
    app.idle_reset_s = 600
    app.last_activity = 0.0
    app._check_idle(now=601.0)
    self.assertEqual(app.mode, "out")
    self.assertIsNone(app.location)
    self.assertEqual(app.multiplier, 1)

def test_rücksprung_abschaltbar(self):
    app = make_app(FakeAPI())
    app.mode, app.idle_reset_s, app.last_activity = "in", 0, 0.0
    app._check_idle(now=99999.0)
    self.assertEqual(app.mode, "in")
```

- [ ] **Schritt 11: Fehlerbehandlung vervollständigen** — die Tabelle aus der
      Spezifikation, Abschnitt *Fehlerbehandlung*, Zeile für Zeile: 404 unbekannter
      Barcode (Warnfarbe, Barcode-Nummer, **kein** Verlaufseintrag), 400
      `invalid_storage_location` (Orte nachladen, zurück zur Ortswahl), 401
      (Fehlerfarbe, „Token prüfen").

- [ ] **Schritt 12: Alle Tests laufen lassen und festhalten**

```bash
ssh dstn@scanner.local 'cd ~ && python3 -m unittest discover tests -v'
git add -A && git commit -m "feat(scanner): Rückgängig, Multiplikator, Leerlauf-Rücksprung, Statusanzeige"
```

---

## Aufgabe 9: Ausliefern und am Gerät prüfen

- [ ] **Schritt 1: Alles aufspielen**

```bash
scp -r scannerlib scanner.py scanner.conf dstn@scanner.local:~/
ssh dstn@scanner.local 'sudo systemctl restart scanner && sleep 5 && systemctl is-active scanner'
```

- [ ] **Schritt 2: Vollständiger Testlauf auf dem Gerät**

```bash
ssh dstn@scanner.local 'cd ~ && python3 -m unittest discover tests -v'
```

- [ ] **Schritt 3: Bildrate unter Last bestätigen** — während des Scrollens, aus dem
      Journal. Erwartet ≥ 28 fps.

- [ ] **Schritt 4: Von Hand durchgehen** — Modus umschalten, Lagerort wählen (scrollen,
      überziehen, loslassen), scannen, rückgängig, ×8 buchen, Verlauf öffnen, zehn Minuten
      warten und den Rücksprung prüfen.

- [ ] **Schritt 5: Scroll-Konstanten nachziehen** — die Werte aus dem Entwurf übernehmen,
      sobald sie feststehen.

- [ ] **Schritt 6: Festhalten und zusammenfassen**
