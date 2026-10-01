"""Farben, Schriftstufen und Abstaende.

Alle Werte stammen aus der Spezifikation, Abschnitte Farben, Schrift und
Raster. Das Layout rechnet in logischen Einheiten einer 320 px breiten
Entwurfsflaeche; skaliert wird zentral hier, damit ein groesseres Panel
spaeter nicht jede Koordinate anfasst.
"""
from pathlib import Path

from PIL import ImageFont

DESIGN_WIDTH = 320

_FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
]


def _font(size):
    for p in _FONT_PATHS:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                pass
    return ImageFont.load_default()


class Theme:
    # --- Farben ---
    BG = (0x0E, 0x10, 0x14)
    SURFACE = (0x1A, 0x1D, 0x24)
    SURFACE_ALT = (0x23, 0x27, 0x33)
    LINE = (0x2E, 0x33, 0x40)
    FG = (0xE8, 0xEB, 0xF0)
    FG_DIM = (0x8B, 0x93, 0xA3)
    ACCENT = (0x4F, 0xA8, 0xFF)
    OUT = (0xF2, 0xA3, 0x41)        # Modus Auslagern
    IN = (0x4E, 0xD9, 0x7E)         # Modus Einlagern, Erfolg
    WARN = (0xFF, 0xC2, 0x4D)
    DANGER = (0xFF, 0x6B, 0x6B)
    ON_ACCENT = (0x10, 0x13, 0x1A)  # Text auf gefuellten Flaechen

    def __init__(self, width):
        self.width = width
        self.scale = width / float(DESIGN_WIDTH)

        # Schriftleiter. Die kleinste Stufe liegt unter den 30 px, die ab
        # 50 cm Leseabstand noetig waeren, und ist deshalb nur fuer Beiwerk.
        self.font_xl = _font(self.s(28))   # 56
        self.font_lg = _font(self.s(20))   # 40
        self.font_md = _font(self.s(16))   # 32
        self.font_sm = _font(self.s(13))   # 26

        # Symbolgroessen stehen bewusst neben der Leiter: x, Haken, Pfeile
        # sind Zeichen und werden nach Flaeche bemessen, nicht nach
        # Lesbarkeit auf Distanz.
        self.font_mult = _font(self.s(18))  # 36, der xN-Knopf
        self.font_icon = _font(self.s(15))  # 30, Verlauf-Knopf
        self.font_back = _font(self.s(14))  # 28, Zurueck-Pfeil
        self.font_tick = _font(self.s(11))  # 22, Haken in der Karte

        # --- Raster ---
        self.GAP = self.s(4)          # Grundabstand 8
        self.PAD = self.s(8)          # Rand 16
        self.RADIUS = self.s(6)       # Karten 12
        self.RADIUS_SM = self.s(4)    # Knoepfe 8
        self.HEADER_H = self.s(36)    # 72
        self.SUBHEADER_H = self.s(30)  # 60
        self.ROW_H = self.s(48)       # 96, eine Fingerkuppe
        self.CARD_MIN_H = self.s(64)  # 128

    def s(self, v):
        """Logische Entwurfseinheit -> echtes Bildschirmpixel."""
        return int(round(v * self.scale))
