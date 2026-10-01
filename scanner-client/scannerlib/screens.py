"""Zeichnen der drei Bildschirme.

Alle Masse stammen aus der Spezifikation. Die Methoden zeichnen und liefern
Trefferflaechen zurueck; was ein Treffer bedeutet, entscheidet App.
"""
from PIL import ImageDraw


def ellipsize(draw, text, font, max_px):
    """Kuerzt mit Auslassungspunkten.

    Nie umbrechen -- eine zweite Zeile sprengt die Kartenhoehe. Binaere
    Suche statt zeichenweisem Abschneiden, weil textlength() der teuerste
    Teil ist und das Zeichnen im 33-ms-Budget liegen muss.
    """
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


def _center(draw, text, font, fill, y, width):
    w = draw.textlength(text, font=font)
    draw.text(((width - w) / 2, y), text, font=font, fill=fill)


class Screens:
    """Zeichnet nach Zustand. Haelt selbst keinen Zustand ausser dem Theme."""

    def __init__(self, theme):
        self.t = theme

    # ---------- gemeinsame Teile ----------

    def header(self, draw, mode, rects):
        """Modusleiste plus Verlauf-Knopf. Fuellt rects mit Trefferflaechen."""
        t = self.t
        h = t.HEADER_H
        pad, gap = t.s(6), t.s(5)
        ham_w = int(t.width * 0.15)          # 15 Prozent der Breite
        seg_x0, seg_x1 = pad, t.width - pad - ham_w - gap
        half = (seg_x1 - seg_x0) // 2

        draw.rectangle((0, 0, t.width, h), fill=t.BG)
        draw.line((0, h, t.width, h), fill=t.LINE)
        draw.rounded_rectangle((seg_x0, t.s(5), seg_x1, h - t.s(5)),
                               radius=t.RADIUS_SM, outline=t.LINE, width=2)
        for i, (key, label, colour) in enumerate(
                (("mode_out", "Auslagern", t.OUT), ("mode_in", "Einlagern", t.IN))):
            x0 = seg_x0 + i * half
            x1 = x0 + half
            on = (mode == ("out" if i == 0 else "in"))
            if on:
                draw.rounded_rectangle((x0, t.s(5), x1, h - t.s(5)),
                                       radius=t.RADIUS_SM, fill=colour)
            w = draw.textlength(label, font=t.font_md)
            draw.text((x0 + (half - w) / 2, (h - t.font_md.size) / 2 - t.s(1)),
                      label, font=t.font_md, fill=t.ON_ACCENT if on else t.FG_DIM)
            rects[key] = (x0, 0, x1, h)

        hx0 = t.width - pad - ham_w
        draw.rounded_rectangle((hx0, t.s(5), t.width - pad, h - t.s(5)),
                               radius=t.RADIUS_SM, fill=t.SURFACE_ALT)
        w = draw.textlength("☰", font=t.font_icon)
        draw.text((hx0 + (ham_w - w) / 2, (h - t.font_icon.size) / 2 - t.s(1)),
                  "☰", font=t.font_icon, fill=t.FG)
        rects["hist"] = (hx0, 0, t.width - pad, h)

    def status_dot(self, draw, ok):
        """Unten links, frei im Bild -- nimmt der Modusleiste keine Breite weg."""
        t = self.t
        r = t.s(7)
        x, y = t.PAD + r, t.height - t.PAD - r
        draw.ellipse((x - r, y - r, x + r, y + r), fill=t.IN if ok else t.DANGER)

    def subheader(self, draw, title, rects):
        """Zurueck-Pfeil und Titel. Nur auf Lagerort und Verlauf."""
        t = self.t
        y0, h = t.HEADER_H, t.SUBHEADER_H
        draw.rectangle((0, y0, t.width, y0 + h), fill=t.BG)
        draw.line((0, y0 + h, t.width, y0 + h), fill=t.LINE)
        bw, bh = t.s(32), t.s(24)
        bx, by = t.s(6), y0 + (h - bh) // 2
        draw.rounded_rectangle((bx, by, bx + bw, by + bh),
                               radius=t.RADIUS_SM, fill=t.SURFACE_ALT)
        w = draw.textlength("←", font=t.font_back)
        draw.text((bx + (bw - w) / 2, by + (bh - t.font_back.size) / 2 - t.s(1)),
                  "←", font=t.font_back, fill=t.FG)
        rects["back"] = (bx, y0, bx + bw, y0 + h)
        _center(draw, title, t.font_sm, t.FG_DIM,
                y0 + (h - t.font_sm.size) / 2 - t.s(1), t.width)
        return y0 + h

    # ---------- Scan ----------

    def scan(self, draw, state, rects):
        t = self.t
        y = t.HEADER_H
        self.header(draw, state["mode"], rects)

        if state["mode"] == "in":
            loc = state["location"]
            label = "→ " + (loc["name"] if loc else "Ohne Ort")
            draw.text((t.PAD, y + t.s(5)), label, font=t.font_sm, fill=t.ACCENT)
            rects["loc"] = (0, y, t.width, y + t.s(26))
            draw.line((0, y + t.s(26), t.width, y + t.s(26)), fill=t.LINE)
            y += t.s(26)

        _center(draw, state["status"], t.font_md, t.FG_DIM, y + t.s(9), t.width)
        y += t.s(9) + t.font_md.size + t.s(6)

        self._card(draw, state, rects, y)

        mw, mh = t.s(66), t.s(42)
        mx, my = (t.width - mw) // 2, t.height - mh - t.s(11)
        armed = state["multiplier"] > 1
        draw.rounded_rectangle((mx, my, mx + mw, my + mh), radius=t.RADIUS,
                               fill=(0x13, 0x22, 0x31) if armed else t.SURFACE,
                               outline=t.ACCENT if armed else t.LINE, width=2)
        label = "×%d" % state["multiplier"]
        w = draw.textlength(label, font=t.font_mult)
        draw.text((mx + (mw - w) / 2, my + (mh - t.font_mult.size) / 2 - t.s(2)),
                  label, font=t.font_mult, fill=t.ACCENT if armed else t.FG)
        rects["mult"] = (mx, my, mx + mw, my + mh)

        self.status_dot(draw, state["api_ok"])

    def _card(self, draw, state, rects, y):
        """Letzter Scan. Bleibt stehen, statt nach vier Sekunden zu verschwinden."""
        t = self.t
        res = state["result"]
        x0, x1 = t.PAD, t.width - t.PAD
        h = max(t.CARD_MIN_H, t.s(64))
        if res is None:
            draw.rounded_rectangle((x0, y, x1, y + h), radius=t.RADIUS,
                                   outline=t.LINE, width=1)
            _center(draw, "noch nichts gescannt", t.font_sm, t.FG_DIM,
                    y + (h - t.font_sm.size) / 2, t.width)
            return

        draw.rounded_rectangle((x0, y, x1, y + h), radius=t.RADIUS,
                               fill=state["card_bg"] or t.SURFACE,
                               outline=t.LINE, width=1)
        undo_w = t.s(98)   # 196 px: "Rückgängig" misst bei 26 px 172 px plus Innenrand
        pad = t.s(8)
        inner_x1 = x1 - pad - undo_w - t.s(7)

        tick_r = t.s(17)
        cx, cy = x0 + pad + tick_r, y + pad + tick_r
        draw.ellipse((cx - tick_r, cy - tick_r, cx + tick_r, cy + tick_r),
                     fill={"ok": t.IN, "warn": t.WARN, "err": t.DANGER}[res["kind"]])
        sym = {"ok": "✓", "warn": "!", "err": "×"}[res["kind"]]
        w = draw.textlength(sym, font=t.font_tick)
        draw.text((cx - w / 2, cy - t.font_tick.size / 2 - t.s(1)), sym,
                  font=t.font_tick, fill=t.ON_ACCENT)

        name_x = cx + tick_r + t.s(6)
        draw.text((name_x, cy - t.font_md.size / 2 - t.s(1)),
                  ellipsize(draw, res["name"], t.font_md, inner_x1 - name_x),
                  font=t.font_md, fill=t.FG)
        draw.text((x0 + pad, y + h - pad - t.font_sm.size - t.s(2)),
                  ellipsize(draw, res["meta"], t.font_sm, inner_x1 - x0 - pad),
                  font=t.font_sm, fill=t.FG_DIM)

        if res.get("undoable"):
            ux0 = x1 - pad - undo_w
            draw.rounded_rectangle((ux0, y + pad, x1 - pad, y + h - pad),
                                   radius=t.RADIUS_SM, fill=t.SURFACE_ALT,
                                   outline=t.LINE, width=1)
            w = draw.textlength("Rückgängig", font=t.font_sm)
            draw.text((ux0 + (undo_w - w) / 2, y + h / 2 - t.font_sm.size / 2),
                      "Rückgängig", font=t.font_sm, fill=t.FG)
            rects["undo"] = (ux0, y + pad, x1 - pad, y + h - pad)
