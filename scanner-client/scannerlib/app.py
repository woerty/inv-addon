"""Zustand, Ereignisbehandlung und Hauptschleife."""
import queue
import threading
import time

from PIL import ImageDraw

from .api import API
from .display import Display, hit
from .inputs import barcode_reader, touch_reader


# --- Screens ---

# Solange keine Lagerorte bekannt sind, im Hintergrund erneut versuchen.
# Beim Booten ist der HA-Host oft noch nicht erreichbar.
LOCATION_RETRY_INTERVAL = 30.0

# Bildrate waehrend Animationen. Gemessen: ein Vollbild kostet 19,4 ms,
# das Budget sind 33,3 ms.
FPS = 30
FRAME_SECONDS = 1.0 / FPS
RESULT_SECONDS = 4.0

# Mindeststrecke fuer einen Wisch, in echten Bildschirmpixeln. Der
# kapazitive Touch zittert kaum, deshalb reicht ein kleiner Wert --
# er muss nur unter der Zeilenhoehe der Lagerortliste bleiben.
DRAG_THRESHOLD = 25

MODE_SELECT = "mode_select"
LOCATION_SELECT = "location_select"
SCANNING = "scanning"
RESULT = "result"


class App:
    def __init__(self, cfg):
        self.cfg = cfg
        self.display = Display(
            cfg["fb_device"], cfg["screen_width"], cfg["screen_height"],
            cfg["backlight"], cfg["backlight_timeout"],
            rotate=cfg.get("fb_rotate", 0),
        )
        self.api = API(cfg["api_url"], cfg["scanner_token"])
        self.event_queue = queue.Queue()

        # State
        self.screen = MODE_SELECT
        self.mode = None
        self.location = None
        self.locations = []
        self.scroll_offset = 0
        self.touch_start_y = None
        self.touch_start_y_initial = None
        self.is_dragging = False
        self._swallow_gesture = False
        self.result_deadline = None
        self.last_result = None

        self._render_lock = threading.Lock()
        self._locations_lock = threading.Lock()
        self._location_fetch_running = False

        self._refresh_locations()
        self._last_location_fetch = time.monotonic()
        self._apply_start_mode()

    def _apply_start_mode(self):
        """Laut scanner.conf direkt in einen Modus starten.

        Das Geraet haengt an der Wand -- ohne das hier muss jemand erst
        koerperlich "Auslagern" antippen, auch wenn ohnehin immer
        ausgescannt wird.
        """
        mode = str(self.cfg.get("start_mode", "")).strip().lower()
        if not mode:
            return
        if mode == "out":
            self.mode = "out"
            self.screen = SCANNING
        elif mode == "in":
            self.mode = "in"
            self.screen = LOCATION_SELECT
        else:
            print(f"start_mode: '{mode}' unbekannt "
                  f"(erwartet 'out', 'in' oder leer) -- ignoriert")
            return
        print(f"Startmodus: {mode}")

    def _refresh_locations(self):
        data = self.api.get_locations()
        if data and isinstance(data, list):
            self.locations = data
        elif data and isinstance(data, dict) and "locations" in data:
            self.locations = data["locations"]
        print(f"Locations loaded: {len(self.locations)}")

    def _refresh_locations_async(self):
        """Lagerorte im Hintergrund holen; zeichnet neu, wenn sie sich aendern.

        Nicht blockierend, damit die Liste sofort mit dem bisherigen Stand
        erscheint und sich nachtraeglich aktualisiert.
        """
        with self._locations_lock:
            if self._location_fetch_running:
                return
            self._location_fetch_running = True

        def work():
            try:
                before = [l.get("id") for l in self.locations if isinstance(l, dict)]
                self._refresh_locations()
                after = [l.get("id") for l in self.locations if isinstance(l, dict)]
                if before != after and self.screen == LOCATION_SELECT:
                    self.render()
            finally:
                with self._locations_lock:
                    self._location_fetch_running = False
                    self._last_location_fetch = time.monotonic()

        threading.Thread(target=work, daemon=True).start()

    def _maybe_retry_locations(self):
        """Periodischer Versuch, solange ueberhaupt keine Orte bekannt sind."""
        if self.locations:
            return
        if time.monotonic() - self._last_location_fetch < LOCATION_RETRY_INTERVAL:
            return
        self._refresh_locations_async()

    # --- Rendering ---

    def render(self):
        # Auch Hintergrund-Threads zeichnen (Nachladen, Ergebnis-Timeout);
        # ohne Sperre schreiben zwei Threads gleichzeitig in den Framebuffer.
        with self._render_lock:
            self._render()

    def _render(self):
        if self.screen == MODE_SELECT:
            self._render_mode_select()
        elif self.screen == LOCATION_SELECT:
            self._render_location_select()
        elif self.screen == SCANNING:
            self._render_scanning()
        elif self.screen == RESULT:
            self._render_result()

    def _render_mode_select(self):
        d = self.display
        img = d.new_frame()
        draw = ImageDraw.Draw(img)

        d.center_text(draw, "Modus wählen", d.font_medium, d.GRAY, 15)

        self._btn_out = d.draw_button(draw, 20, 55, 280, 70,
                                       "Auslagern", d.ORANGE)
        self._btn_in = d.draw_button(draw, 20, 145, 280, 70,
                                      "Einlagern", d.GREEN)
        d.flush(img)

    def _render_location_select(self):
        d = self.display
        img = d.new_frame()
        draw = ImageDraw.Draw(img)

        self._btn_back = d.draw_back_button(draw)
        d.center_text(draw, "Lagerort", d.font_medium, d.GRAY, 10)

        list_top = d._s(42)
        list_bottom = d.height
        item_h = d._s(44)
        visible_h = list_bottom - list_top

        items = [{"id": None, "name": "Ohne Ort"}] + self.locations
        total_h = len(items) * item_h

        max_scroll = max(0, total_h - visible_h)
        self.scroll_offset = max(0, min(self.scroll_offset, max_scroll))

        self._location_rects = []
        for i, loc in enumerate(items):
            y = list_top + i * item_h - self.scroll_offset
            if y + item_h < list_top or y > list_bottom:
                self._location_rects.append(None)
                continue
            vy = max(y, list_top)
            vh = min(y + item_h, list_bottom) - vy
            if vh <= 0:
                self._location_rects.append(None)
                continue

            bg = d.DARK_GRAY if i % 2 == 0 else d.BG
            draw.rectangle((0, vy, d.width, vy + vh), fill=bg)
            draw.line((d._s(10), vy + vh - 1, d.width - d._s(10), vy + vh - 1),
                      fill=(40, 40, 55))

            name = loc["name"] if isinstance(loc, dict) else str(loc)
            color = d.CYAN if loc["id"] is None else d.WHITE
            bbox = draw.textbbox((0, 0), name, font=d.font_medium)
            th = bbox[3] - bbox[1]
            ty = y + (item_h - th) // 2
            if list_top <= ty < list_bottom - th:
                draw.text((d._s(20), ty), name, fill=color, font=d.font_medium)

            self._location_rects.append((0, vy, d.width, vy + vh, loc))

        if total_h > visible_h:
            sb_h = max(d._s(20), int(visible_h * visible_h / total_h))
            sb_y = list_top + int(self.scroll_offset / total_h * visible_h)
            draw.rectangle((d.width - d._s(4), sb_y, d.width - 1, sb_y + sb_h),
                           fill=d.GRAY)

        d.flush(img)

    def _render_scanning(self):
        d = self.display
        img = d.new_frame()
        draw = ImageDraw.Draw(img)

        self._btn_back = d.draw_back_button(draw)

        if self.mode == "out":
            d.center_text(draw, "Auslagern", d.font_large, d.ORANGE, 50)
        else:
            d.center_text(draw, "Einlagern", d.font_large, d.GREEN, 40)
            if self.location and self.location["id"] is not None:
                d.center_text(draw, self.location["name"],
                              d.font_medium, d.CYAN, 80)
            else:
                d.center_text(draw, "Ohne Ort",
                              d.font_medium, d.GRAY, 80)

        y_ready = 130 if self.mode == "in" else 110
        d.center_text(draw, "Bereit", d.font_medium, d.GREEN, y_ready)
        d.center_text(draw, "Barcode scannen...", d.font_small, d.GRAY,
                      y_ready + 30)
        d.flush(img)

    def _render_result(self):
        if self.last_result is None:
            return
        d = self.display
        img = d.new_frame()
        draw = ImageDraw.Draw(img)

        status, data, mode = self.last_result

        if status == 200:
            if mode == "out":
                deleted = data.get("deleted", False)
                name = data.get("name", "?")
                remaining = data.get("remaining_quantity", 0)
                if deleted:
                    d.center_text(draw, "Letztes entfernt",
                                  d.font_large, d.ORANGE, 30)
                else:
                    d.center_text(draw, "Entnommen",
                                  d.font_large, d.GREEN, 30)
                y = d.wrap_text(draw, name, d.font_medium, d.WHITE, 80)
                if not deleted:
                    d.center_text(draw, f"Noch {remaining} auf Lager",
                                  d.font_medium, d.GRAY, y + 10)
                else:
                    d.center_text(draw, "Aus Inventar gelöscht",
                                  d.font_small, d.YELLOW, y + 10)
            else:
                name = data.get("name", "?")
                qty = data.get("quantity", 1)
                loc = data.get("storage_location")
                created = data.get("created", False)
                if created:
                    d.center_text(draw, "Neu angelegt",
                                  d.font_large, d.GREEN, 30)
                else:
                    d.center_text(draw, "Eingelagert",
                                  d.font_large, d.GREEN, 30)
                y = d.wrap_text(draw, name, d.font_medium, d.WHITE, 80)
                d.center_text(draw, f"Menge: {qty}",
                              d.font_medium, d.GRAY, y + 10)
                if loc and isinstance(loc, dict) and loc.get("name"):
                    d.center_text(draw, loc["name"],
                                  d.font_small, d.CYAN, y + 38)
                elif loc and isinstance(loc, str):
                    d.center_text(draw, loc,
                                  d.font_small, d.CYAN, y + 38)

        elif status == 404:
            barcode = data.get("barcode", "?") if isinstance(data, dict) else "?"
            d.center_text(draw, "Unbekannt", d.font_large, d.YELLOW, 70)
            d.center_text(draw, barcode, d.font_small, d.GRAY, 120)
            d.center_text(draw, "Nicht im Inventar",
                          d.font_medium, d.YELLOW, 155)

        elif status == 400:
            err_status = data.get("status", "") if isinstance(data, dict) else ""
            if err_status == "invalid_storage_location":
                d.center_text(draw, "Ort ungültig", d.font_large, d.YELLOW, 60)
                d.center_text(draw, "Orte neu laden...",
                              d.font_medium, d.GRAY, 110)
            else:
                msg = data.get("error", "Bad Request") if isinstance(data, dict) else str(data)
                d.center_text(draw, "Fehler", d.font_large, d.RED, 60)
                d.wrap_text(draw, msg, d.font_small, d.WHITE, 110)

        elif status == 401:
            d.center_text(draw, "Auth-Fehler", d.font_large, d.RED, 60)
            d.center_text(draw, "Token prüfen!",
                          d.font_medium, d.WHITE, 110)

        else:
            msg = data if isinstance(data, str) else str(data)
            d.center_text(draw, "Fehler", d.font_large, d.RED, 60)
            d.wrap_text(draw, msg, d.font_small, d.WHITE, 110)

        d.flush(img)

    # --- Event handling ---

    def handle_touch(self, px, py, event_type):
        if self.display.wake():
            # Der Aufwecker darf nichts ausloesen. Es reicht nicht, nur dieses
            # eine Event zu verwerfen: vor dem touch_up kommen bereits
            # touch_move-Events, sonst faellt das touch_up durch und drueckt
            # den Knopf unter dem Finger.
            self._swallow_gesture = True
        if self._swallow_gesture:
            if event_type == "touch_up":
                self._swallow_gesture = False
                self.touch_start_y = None
                self.touch_start_y_initial = None
                self.is_dragging = False
            return

        if event_type == "touch_move":
            if self.screen == LOCATION_SELECT:
                if self.touch_start_y_initial is None:
                    self.touch_start_y_initial = py
                    self.touch_start_y = py
                elif not self.is_dragging:
                    # Erst ab einer Strecke deutlich ueber dem Panel-Rauschen
                    # als Wisch werten -- sonst scrollt die Liste schon beim
                    # blossen Antippen unter dem Finger weg.
                    if abs(py - self.touch_start_y_initial) > DRAG_THRESHOLD:
                        self.is_dragging = True
                        self.touch_start_y = py
                else:
                    delta = self.touch_start_y - py
                    if delta:
                        self.scroll_offset += delta
                        self.touch_start_y = py
                        self.render()
            return

        if event_type == "touch_up":
            was_dragging = self.is_dragging
            self.touch_start_y = None
            self.touch_start_y_initial = None
            self.is_dragging = False

            if self.screen == MODE_SELECT:
                if hit(self._btn_out, px, py):
                    self.mode = "out"
                    self.location = None
                    self.screen = SCANNING
                    self.render()
                elif hit(self._btn_in, px, py):
                    self.mode = "in"
                    self.scroll_offset = 0
                    self.screen = LOCATION_SELECT
                    self.render()
                    # Inzwischen in der Weboberflaeche angelegte Orte holen.
                    # Neue Orte erzeugen nie einen Fehler, tauchen also sonst
                    # bis zum naechsten Dienst-Neustart nicht auf.
                    self._refresh_locations_async()

            elif self.screen == LOCATION_SELECT:
                if hit(self._btn_back, px, py):
                    self.screen = MODE_SELECT
                    self.render()
                elif not was_dragging:
                    for rect_data in self._location_rects:
                        if rect_data is None:
                            continue
                        rx, ry, rx2, ry2, loc = rect_data
                        if hit((rx, ry, rx2, ry2), px, py):
                            self.location = loc
                            self.screen = SCANNING
                            self.render()
                            break

            elif self.screen == SCANNING:
                if hit(self._btn_back, px, py):
                    self.screen = MODE_SELECT
                    self.render()

            elif self.screen == RESULT:
                self.result_deadline = None
                self.screen = SCANNING
                self.render()

    def handle_barcode(self, barcode):
        self.display.wake()

        if self.screen not in (SCANNING, RESULT):
            return

        self.result_deadline = None

        d = self.display
        img = d.new_frame()
        draw = ImageDraw.Draw(img)
        d.center_text(draw, "Scanne...", d.font_large, d.BLUE, 80)
        d.center_text(draw, barcode, d.font_small, d.GRAY, 130)
        d.flush(img)

        if self.mode == "out":
            status, data = self.api.scan_out(barcode)
        else:
            loc_id = self.location["id"] if self.location else None
            status, data = self.api.scan_in(barcode, loc_id)

        if (status == 400 and isinstance(data, dict)
                and data.get("status") == "invalid_storage_location"):
            self._refresh_locations_async()

        self.last_result = (status, data, self.mode)
        self.screen = RESULT
        self.render()

        self.result_deadline = time.monotonic() + RESULT_SECONDS


    # --- Bildschleife ---

    def invalidate(self):
        """Naechstes Bild neu zeichnen. Ersetzt die render()-Aufrufe, die
        bisher als Nebenwirkung ueberall verstreut waren."""
        self._dirty = True

    def _drain_input(self):
        """Alles Wartende abholen, ohne zu blockieren."""
        got = False
        while True:
            try:
                event = self.event_queue.get_nowait()
            except queue.Empty:
                return got
            got = True
            self._handle(event)

    def _handle(self, event):
        if event[0] == "barcode":
            self.handle_barcode(event[1])
        elif event[0] in ("touch_up", "touch_move"):
            self.handle_touch(event[1], event[2], event[0])

    def _advance(self, dt, now):
        """Zeitgeber und Animationen. True, solange etwas in Bewegung ist."""
        moving = False
        if self.display.tick_backlight(now):
            pass                      # nur ausschalten, kein Neuzeichnen noetig
        if self.result_deadline is not None and now >= self.result_deadline:
            self.result_deadline = None
            self.screen = SCANNING
            self.invalidate()
        return moving

    def run(self):
        self._btn_out = (0, 0, 0, 0)
        self._btn_in = (0, 0, 0, 0)
        self._btn_back = (0, 0, 0, 0)
        self._location_rects = []
        self._dirty = True

        t_barcode = threading.Thread(
            target=barcode_reader,
            args=(self.cfg["input_device"], self.event_queue),
            daemon=True,
        )
        t_touch = threading.Thread(
            target=touch_reader,
            args=(self.cfg["touch_device"], self.event_queue, self.cfg),
            daemon=True,
        )
        t_barcode.start()
        t_touch.start()

        self.display.wake()

        print("Scanner client gestartet")
        print(f"API: {self.cfg['api_url']}")
        print(f"Scanner: {self.cfg['input_device']}")
        print(f"Touch: {self.cfg['touch_device']}")
        print(f"Locations: {len(self.locations)}")

        last = time.monotonic()
        frames, fps_since = 0, last
        while True:
            now = time.monotonic()
            dt = now - last
            last = now

            self._drain_input()
            animating = self._advance(dt, now)
            self._maybe_retry_locations()

            if self._dirty or animating:
                self.render()
                self._dirty = False
                frames += 1

            if animating and now - fps_since >= 1.0:
                print("fps: %.1f" % (frames / (now - fps_since)))
                frames, fps_since = 0, now

            rest = FRAME_SECONDS - (time.monotonic() - now)
            if animating:
                if rest > 0:
                    time.sleep(rest)
            else:
                # Im Ruhezustand nicht heisslaufen: auf das naechste Ereignis
                # warten statt 30-mal pro Sekunde nichts zu tun.
                try:
                    event = self.event_queue.get(timeout=0.25)
                except queue.Empty:
                    continue
                self._handle(event)
