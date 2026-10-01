"""Framebuffer, Hintergrundbeleuchtung, Zeichenhelfer."""
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def to_rgb565_rotated(img, rotate, _force_fallback=False):
    """Querbild -> Bytes fuer den hochkanten Framebuffer.

    Gemessen auf dem Pi 3A+: der PIL-Weg kostet 8,3 ms, der numpy-Weg 15,4 ms;
    beide liefern dieselben Bytes. BGR;16 ist in Pillow als veraltet markiert
    und soll in Version 12 entfallen -- faellt es weg, greift der Rueckfall
    und es wird langsamer, nicht kaputt.
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
    # Colors
    BG = (20, 20, 30)
    WHITE = (255, 255, 255)
    GREEN = (80, 220, 120)
    RED = (220, 80, 80)
    YELLOW = (240, 200, 60)
    GRAY = (120, 120, 140)
    DARK_GRAY = (50, 50, 65)
    ORANGE = (240, 160, 50)
    BLUE = (80, 140, 240)
    CYAN = (80, 200, 220)

    # Das Layout wurde fuer 320x240 entworfen. Alle Zahlen in den
    # Render-Methoden bleiben in diesen logischen Einheiten; skaliert wird
    # zentral hier, damit ein groesseres Panel nicht jede Koordinate anfasst.
    DESIGN_WIDTH = 320

    def __init__(self, fb_device, width, height, backlight_path,
                 backlight_timeout, rotate=0):
        self.fb_device = fb_device
        self.width = width
        self.height = height
        self.rotate = rotate
        self.s = width / float(self.DESIGN_WIDTH)
        self.backlight_path = backlight_path
        self.backlight_timeout = backlight_timeout
        self._bl_deadline = None
        self._fb = None
        self._is_off = False

        # Fonts
        self.font_large = ImageFont.load_default()
        self.font_medium = ImageFont.load_default()
        self.font_small = ImageFont.load_default()
        self.font_icon = ImageFont.load_default()
        for path in [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        ]:
            if Path(path).exists():
                self.font_large = ImageFont.truetype(path, self._s(30))
                self.font_medium = ImageFont.truetype(path, self._s(20))
                self.font_small = ImageFont.truetype(path, self._s(16))
                self.font_icon = ImageFont.truetype(path, self._s(24))
                break

    def _s(self, v):
        """Logische Layout-Einheit -> echtes Bildschirmpixel."""
        return int(round(v * self.s))

    def flush(self, img):
        """Bild in den Framebuffer. Der Dateizeiger bleibt offen -- ihn pro
        Bild zu oeffnen kostete bei 30 fps unnoetig Systemaufrufe."""
        data = to_rgb565_rotated(img, self.rotate)
        if self._fb is None:
            self._fb = open(self.fb_device, "wb", buffering=0)
        self._fb.seek(0)
        self._fb.write(data)


    def backlight_on(self):
        try:
            with open(self.backlight_path, 'w') as f:
                f.write('0')
        except OSError:
            pass

    def backlight_off(self):
        try:
            with open(self.backlight_path, 'w') as f:
                f.write('1')
        except OSError:
            pass


    def wake(self):
        """Beleuchtung an, Ablaufzeit neu setzen. True, wenn sie aus war.

        Kein threading.Timer mehr -- die Bildschleife prueft den Zeitpunkt.
        Das spart einen Thread, der bisher nebenlaeufig gezeichnet hat.
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


    def new_frame(self):
        return Image.new('RGB', (self.width, self.height), self.BG)

    def center_text(self, draw, text, font, color, y):
        """y in logischen Einheiten."""
        return self._center_text_px(draw, text, font, color, self._s(y))

    def _center_text_px(self, draw, text, font, color, y_px):
        bbox = draw.textbbox((0, 0), text, font=font)
        tw = bbox[2] - bbox[0]
        x = (self.width - tw) // 2
        draw.text((x, y_px), text, fill=color, font=font)
        return bbox[3] - bbox[1]

    def wrap_text(self, draw, text, font, color, y, max_width=None):
        """y in logischen Einheiten, Rueckgabe ebenfalls logisch."""
        if max_width is None:
            max_width = self.width - self._s(20)
        words = text.split()
        lines = []
        current = ""
        for word in words:
            test = f"{current} {word}".strip()
            bbox = draw.textbbox((0, 0), test, font=font)
            if (bbox[2] - bbox[0]) <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        y_px = self._s(y)
        for line in lines:
            self._center_text_px(draw, line, font, color, y_px)
            bbox = draw.textbbox((0, 0), line, font=font)
            y_px += (bbox[3] - bbox[1]) + self._s(4)
        return int(round(y_px / self.s))

    def draw_button(self, draw, x, y, w, h, text, bg_color, text_color=None):
        """Draw a rounded button. Returns (x, y, x2, y2) hit rect."""
        if text_color is None:
            text_color = self.BG
        x, y, w, h = self._s(x), self._s(y), self._s(w), self._s(h)
        draw.rounded_rectangle((x, y, x + w, y + h), radius=self._s(8),
                               fill=bg_color)
        bbox = draw.textbbox((0, 0), text, font=self.font_medium)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        tx = x + (w - tw) // 2
        ty = y + (h - th) // 2
        draw.text((tx, ty), text, fill=text_color, font=self.font_medium)
        return (x, y, x + w, y + h)

    def draw_back_button(self, draw):
        """Draw a small back arrow top-left. Returns hit rect."""
        rect = (self._s(5), self._s(5), self._s(55), self._s(35))
        draw.rounded_rectangle(rect, radius=self._s(6), fill=self.DARK_GRAY)
        draw.text((self._s(14), self._s(8)), "\u2190",
                  fill=self.WHITE, font=self.font_icon)
        return rect


# --- Hit testing ---

def hit(rect, px, py):
    return rect[0] <= px <= rect[2] and rect[1] <= py <= rect[3]


