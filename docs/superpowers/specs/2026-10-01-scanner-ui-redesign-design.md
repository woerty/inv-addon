# Scanner-UI: Neugestaltung für das kapazitive 640×480-Panel

**Datum:** 2026-10-01
**Betrifft:** `scanner.py` auf dem Barcode-Terminal (`scanner.local`, Raspberry Pi 3A+)
**Status:** Entwurf zur Abnahme

## Ausgangslage

Das Terminal hat ein neues Display bekommen: Waveshare 2,8" kapazitiv, 480×640 über DPI,
Touch über einen GT911. Vorher: 2,8" resistiv, 320×240 über SPI. Die Anbindung läuft
(siehe `scanner.conf`: `fb_rotate=90`, `touch_swap_xy=1`, `touch_flip_x=1`), und die
bestehende Oberfläche wurde lediglich um Faktor 2 hochskaliert.

Damit ist die Auflösung vervierfacht, die Oberfläche aber unverändert — entworfen für ein
Panel, das pro Berührung 21 px zitterte. Die ganze Vorsicht von damals ist gegenstandslos.

## Ziel

Eine Oberfläche, die zum Gerät passt: größere Trefferflächen, saubere Typografie, und
Interaktionen, die sich wertig anfühlen statt bloß zu funktionieren. Dazu drei
Arbeitsabläufe, die heute fehlen: Fehlscans zurücknehmen, sehen was zuletzt passiert ist,
und Mehrfachmengen ohne Mehrfachscannen erfassen.

## Randbedingungen

### Physik des Geräts

Das bestimmt mehr als alles andere:

| Größe | Wert |
|---|---|
| Diagonale | 2,8" = 71 mm |
| Sichtbare Fläche | 57 × 43 mm |
| Auflösung | 640 × 480 (quer, nach 90°-Drehung) |
| Pixeldichte | **11,2 px/mm** |
| Montage | wandmontiert, Blick aus ~50 cm |

Daraus folgt zwingend:

- **Eine Fingerkuppe deckt 8–10 mm ab, also 90–112 px.** Trefferflächen unter 80 px sind
  Glückssache. Listenzeilen gehen von 88 auf **96 px**.
- **Text braucht bei 50 cm rund 0,3° Sehwinkel**, also ≥ 2,6 mm, also **≥ 30 px**.
- Bei 480 px Höhe bleiben nach der 72 px hohen Modusleiste rechnerisch 4,25 Listenzeilen.
  Auf dem Lagerort-Bildschirm kommt eine Unterzeile dazu, dort sind es 3,6 — siehe dort.

Die vierfache Pixelzahl bringt **Schärfe, keinen Platz**. Jeder Entwurf, der mehr Inhalt
unterbringen will, ist falsch.

### Hardware

Raspberry Pi 3A+, BCM2837 (Cortex-A53 4×1,4 GHz), 512 MB. Im Leerlauf praktisch
unbeschäftigt — gemessen 1 min 27 s CPU-Zeit über fünf Tage Laufzeit.

Ein Vollbild kostet: PIL zeichnen → `transpose(ROTATE_90)` → numpy nach RGB565 →
600 KB nach `/dev/fb0`. **Dieser Wert ist nicht gemessen und entscheidet über die
Bildrate.** Siehe Risiken.

### API

Die Endpunkte des Addons kennen **keine Menge**:

```python
class ScanOutRequest(BaseModel):
    barcode: str
class ScanInRequest(BaseModel):
    barcode: str
    storage_location_id: int | None = None
```

`scan-in` macht `existing.quantity += 1`, `scan-out` zieht eins ab. Entschieden:
**die API bleibt unangetastet.** Mengen und Rücknahmen löst der Client durch wiederholte
bzw. gegenläufige Aufrufe. Das vermeidet einen zweiten Bauplatz (Addon-Repo, Docker-Image,
Neu-Ausrollen in Home Assistant) und hält die Änderung in einer Datei.

## Nicht-Ziele

- Keine Änderung am Addon oder an der API.
- Keine Suche in der Lagerortliste. Bei neun Einträgen lohnt sich das nicht.
- Kein Vorschlag des zuletzt benutzten Lagerorts (verworfen).
- Keine Mehrfingergesten. Der GT911 kann fünf Finger, gebraucht wird einer.
- Kein Umstieg auf ein Grafik-Framework. PIL plus Framebuffer bleibt.

## Architektur

### Von der Ereignis- zur Bildschleife

Der Kern der Umstellung. Heute:

```python
while True:
    event = self.event_queue.get(timeout=1.0)   # blockiert
    ...handle...                                # zeichnet als Nebenwirkung
```

Gezeichnet wird nur, wenn ein Ereignis eintrifft. Eine Animation kann es so nicht geben.
Künftig:

```python
while True:
    now = time.monotonic()
    dt = now - last
    self._drain_input()        # alle wartenden Ereignisse, nicht blockierend
    self._advance(dt)          # Physik, Übergänge, Zeitgeber
    if self._dirty or self._animating:
        self._render()
    self._sleep_until_next_frame()
```

Wichtig: **im Ruhezustand wird nicht gezeichnet.** Die Schleife läuft mit 30 fps nur,
solange etwas in Bewegung ist; sonst wartet sie auf Eingaben. Der Stromverbrauch bleibt
damit wie heute.

Die Zeitgeber, die heute `threading.Timer` sind (Ergebnis-Rücksprung, Backlight-Abschaltung),
wandern in `_advance()`. Damit entfällt ein Teil der Nebenläufigkeit, die uns schon einmal
zerrissene Bilder beschert hat.

### Bausteine

| Baustein | Aufgabe | Abhängigkeiten |
|---|---|---|
| `Theme` | Farben, Schriftstufen, Abstände als benannte Werte | PIL (Schriften) |
| `ScrollView` | Scroll-Physik: Offset, Geschwindigkeit, Rubberband | keine (reine Mathematik) |
| `ScanLog` | Ringpuffer der letzten Scans, Zusammenfassung, Rücknahme | `API` |
| `Multiplier` | Zustand des ×N-Knopfs | keine |
| Bildschirme | Zeichnen und Eingabebehandlung je Ansicht | `Theme`, `Display` |

`ScrollView` und `ScanLog` haben keine Ein-/Ausgabe und sind dadurch eigenständig testbar.
Das ist Absicht: die Scroll-Physik ist der Teil, bei dem man Fehler sonst nur erfühlt.

## Scroll-Physik

### Zustände

```
RUHEND ──(Berührung)──► ZIEHEND ──(Loslassen, v groß)──► GLEITEND ──► RUHEND
                            │                                │
                            └──(Loslassen außerhalb)──► FEDERND ──┘
```

### Ziehen

Innerhalb der Grenzen folgt der Inhalt dem Finger 1:1.

Außerhalb greift Dämpfung, damit sich der Rand „schwer" anfühlt:

```
gedämpft = grenze + d * (1 - 1/(überhang/d + 1))      mit d = Ansichtshöhe
```

Bei kleinem Überhang nahezu 1:1, asymptotisch gegen `d`. Weiter als eine Bildschirmhöhe
lässt sich nicht ziehen.

### Gleiten

Beim Loslassen wird die Geschwindigkeit aus den Bewegungen der letzten **100 ms**
geschätzt (nicht aus dem letzten Einzelwert — der ist beim Abheben verrauscht).

```
v(t) = v₀ · e^(−k·t)        k = 3,0 /s
```

Ende bei `|v| < 20 px/s`. Erreicht der Inhalt beim Gleiten eine Grenze, geht der Zustand
nach FEDERND über und nimmt die Restgeschwindigkeit mit.

### Federn

Kritisch gedämpfte Annäherung an die Grenze:

```
x += (ziel − x) · (1 − e^(−k·dt))        k = 12,0 /s
```

Ende bei `|ziel − x| < 0,5 px`.

Alle vier Konstanten (`k_reibung`, `v_min`, `k_feder`, Dämpfungsweite) gehören als
benannte Werte in `ScrollView` — sie werden am echten Gerät nachjustiert.

### Tippen oder Wischen

Die heutige Schwelle von 25 px bleibt, ist aber nicht mehr gegen Rauschen gerichtet,
sondern gegen den natürlichen Wackler beim Antippen. Erst wenn der Finger sie
überschreitet, beginnt das Ziehen; vorher ist es ein Tipp.

## Gestaltung

### Farben

| Name | Wert | Verwendung |
|---|---|---|
| `bg` | `#0E1014` | Hintergrund |
| `surface` | `#1A1D24` | Karten, Listenzeilen (gerade) |
| `surface_alt` | `#232733` | Listenzeilen (ungerade) |
| `border` | `#2E3340` | Trennlinien |
| `text` | `#E8EBF0` | Haupttext |
| `text_dim` | `#8B93A3` | Nebentext |
| `accent` | `#4FA8FF` | Auswahl, Hinweise |
| `out` | `#F2A341` | Modus Auslagern |
| `in` | `#4ED97E` | Modus Einlagern, Erfolg |
| `warn` | `#FFC24D` | Unbekannter Barcode |
| `danger` | `#FF6B6B` | Fehler |

Dunkel bleibt dunkel — das Gerät hängt in der Küche und soll nachts nicht blenden.

### Schrift

DejaVu Sans Bold, vier Stufen: **56 / 40 / 32 / 26 px**. Die kleinste liegt knapp unter
der 30-px-Regel und ist deshalb nur für Beiwerk erlaubt, nie für Information, die man
lesen muss.

Zuordnung, wie am Entwurf festgelegt:

| Element | Größe | |
|---|---|---|
| Modusknöpfe, Listenzeile, Produktname, Zustandszeile, Mengenraster | 32 px | Leiter |
| Rückgängig, Zusatztext, Lagerortzeile, Zeitangabe im Verlauf | 26 px | Leiter |
| ×N-Knopf | 36 px | Symbol |
| Verlauf-Knopf ☰ | 30 px | Symbol |
| Zurück-Pfeil ← | 28 px | Symbol |
| Haken in der Karte | 22 px | Symbol |

Die drei Symbolgrößen stehen bewusst neben der Leiter: ×, ☰, ← und ✓ sind Zeichen, keine
Lesetexte, und werden nach ihrer Fläche bemessen statt nach Lesbarkeit auf Distanz. Jede
Größe unter 32 px, die *Text* trägt, muss sich gegen diese Tabelle rechtfertigen.

### Raster

Grundabstand 8 px. Ränder 16 px. Eckenradius 12 px für Karten, 8 px für Knöpfe.

## Bildschirme

Es gibt künftig **drei** statt vier. Der Modus-Bildschirm (`MODE_SELECT`) entfällt
ersatzlos — seine Aufgabe übernimmt die Leiste in der Kopfzeile.

### Navigation

| von | Aktion | nach |
|---|---|---|
| Scan | „Einlagern" antippen, kein Ort gewählt | Lagerort |
| Scan | „Einlagern" antippen, Ort bereits gewählt | bleibt, Modus wechselt |
| Scan | Ortszeile unter der Leiste antippen | Lagerort |
| Scan | ≡ antippen | Verlauf |
| Lagerort | Zeile antippen | Scan, Modus Einlagern |
| Lagerort | „Auslagern" in der Leiste antippen | Scan, Modus Auslagern |
| Lagerort | Zurück | Scan, Modus unverändert |
| Verlauf | Zurück | Scan |

Der Zurück-Pfeil erscheint nur auf Lagerort und Verlauf, nie auf der Scan-Ansicht —
dort gibt es nichts, wohin man zurückkönnte.

### Scan (Hauptansicht, ~95 % der Laufzeit)

```
┌────────────────────────────────────────────┐
│ ┌  Auslagern  ┐┌  Einlagern  ┐      ┌ ≡ ┐  │  Kopf, 72 px
├────────────────────────────────────────────┤
│            Bereit zum Scannen              │  Zustand
│  ╭───────────────────────────┬──────────╮  │
│  │ ✓  Gouda jung 48%         │          │  │  letzter Scan
│  │    noch 3 auf Lager       │Rückgängig│  │  min. 128 px
│  ╰───────────────────────────┴──────────╯  │
│                                            │
│                 ╭──────╮                   │
│                 │  ×1  │                   │  Multiplikator
│                 ╰──────╯                   │
│  ●                                         │  Verbindung
└────────────────────────────────────────────┘
```

Die wesentliche Änderung gegenüber heute: **das Ergebnis bleibt stehen.** Kein
Vollbild-Takeover für vier Sekunden. Die Karte wird beim nächsten Scan ersetzt und leuchtet
dabei kurz auf (200 ms Überblendung der Hintergrundfarbe).

Zustandszeile: „Bereit zum Scannen" / „Scanne…" / bei fehlender Verbindung „Keine
Verbindung".

#### Aufteilung der Kopfzeile

Festgelegt am Entwurf:

| Element | Breite |
|---|---|
| Modusleiste | der gesamte verbleibende Platz, beide Knöpfe gleich breit (je ~255 px) |
| Verlauf-Knopf | **96 px = 15 % der Bildschirmbreite** |
| Innenabstand / Lücke | 2 × 12 px Rand, 10 px Lücke |

Der Verlauf-Knopf ist eine Fläche von 96 × 52 px, kein bloßes Zeichen. Als reines Symbol
wäre er rund 38 px breit gewesen und damit deutlich unter der Fingerbreite — nicht
zuverlässig zu treffen.

Der **Verbindungspunkt sitzt nicht in der Kopfzeile**, sondern frei in der unteren linken
Ecke (16 px vom Rand, 14 px Durchmesser). Er gilt für alle drei Bildschirme und nimmt der
Modusleiste so keine Breite weg.

#### Ergebniskarte

Die Karte ist eine Zeile aus zwei Teilen: links Haken, Name und Zusatz untereinander,
rechts der Rückgängig-Knopf über die **volle Kartenhöhe**. Bei 128 px Mindesthöhe und
2 × 16 px Innenabstand ergibt das 96 px — dasselbe Fingermaß wie die Listenzeilen. Als
flacher Knopf in einer Fußzeile wäre er rund 68 px hoch gewesen und damit unterhalb der
Fingerkuppe.

Der Knopf ist **172 px breit**. Bei 156 px hätte die Beschriftung auf 24 px heruntergehen
müssen, also unter die Leiter; mit 172 px passen die 26 px.

Lange Produktnamen werden mit Auslassungspunkten gekürzt, nicht umgebrochen — eine zweite
Zeile würde die Kartenhöhe sprengen. Dasselbe gilt für die Namen im Verlauf.

### Lagerort

Erscheint beim Wechsel auf Einlagern, solange kein Ort gewählt ist. Modusleiste wie oben,
darunter eine 60 px hohe Unterzeile mit Zurück-Pfeil und Titel, darunter die scrollende
Liste. Zeilenhöhe 96 px, Scrollbalken rechts (4 px, nur während der Bewegung sichtbar).

**Sichtbar sind drei volle Zeilen und eine angeschnittene** — 480 − 72 − 60 = 348 px,
also 3,6 Zeilen. Die weiter oben genannten vier Zeilen gelten für eine Liste über die
volle Höhe; hier kosten Modusleiste und Unterzeile zusammen 132 px.

Die angeschnittene vierte Zeile ist kein Schönheitsfehler, sondern erwünscht: eine halb
sichtbare Zeile sagt dem Auge, dass die Liste weitergeht. Eine Liste, die exakt mit der
Unterkante abschließt, sieht vollständig aus und wird nicht gescrollt.

Nach der Wahl zurück zur Scan-Ansicht; der Ort steht unter der Modusleiste und ist
antippbar, um ihn zu wechseln.

### Verlauf

Über das ≡ oben rechts. Liste der letzten **20** Scans, gleiche Artikel zusammengefasst:

```
  Milch 3,5%          ×3     vor 2 min    [↶]
  Gouda jung 48%      ×1     vor 5 min    [↶]
```

Zusammengefasst wird nur, was **direkt aufeinander folgt** und denselben Barcode und
dieselbe Richtung hat — sonst würde ein dazwischenliegender anderer Scan die zeitliche
Ordnung verfälschen.

## Arbeitsabläufe

### Rückgängig

Als Gegenbuchung: ein `scan-out` hebt ein `scan-in` auf und umgekehrt. Bei einem
zusammengefassten Eintrag (`×3`) werden drei Gegenbuchungen abgesetzt.

**Bekannte Einschränkung, die angezeigt werden muss:** war es das letzte Exemplar und der
Artikel wurde dadurch gelöscht, legt die Gegenbuchung ihn neu an — **der Lagerort geht
dabei verloren**. In diesem Fall zeigt die Karte „wiederhergestellt, Lagerort fehlt".

Ein zurückgenommener Eintrag verschwindet aus dem Verlauf und kann nicht erneut
zurückgenommen werden.

### Multiplikator ×N

Tipp auf den Knopf öffnet eine Auswahl: **×1 bis ×12**, als Raster aus vier Spalten und
drei Zeilen, Kacheln 96 × 80 px. Vier Spalten, weil das Raster damit 420 × 264 px misst
und bequem ins Bild passt — bei drei Spalten wären es 312 × 356 px, was zusammen mit der
Überschrift der Unterkante zu nahe käme. ×1 steht vorn und dient zum Abwählen.

Nach der Wahl steht der Knopf in Akzentfarbe und deutlich größer, damit man ihn nicht
übersieht.

Beim nächsten Scan werden N Aufrufe nacheinander abgesetzt, mit Fortschrittsring auf der
Karte. **Danach springt er auf ×1 zurück** — auch bei Teilerfolg oder Abbruch.

Schlägt ein Aufruf fehl, bricht die Schleife ab und die Karte zeigt ehrlich
„6 von 8 gebucht" in Warnfarbe. Es wird nichts automatisch zurückgenommen; der Verlauf
zeigt den Eintrag mit der tatsächlich gebuchten Menge, und von dort lässt er sich
zurücknehmen.

### Rücksprung nach Leerlauf

Nach **10 Minuten** ohne Berührung und ohne Scan: zurück in den Auslagern-Modus,
Lagerortwahl verworfen, Multiplikator auf ×1, Ergebniskarte geleert. Einstellbar über
`idle_reset_minutes` in `scanner.conf`, 0 schaltet ab.

Davon unberührt bleibt die Backlight-Abschaltung nach 10 Sekunden.

### Verbindungsstatus

Punkt unten links: grün bei erfolgreichem Abruf, rot nach einem fehlgeschlagenen.
Gespeist wird er aus den ohnehin stattfindenden Aufrufen plus dem Lagerort-Nachladen —
**kein eigener Abfragetakt.**

## Fehlerbehandlung

| Fall | Verhalten |
|---|---|
| API nicht erreichbar | Karte in Warnfarbe, Statuspunkt rot, Zustandszeile „Keine Verbindung" |
| Barcode unbekannt (404) | Karte in Warnfarbe mit Barcode-Nummer, kein Verlaufseintrag |
| Lagerort ungültig (400) | Orte nachladen, zurück zur Lagerortwahl |
| Token falsch (401) | Karte in Fehlerfarbe, „Token prüfen" |
| Scanner abgezogen | Zustandszeile „Scanner nicht verbunden" statt „Bereit" |
| ×N bricht ab | „n von N gebucht" in Warnfarbe, kein automatisches Zurücknehmen |

Der Fall „Scanner abgezogen" ist neu und behebt ein echtes Ärgernis: am 27.09. fiel der
Scanner vom USB-Bus und das Display zeigte 20 Stunden lang fröhlich „Bereit".

## Testen

**Testgetrieben, weil reine Mathematik:**

- `ScrollView`: Offset nach gegebenen `dt`-Schritten, Abklingen der Geschwindigkeit,
  Rubberband überschreitet nie die Dämpfungsweite, Federn endet, Tipp unterhalb der
  Schwelle scrollt nicht, Wisch oberhalb schon.
- `ScanLog`: Zusammenfassung nur bei direkter Folge, Rücknahme entfernt den Eintrag,
  Ringpuffer läuft bei 20 über.

**Gegen das echte Gerät:**

- Bildzeit messen, bevor irgendetwas gebaut wird (siehe Risiken).
- Bildschirme rendern, Framebuffer auslesen, ansehen — das Verfahren hat sich bewährt.
- Trefferflächen gegen die 80-px-Regel prüfen.

## Risiken

**Gemessen am 2026-10-01 auf dem Gerät. Plan A trägt.**

Ein realistisches Vollbild (Modusleiste plus scrollende Liste), Mittel über 35 Durchläufe:

| Stufe | Zeit |
|---|---|
| Zeichnen (PIL) | 10,6 ms |
| Wandeln nach RGB565 **und** Drehen | 8,3 ms |
| Schreiben nach `/dev/fb0` | 0,5 ms |
| **Gesamt** | **19,4 ms → 51 fps möglich** |

Bei 30 fps (33,3 ms Budget) bleiben damit 14 ms Reserve für Eingaben und Physik.

Der Weg dorthin war nicht offensichtlich. Vier Varianten wurden verglichen, alle liefern
**byteidentische** Ergebnisse:

| Variante | Zeit |
|---|---|
| PIL dreht, numpy wandelt (bisheriger Code) | 17,9 ms |
| numpy wandelt, numpy dreht | 15,4 ms |
| PIL dreht, PIL wandelt | 8,7 ms |
| **PIL wandelt (`convert("BGR;16")`), numpy dreht (`rot90`)** | **8,3 ms** |

`BGR;16` ist in Pillow als veraltet markiert und soll in Version 12 entfallen (installiert
ist 11.1.0). Deshalb wird die Wandlung **mit Rückfall** geschrieben: zuerst der schnelle
Weg, bei `ValueError`/`KeyError` der numpy-Weg. Entfällt der Modus künftig, kostet das
7 ms und damit 26,5 ms gesamt — immer noch innerhalb des 30-fps-Budgets. Es bricht nichts,
es wird nur langsamer.

Plan B (nur den Listenbereich neu zeichnen) wird damit **nicht gebraucht** und entfällt
ersatzlos.

**Zweitrangig:** die Gegenbuchung ist keine echte Rücknahme. Zwischen Scan und Rücknahme
kann jemand über die Weboberfläche eingegriffen haben. Für ein Haushaltsinventar ist das
hinnehmbar; es gehört aber in die Anzeige, nicht in eine Fußnote.

## Offene Punkte

Keine. Die Mengenfrage ist entschieden (Client-seitig), der Umfang der Zusätze ist
abgestimmt, die physischen Randbedingungen sind gemessen.
