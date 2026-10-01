"""Framebuffer und Hintergrundbeleuchtung.

Nur das Geraet. Farben, Schriften und Zeichenhelfer liegen in theme.py und
screens.py -- diese Datei trug nach der Aufteilung noch die komplette alte
Zeichenschicht mit, darunter ein zweites `hit()` ohne Null-Pruefung, das
bei einem falschen Import still abgestuerzt waere.
"""
import time
from pathlib import Path

import numpy as np
from PIL import Image


def to_rgb565_rotated(img, rotate, _force_fallback=False):
    """Querbild -> Bytes fuer den hochkanten Framebuffer.

    Gemessen auf dem Pi 3A+: der PIL-Weg kostet 8,3 ms, der numpy-Weg
    15,4 ms; beide liefern dieselben Bytes. BGR;16 ist in Pillow als
    veraltet markiert und soll in Version 12 entfallen -- faellt es weg,
    greift der Rueckfall und es wird langsamer, nicht kaputt.
    """
    buf = None
    if not _force_fallback:
        try:
            raw = img.convert("BGR;16").tobytes()
            buf = np.frombuffer(raw, dtype=np.uint16).reshape(img.height, img.width)
        except (ValueError, KeyError, OSError):
            buf = None
    if buf is None:
        a = np.asarray(img)
        r = (a[:, :, 0].astype(np.uint16) >> 3) << 11
        g = (a[:, :, 1].astype(np.uint16) >> 2) << 5
        b = a[:, :, 2].astype(np.uint16) >> 3
        buf = r | g | b
    if rotate:
        buf = np.rot90(buf, rotate // 90)
    return np.ascontiguousarray(buf).tobytes()


class Display:
    BG = (0x0E, 0x10, 0x14)

    def __init__(self, fb_device, width, height, backlight_path,
                 backlight_timeout, rotate=0):
        self.fb_device = fb_device
        self.width = width
        self.height = height
        self.rotate = rotate
        self.backlight_path = backlight_path
        self.backlight_timeout = backlight_timeout
        self._bl_deadline = None
        self._is_off = False
        self._fb = None

    # --- Bild ---

    def new_frame(self):
        return Image.new("RGB", (self.width, self.height), self.BG)

    def flush(self, img):
        """Bild in den Framebuffer. Der Dateizeiger bleibt offen -- ihn pro
        Bild zu oeffnen kostete bei 30 fps unnoetig Systemaufrufe."""
        data = to_rgb565_rotated(img, self.rotate)
        if self._fb is None:
            self._fb = open(self.fb_device, "wb", buffering=0)
        self._fb.seek(0)
        self._fb.write(data)

    # --- Beleuchtung ---

    def _write_backlight(self, value):
        try:
            Path(self.backlight_path).write_text(value)
        except OSError:
            pass

    def backlight_on(self):
        self._write_backlight("0")

    def backlight_off(self):
        self._write_backlight("1")

    def wake(self):
        """Beleuchtung an, Ablaufzeit neu setzen. True, wenn sie aus war.

        Kein threading.Timer -- die Bildschleife prueft den Zeitpunkt. Das
        spart einen Thread, der bisher nebenlaeufig gezeichnet hat.
        """
        was_off = self._is_off
        self._is_off = False
        self.backlight_on()
        self._bl_deadline = time.monotonic() + self.backlight_timeout
        return was_off

    def tick_backlight(self, now):
        """Von der Bildschleife aufgerufen. True, wenn gerade abgeschaltet wurde."""
        if self._is_off or self._bl_deadline is None:
            return False
        if now < self._bl_deadline:
            return False
        self._is_off = True
        self.backlight_off()
        self._bl_deadline = None
        return True
