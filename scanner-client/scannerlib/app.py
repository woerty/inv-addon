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
FRAME_SECONDS = 1.0 / FPS
RESULT_SECONDS = 4.0
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
        self.theme = Theme(cfg["screen_width"])
        self.theme.height = cfg["screen_height"]
        self.screens = Screens(self.theme)
        self.api = API(cfg["api_url"], cfg["scanner_token"])
        self.event_queue = queue.Queue()
        self.log = ScanLog()

        self.screen = SCAN
        self.mode = "out"
        self.location = None
        self.locations = []
        self.multiplier = 1
        self.api_ok = True
        self.scanner_connected = True
        self.busy = False
        self.last_result = None      # dict fuer die Karte
        self.last_entry = None       # zugehoeriger ScanEntry, fuer Rueckgaengig
        self.result_deadline = None
        self.card_bg = None
        self.idle_reset_s = int(cfg.get("idle_reset_minutes", 10)) * 60
        self.last_activity = time.monotonic()

        self.scroll = None
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
        data = self.api.get_locations()
        if data and isinstance(data, list):
            self.locations = data
            self.api_ok = True
        elif data and isinstance(data, dict) and "locations" in data:
            self.locations = data["locations"]
            self.api_ok = True
        else:
            self.api_ok = False
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
        if self.locations:
            return
        if time.monotonic() - self._last_location_fetch < LOCATION_RETRY_INTERVAL:
            return
        self._refresh_locations_async()

    def _items(self):
        return [{"id": None, "name": "Ohne Ort"}] + list(self.locations)

    def _sync_scroll(self):
        if self.scroll is not None:
            self.scroll.set_content_h(len(self._items()) * self.theme.ROW_H)

    def _apply_start_mode(self):
        mode = str(self.cfg.get("start_mode", "")).strip().lower()
        if mode in ("out", "in"):
            self.mode = mode
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
            self.invalidate()
        self.busy = False
        self.multiplier = 1            # faellt immer zurueck, auch bei Abbruch
        self.api_ok = status is not None
        self.touch_activity()

        if booked == 0:
            self.last_entry = None
            self.last_result = self._failure_card(barcode, status, data)
            self.result_deadline = None
            self.invalidate()
            return None

        entry = self.log.add(barcode, name, self.mode, count=count, booked=booked)
        self.last_entry = entry
        self.last_result = self._success_card(entry, data)
        self.card_bg = (0x1F, 0x2E, 0x26)
        self.result_deadline = time.monotonic() + 0.22   # kurzes Aufleuchten
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

    def _state(self):
        return {
            "mode": self.mode, "location": self.location,
            "status": self.state_text(), "multiplier": self.multiplier,
            "api_ok": self.api_ok, "result": self.last_result,
            "card_bg": self.card_bg,
            "items": self._items(), "scroll": self.scroll,
            "scrolling": self.scroll is not None and (
                self.scroll.is_dragging or abs(self.scroll.velocity) > 0),
            "entries": self.log.entries, "now": time.monotonic(),
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
                if self.scroll is not None:
                    self.scroll.on_up(time.monotonic())   # Ziehzustand aufraeumen
            return
        self.touch_activity()

        if self.screen == LOCATIONS and self.scroll is not None:
            now = time.monotonic()
            if kind == "touch_move":
                if self.scroll.on_move(py, now):
                    self.invalidate()
                return
            self.scroll.on_up(now)
            if self.scroll.was_drag:
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
            self.screen = HISTORY
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

    def _open_locations(self):
        """Liste oeffnen und dabei den Scrollstand behalten.

        Ein Fehlgriff kostete sonst nicht nur einen zweiten Tipp, sondern das
        erneute Herunterscrollen -- die Liste sprang jedes Mal nach oben.
        """
        self.screen = LOCATIONS
        y0 = self.theme.HEADER_H
        if self.scroll is None:
            self.scroll = ScrollView(view_h=self.theme.height - y0,
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
        if self.screen == LOCATIONS and self.scroll is not None:
            self.scroll.on_down(py, time.monotonic())

    def handle_barcode(self, barcode):
        self.display.wake()
        self.touch_activity()
        if self.screen != SCAN:
            self.screen = SCAN
        self.busy = True
        self.invalidate()
        self.render()
        self.book(barcode, max(1, self.multiplier))

    def handle_scanner_state(self, connected):
        if connected != self.scanner_connected:
            self.scanner_connected = connected
            self.invalidate()

    # ---------- Bildschleife ----------

    def _drain_input(self):
        while True:
            try:
                event = self.event_queue.get_nowait()
            except queue.Empty:
                return
            self._handle(event)

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
        moving = False
        self.display.tick_backlight(now)
        if self.result_deadline is not None and now >= self.result_deadline:
            self.result_deadline = None
            self.card_bg = None
            self.invalidate()
        if self.screen == LOCATIONS and self.scroll is not None:
            if self.scroll.advance(dt):
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
                self.render()
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
                    self._handle(self.event_queue.get(timeout=0.25))
                except queue.Empty:
                    pass
                fps_since = time.monotonic()
                frames = 0
