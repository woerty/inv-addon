"""Framebuffer, Hintergrundbeleuchtung, Zeichenhelfer."""
import threading
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


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
        self._bl_timer = None
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
        """Convert PIL Image to RGB565 via numpy and write to fb."""
        if self.rotate == 90:
            img = img.transpose(Image.ROTATE_90)
        elif self.rotate == 180:
            img = img.transpose(Image.ROTATE_180)
        elif self.rotate == 270:
            img = img.transpose(Image.ROTATE_270)
        arr = np.array(img)
        r = (arr[:, :, 0].astype(np.uint16) >> 3) << 11
        g = (arr[:, :, 1].astype(np.uint16) >> 2) << 5
        b = arr[:, :, 2].astype(np.uint16) >> 3
        rgb565 = (r | g | b).astype(np.uint16)
        with open(self.fb_device, 'wb') as f:
            f.write(rgb565.tobytes())

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

    def _backlight_off_and_flag(self):
        self._is_off = True
        self.backlight_off()

    def wake(self):
        """Turn backlight on, restart timer. Returns True if was asleep."""
        was_off = self._is_off
        self._is_off = False
        self.backlight_on()
        if self._bl_timer is not None:
            self._bl_timer.cancel()
        self._bl_timer = threading.Timer(self.backlight_timeout,
                                         self._backlight_off_and_flag)
        self._bl_timer.daemon = True
        self._bl_timer.start()
        return was_off

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


