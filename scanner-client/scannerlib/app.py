"""Zustand, Ereignisbehandlung und Bildschleife."""
import queue
import threading
import time

from PIL import ImageDraw

from .api import API
from .display import Display
from .inputs import barcode_reader, touch_reader
from .scanlog import ScanLog
from .screens import Screens
from .scroll import ScrollView
from .theme import Theme

# Bildrate waehrend Animationen. Gemessen auf dem Pi 3A+: ein Vollbild kostet
# 19,4 ms, das Budget sind 33,3 ms.
FPS = 30
FLASH_SECONDS = 0.2
FRAME_SECONDS = 1.0 / FPS
LOCATION_RETRY_INTERVAL = 30.0

SCAN, LOCATIONS, HISTORY, MULT = "scan", "locations", "history", "mult"


def hit(rect, px, py):
    return rect is not None and rect[0] <= px <= rect[2] and rect[1] <= py <= rect[3]


class App:
    def __init__(self, cfg):
        self.cfg = cfg
        self.display = Display(
            cfg["fb_device"], cfg["screen_width"], cfg["screen_height"],
            cfg["backlight"], cfg["backlight_timeout"],
            rotate=cfg.get("fb_rotate", 0),
        )
        self.theme = Theme(cfg["screen_width"], cfg["screen_height"])
        self.screens = Screens(self.theme)
        self.api = API(cfg["api_url"], cfg["scanner_token"])
        self.event_queue = queue.Queue()
        self.log = ScanLog()

        self.screen = SCAN
        self.mode = "out"
        self.location = None
        self.locations = []
        self.locations_known = False
        self.multiplier = 1
        self.api_ok = True
        self.scanner_connected = True
        self.busy = False
        self.booking = False
        self.progress = None    # (erledigt, gesamt) waehrend einer Buchung
        self.last_result = None      # dict fuer die Karte
        self.last_entry = None       # zugehoeriger ScanEntry, fuer Rueckgaengig
        self.flash_until = 0.0
        self.idle_reset_s = int(cfg.get("idle_reset_minutes", 10)) * 60
        self.last_activity = time.monotonic()

        self.scroll_loc = None
        self.scroll_hist = None
        self._swallow = False
        self._dirty = True
        self._rects = {}
        self._locations_lock = threading.Lock()
        self._location_fetch_running = False

        self._refresh_locations()
        self._last_location_fetch = time.monotonic()
        self._apply_start_mode()

    # ---------- Lagerorte ----------

    def _refresh_locations(self):
        """Lagerorte holen.

        Eine leere Liste ist eine gueltige Antwort, kein Ausfall -- sonst
        steht dauerhaft "Keine Verbindung" und es wird alle 30 Sekunden
        erfolglos nachgefragt. Nur None heisst, dass der Abruf scheiterte.
        """
        data = self.api.get_locations()
        if data is None:
            self.api_ok = False
            print("Locations: Abruf fehlgeschlagen (%d bekannt)" % len(self.locations))
            return
        self.locations = list(data)
        self.api_ok = True
        self.locations_known = True
        print("Locations loaded: %d" % len(self.locations))

    def _refresh_locations_async(self):
        with self._locations_lock:
            if self._location_fetch_running:
                return
            self._location_fetch_running = True

        def work():
            try:
                before = [l.get("id") for l in self.locations if isinstance(l, dict)]
                self._refresh_locations()
                after = [l.get("id") for l in self.locations if isinstance(l, dict)]
                if before != after:
                    self._sync_scroll()
                    self.invalidate()
            finally:
                with self._locations_lock:
                    self._location_fetch_running = False
                    self._last_location_fetch = time.monotonic()

        threading.Thread(target=work, daemon=True).start()

    def _maybe_retry_locations(self):
        """Solange gar keine Orte bekannt sind, im Hintergrund nachfragen.

        Beim Booten ist der HA-Host oft noch nicht erreichbar; ohne das hier
        bliebe die Liste bis zum naechsten Dienst-Neustart leer.
        """
        # Eine bestaetigt leere Liste ist eine Antwort, kein Grund zum
        # Nachfragen. Nur ein nie geglueckter Abruf wird wiederholt.
        if self.locations or self.locations_known:
            return
        if time.monotonic() - self._last_location_fetch < LOCATION_RETRY_INTERVAL:
            return
        self._refresh_locations_async()

    def _items(self):
        return [{"id": None, "name": "Ohne Ort"}] + list(self.locations)

    def _sync_scroll(self):
        if self.scroll_loc is not None:
            self.scroll_loc.set_content_h(len(self._items()) * self.theme.ROW_H)

    def _apply_start_mode(self):
        mode = str(self.cfg.get("start_mode", "")).strip().lower()
        if mode in ("out", "in"):
            self.mode = mode
            # Einlagern ohne gewaehlten Ort wuerde still auf "Ohne Ort"
            # buchen -- die Navigationstabelle fuehrt hier in die Ortswahl.
            if mode == "in" and self.location is None:
                self._open_locations()
            print("Startmodus: %s" % mode)
        elif mode:
            print("start_mode: '%s' unbekannt (erwartet 'out', 'in' oder leer)" % mode)

    # ---------- Zustandstext ----------

    def state_text(self):
        """Die Zeile unter der Modusleiste. Die Reihenfolge ist Absicht:
        ein fehlender Scanner ist dringender als eine fehlende Verbindung."""
        if not self.scanner_connected:
            return "Scanner nicht verbunden"
        if not self.api_ok:
            return "Keine Verbindung"
        if self.busy:
            return "Scanne…"
        return "Bereit zum " + ("Auslagern" if self.mode == "out" else "Einlagern")

    # ---------- Buchen ----------

    def book(self, barcode, count=1):
        """Setzt count Aufrufe nacheinander ab und legt den Verlaufseintrag an.

        Die API kennt keine Menge, deshalb die Schleife. Bricht ein Aufruf ab,
        endet sie -- der Eintrag traegt dann die tatsaechlich gebuchte Zahl,
        nicht die gewuenschte.
        """
        self.busy = True
        self.progress = (0, count) if count > 1 else None
        booked, status, data, name = 0, None, None, barcode
        for _ in range(count):
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
            if count > 1:
                self.progress = (booked, count)
            self.invalidate()
        self.busy = False
        self.progress = None
        self.multiplier = 1            # faellt immer zurueck, auch bei Abbruch
        self.api_ok = status is not None
        self.touch_activity()

        if booked == 0:
            self.last_entry = None
            self.last_result = self._failure_card(barcode, status, data)
            self.invalidate()
            return None

        entry = self.log.add(barcode, name, self.mode, count=count, booked=booked)
        self.last_entry = entry
        self.last_result = self._success_card(entry, data)
        self.flash_until = time.monotonic() + FLASH_SECONDS
        self.invalidate()
        return entry

    def _success_card(self, entry, data):
        if entry.partial:
            meta = "%d von %d gebucht" % (entry.booked, entry.count)
            kind = "warn"
        elif entry.mode == "out":
            rest = data.get("remaining_quantity", 0) if isinstance(data, dict) else 0
            meta = "Letztes entnommen" if (isinstance(data, dict) and data.get("deleted")) \
                else "noch %d auf Lager" % rest
            kind = "ok"
        else:
            qty = data.get("quantity", 1) if isinstance(data, dict) else 1
            loc = data.get("storage_location") if isinstance(data, dict) else None
            meta = "Menge: %d" % qty
            if isinstance(loc, dict) and loc.get("name"):
                meta += " · " + loc["name"]
            kind = "ok"
        if entry.count > 1 and not entry.partial:
            meta = "%d× · %s" % (entry.count, meta)
        return {"name": entry.name, "meta": meta, "kind": kind, "undoable": True}

    def _failure_card(self, barcode, status, data):
        if status == 404:
            return {"name": barcode, "meta": "Nicht im Inventar",
                    "kind": "warn", "undoable": False}
        if status == 401:
            return {"name": "Auth-Fehler", "meta": "Token prüfen",
                    "kind": "err", "undoable": False}
        if status == 400 and isinstance(data, dict) \
                and data.get("status") == "invalid_storage_location":
            self._refresh_locations_async()
            self.location = None
            self.screen = LOCATIONS
            return {"name": "Ort ungültig", "meta": "Orte werden neu geladen",
                    "kind": "warn", "undoable": False}
        msg = data if isinstance(data, str) else "Keine Verbindung"
        return {"name": "Fehler", "meta": msg, "kind": "err", "undoable": False}

    def undo(self, entry):
        """Gegenbuchung: ein scan_in hebt ein scan_out auf und umgekehrt.

        Keine echte Ruecknahme -- zwischen Scan und Ruecknahme kann jemand
        ueber die Weboberflaeche eingegriffen haben.

        Zwei Dinge muessen ehrlich bleiben, weil die Spezifikation das
        ausdruecklich verlangt. Erstens: schlaegt die Gegenbuchung fehl,
        bleibt der Beleg im Verlauf stehen, mit der verbliebenen Menge --
        sonst waere das Inventar dauerhaft falsch und der einzige Hinweis
        darauf geloescht. Zweitens: war es das letzte Exemplar und der
        Artikel wurde geloescht, legt die Gegenbuchung ihn neu an und der
        Lagerort fehlt.
        """
        if entry is None:
            return
        lost, undone, status = False, 0, 200
        for _ in range(entry.booked):
            if entry.mode == "out":
                status, data = self.api.scan_in(entry.barcode)
                if status == 200 and isinstance(data, dict) and data.get("created"):
                    lost = True
            else:
                status, data = self.api.scan_out(entry.barcode)
            if status != 200:
                break
            undone += 1

        # Nur ein ausgebliebener Status heisst fehlende Verbindung. Ein 404
        # oder 401 kam ueber eine funktionierende Leitung.
        if status is None:
            self.api_ok = False
        elif undone:
            self.api_ok = True

        entry.location_lost = lost
        if undone >= entry.booked:
            self.log.remove(entry)
            self.last_entry = None
            meta = "wiederhergestellt, Lagerort fehlt" if lost else "zurückgenommen"
            kind = "warn" if lost else "ok"
        else:
            entry.booked -= undone
            meta = "%d von %d zurückgenommen" % (undone, undone + entry.booked)
            kind = "warn"
        self.last_result = {"name": entry.name, "meta": meta,
                            "kind": kind, "undoable": False}
        self.touch_activity()
        self.invalidate()

    # ---------- Leerlauf ----------

    def touch_activity(self):
        self.last_activity = time.monotonic()

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
        self.last_entry = None
        self.screen = SCAN
        self.last_activity = now
        self.invalidate()
        return True

    # ---------- Zeichnen ----------

    def invalidate(self):
        self._dirty = True

    def _flash_colour(self):
        """Blendet die Aufleuchtfarbe ueber FLASH_SECONDS zur Kartenfarbe
        zurueck. Vorher war es eine konstante Flaeche mit hartem Sprung am
        Ende -- und weil die Schleife danach bis zu 0,25 s auf der
        Warteschlange stand, dauerte es real fast eine halbe Sekunde.
        """
        rest = self.flash_until - time.monotonic()
        if rest <= 0:
            return None
        anteil = max(0.0, min(1.0, rest / FLASH_SECONDS))
        von = self.theme.FLASH_IN if self.mode == "in" else self.theme.FLASH_OUT
        nach = self.theme.SURFACE
        return tuple(int(n + (v - n) * anteil) for v, n in zip(von, nach))

    def _state(self):
        return {
            "mode": self.mode, "location": self.location,
            "status": self.state_text(), "multiplier": self.multiplier,
            "api_ok": self.api_ok, "result": self.last_result,
            "card_bg": self._flash_colour(),
            "items": self._items(), "scroll": self._scroll(),
            "scrolling": self._scroll() is not None and (
                self._scroll().is_dragging
                or abs(self._scroll().velocity) > 0
                or self._scroll().offset != round(self._scroll().offset)),
            "entries": self.log.entries, "now": time.monotonic(),
            "progress": self.progress,
            "selected_id": self.location["id"] if self.location else None,
        }

    def render(self):
        img = self.display.new_frame()
        draw = ImageDraw.Draw(img)
        self._rects = {}
        state = self._state()
        # Die Liste festhalten, aus der die Rechtecke entstanden sind. Ein
        # Hintergrund-Abruf kann self.locations zwischen Zeichnen und
        # Beruehrung ersetzen -- dann zeigt derselbe Index auf einen anderen
        # Ort oder gar keinen mehr.
        self._rendered_items = state["items"]
        if self.screen == LOCATIONS:
            self.screens.locations(draw, state, self._rects)
        elif self.screen == HISTORY:
            self.screens.history(draw, state, self._rects)
        elif self.screen == MULT:
            self.screens.scan(draw, state, self._rects)
            # Das Raster deckt den Scan-Bildschirm vollstaendig ab. Ohne das
            # Leeren blieben dessen Trefferflaechen aktiv und ein Tipp auf
            # eine Mengenkachel haette "Rueckgaengig" ausgeloest.
            self._rects = {}
            self.screens.multiplier_sheet(draw, self._rects)
        else:
            self.screens.scan(draw, state, self._rects)
        self.display.flush(img)

    # ---------- Eingaben ----------

    def handle_touch(self, px, py, kind):
        if self.display.wake():
            self._swallow = True          # Aufwecker loest nichts aus
        if self._swallow:
            if kind == "touch_up":
                self._swallow = False
                sv = self._scroll()
                if sv is not None:
                    sv.on_up(time.monotonic())   # Ziehzustand aufraeumen
            return
        self.touch_activity()

        sv = self._scroll()
        if sv is not None:
            now = time.monotonic()
            if kind == "touch_move":
                if sv.on_move(py, now):
                    self.invalidate()
                return
            sv.on_up(now)
            if sv.was_drag:
                self.invalidate()
                return

        if kind != "touch_up":
            return

        r = self._rects
        if hit(r.get("mode_out"), px, py):
            self.mode = "out"
            self.screen = SCAN
        elif hit(r.get("mode_in"), px, py):
            self.mode = "in"
            self.screen = SCAN if self.location else LOCATIONS
            if self.screen == LOCATIONS:
                self._open_locations()
        elif hit(r.get("hist"), px, py):
            self._open_history()
        elif hit(r.get("back"), px, py):
            self.screen = SCAN
        elif hit(r.get("loc"), px, py):
            self._open_locations()
        elif hit(r.get("undo"), px, py):
            self.undo(self.last_entry)
        elif hit(r.get("mult"), px, py):
            self.screen = MULT
        elif self.screen == MULT:
            for i, rect in enumerate(r.get("mcells", [])):
                if hit(rect, px, py):
                    self.multiplier = i + 1
                    break
            self.screen = SCAN          # auch ein Danebentippen schliesst
        elif self.screen == LOCATIONS:
            for i, rect in enumerate(r.get("rows", [])):
                if hit(rect, px, py):
                    items = getattr(self, "_rendered_items", self._items())
                    if i >= len(items):
                        break
                    item = items[i]
                    self.location = None if item["id"] is None else item
                    self.mode = "in"
                    self.screen = SCAN
                    break
        elif self.screen == HISTORY:
            for i, rect in enumerate(r.get("hrows", [])):
                if hit(rect, px, py):
                    entries = self.log.entries
                    if i < len(entries):
                        self.undo(entries[i])
                        self.screen = SCAN
                    break
        self.invalidate()

    def _scroll(self):
        """Der Scrollstand des gerade sichtbaren Bildschirms."""
        if self.screen == LOCATIONS:
            return self.scroll_loc
        if self.screen == HISTORY:
            return self.scroll_hist
        return None

    def _open_history(self):
        self.screen = HISTORY
        y0 = self.theme.HEADER_H
        n = max(1, len(self.log.entries))
        if self.scroll_hist is None:
            self.scroll_hist = ScrollView(view_h=self.theme.height - y0,
                                          content_h=n * self.theme.ROW_H)
        else:
            self.scroll_hist.set_content_h(n * self.theme.ROW_H)

    def _open_locations(self):
        """Liste oeffnen und dabei den Scrollstand behalten.

        Ein Fehlgriff kostete sonst nicht nur einen zweiten Tipp, sondern das
        erneute Herunterscrollen -- die Liste sprang jedes Mal nach oben.
        """
        self.screen = LOCATIONS
        y0 = self.theme.HEADER_H
        if self.scroll_loc is None:
            self.scroll_loc = ScrollView(view_h=self.theme.height - y0,
                                         content_h=len(self._items()) * self.theme.ROW_H)
        else:
            self._sync_scroll()
        self._refresh_locations_async()

    def handle_touch_down(self, py):
        # Nicht waehrend einer Aufweck-Beruehrung ziehen: sonst startet hier
        # on_down, das zugehoerige touch_up wird verschluckt, und is_dragging
        # bleibt dauerhaft True -- die Liste federt dann nie zurueck.
        if self._swallow:
            return
        sv = self._scroll()
        if sv is not None:
            sv.on_down(py, time.monotonic())

    def handle_barcode(self, barcode):
        """Nimmt den Scan an und gibt die Buchung an einen Thread ab.

        Frueher lief book() hier im Schleifen-Thread. Bei x12 auf eine lahme
        Verbindung stand das Display minutenlang still, keine Beruehrung kam
        durch, und die gestauten Ereignisse wurden danach gegen ein veraltetes
        Layout abgespielt.
        """
        self.display.wake()
        self.touch_activity()
        if self.booking:
            return                       # eine Buchung reicht
        if self.screen != SCAN:
            self.screen = SCAN
        anzahl = max(1, self.multiplier)
        self.booking = True
        self.busy = True
        self.progress = (0, anzahl) if anzahl > 1 else None
        self.invalidate()

        def arbeiten():
            try:
                self.book(barcode, anzahl)
            finally:
                self.booking = False
                self.busy = False
                self.progress = None
                self.invalidate()

        threading.Thread(target=arbeiten, daemon=True).start()

    def handle_scanner_state(self, connected):
        if connected != self.scanner_connected:
            self.scanner_connected = connected
            self.invalidate()

    # ---------- Bildschleife ----------

    def _safe_handle(self, event):
        """Ein unerwarteter Fehler darf das Geraet nicht abschalten.

        Frueher beendete jede Ausnahme in _handle oder render den Prozess;
        systemd startete neu, und Modus, Lagerort und Verlauf waren weg.
        """
        try:
            self._handle(event)
        except Exception as e:                      # noqa: BLE001
            print("Fehler bei %r: %s" % (event[0], e))
            self.last_result = {"name": "Fehler", "meta": str(e)[:60],
                                "kind": "err", "undoable": False}
            self.invalidate()

    def _drain_input(self):
        while True:
            try:
                event = self.event_queue.get_nowait()
            except queue.Empty:
                return
            self._safe_handle(event)

    def _handle(self, event):
        if event[0] == "barcode":
            self.handle_barcode(event[1])
        elif event[0] == "scanner":
            self.handle_scanner_state(event[1])
        elif event[0] == "touch_down":
            self.handle_touch_down(event[2])
        elif event[0] in ("touch_up", "touch_move"):
            self.handle_touch(event[1], event[2], event[0])

    def _advance(self, dt, now):
        """Zeitgeber und Animationen. True, solange etwas in Bewegung ist."""
        moving = bool(self.booking)
        self.display.tick_backlight(now)
        if self.flash_until and now < self.flash_until:
            moving = True
            self.invalidate()
        elif self.flash_until:
            self.flash_until = 0.0
            self.invalidate()
        sv = self._scroll()
        if sv is not None:
            if sv.advance(dt):
                moving = True
                self.invalidate()
        self._check_idle(now)
        return moving

    def run(self):
        threading.Thread(target=barcode_reader, daemon=True,
                         args=(self.cfg["input_device"], self.event_queue)).start()
        threading.Thread(target=touch_reader, daemon=True,
                         args=(self.cfg["touch_device"], self.event_queue, self.cfg)).start()
        self.display.wake()

        print("Scanner client gestartet")
        print("API: %s" % self.cfg["api_url"])
        print("Scanner: %s" % self.cfg["input_device"])
        print("Touch: %s" % self.cfg["touch_device"])
        print("Locations: %d" % len(self.locations))

        last = time.monotonic()
        frames, fps_since = 0, last
        while True:
            now = time.monotonic()
            dt = now - last
            last = now

            self._drain_input()
            animating = self._advance(dt, now)
            self._maybe_retry_locations()

            if self._dirty:
                try:
                    self.render()
                except Exception as e:              # noqa: BLE001
                    print("Fehler beim Zeichnen: %s" % e)
                self._dirty = False
                frames += 1

            if animating and now - fps_since >= 1.0:
                print("fps: %.1f" % (frames / (now - fps_since)))
                frames, fps_since = 0, now

            if animating:
                rest = FRAME_SECONDS - (time.monotonic() - now)
                if rest > 0:
                    time.sleep(rest)
            else:
                # Im Ruhezustand auf Ereignisse warten statt 30-mal pro
                # Sekunde nichts zu tun.
                try:
                    self._safe_handle(self.event_queue.get(timeout=0.25))
                except queue.Empty:
                    pass
                fps_since = time.monotonic()
                frames = 0
