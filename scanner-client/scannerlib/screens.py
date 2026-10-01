"""Zeichnen der drei Bildschirme.

Alle Masse stammen aus der Spezifikation. Die Methoden zeichnen und liefern
Trefferflaechen zurueck; was ein Treffer bedeutet, entscheidet App.
"""
_ELLIPSIS_CACHE = {}


def ellipsize(draw, text, font, max_px):
    """Kuerzt mit Auslassungspunkten.

    Nie umbrechen -- eine zweite Zeile sprengt die Kartenhoehe. Binaere
    Suche statt zeichenweisem Abschneiden, weil textlength() der teuerste
    Teil ist und das Zeichnen im 33-ms-Budget liegen muss.
    """
    schluessel = (text, getattr(font, "size", 0), int(max_px))
    treffer = _ELLIPSIS_CACHE.get(schluessel)
    if treffer is not None:
        return treffer
    if draw.textlength(text, font=font) <= max_px:
        if len(_ELLIPSIS_CACHE) < 512:
            _ELLIPSIS_CACHE[schluessel] = text
        return text
    lo, hi = 0, len(text)
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if draw.textlength(text[:mid] + "…", font=font) <= max_px:
            lo = mid
        else:
            hi = mid - 1
    ergebnis = text[:lo] + "…"
    # Produktnamen wiederholen sich, Breiten auch. Die Binaersuche pro Bild
    # pro Zeile war ein messbarer Teil der 28 ms Bildzeit.
    if len(_ELLIPSIS_CACHE) < 512:
        _ELLIPSIS_CACHE[schluessel] = ergebnis
    return ergebnis


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

    def status_dot(self, draw, ok, in_subheader=False):
        """Verbindungsanzeige.

        Auf dem Scan-Bildschirm unten links im freien Raum. Auf Listen-
        Bildschirmen waere dort eine Zeile -- dort sitzt er rechts in der
        Unterzeile, wo ohnehin Platz ist.
        """
        t = self.t
        r = t.s(3)    # 14 px Durchmesser, nicht Radius
        if in_subheader:
            x = t.width - t.PAD - r
            y = t.HEADER_H + t.SUBHEADER_H // 2
        else:
            x, y = t.PAD + r, t.height - t.PAD - r
        draw.ellipse((x - r, y - r, x + r, y + r), fill=t.IN if ok else t.DANGER)

    def listheader(self, draw, title, ok, rects):
        """Eine 80-px-Leiste fuer Lagerort und Verlauf: zurueck, Titel, Punkt.

        Ersetzt dort Modusleiste plus Unterzeile. Das gibt dem Zurueck-Knopf
        Fingermass und der Liste eine ganze Zeile mehr -- zwei Leisten
        uebereinander kosteten 160 der 480 px.
        """
        t = self.t
        h = t.HEADER_H
        draw.rectangle((0, 0, t.width, h), fill=t.BG)
        draw.line((0, h, t.width, h), fill=t.LINE)
        bw, bh = t.s(50), t.s(30)
        bx, by = t.s(6), (h - bh) // 2
        draw.rounded_rectangle((bx, by, bx + bw, by + bh),
                               radius=t.RADIUS_SM, fill=t.SURFACE_ALT)
        w = draw.textlength("\u2190", font=t.font_back)
        draw.text((bx + (bw - w) / 2, by + (bh - t.font_back.size) / 2 - t.s(1)),
                  "\u2190", font=t.font_back, fill=t.FG)
        # Trefferflaeche groesser als der gezeichnete Knopf: bis an den Rand
        # und ueber die volle Hoehe der Leiste.
        rects["back"] = (0, 0, bx + bw + t.s(12), h)
        _center(draw, title, t.font_md, t.FG_DIM, (h - t.font_md.size) / 2 - t.s(1),
                t.width)
        r = t.s(3)    # 14 px Durchmesser
        draw.ellipse((t.width - t.PAD - 2 * r, h // 2 - r,
                      t.width - t.PAD, h // 2 + r), fill=t.IN if ok else t.DANGER)
        return h

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
            draw.text((t.PAD, y + t.s(12)), label, font=t.font_sm, fill=t.ACCENT)
            rects["loc"] = (0, y, t.width, y + t.s(40))
            draw.line((0, y + t.s(40), t.width, y + t.s(40)), fill=t.LINE)
            y += t.s(40)

        _center(draw, state["status"], t.font_md, t.FG_DIM, y + t.s(9), t.width)
        y += t.s(9) + t.font_md.size + t.s(6)

        self._card(draw, state, rects, y)

        mw, mh = t.s(66), t.s(42)
        mx, my = (t.width - mw) // 2, t.height - mh - t.s(11)
        armed = state["multiplier"] > 1
        draw.rounded_rectangle((mx, my, mx + mw, my + mh), radius=t.RADIUS,
                               fill=t.SELECTED if armed else t.SURFACE,
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

        fortschritt = state.get("progress")
        if fortschritt:
            erledigt, gesamt = fortschritt
            draw.rounded_rectangle((x0, y, x1, y + h), radius=t.RADIUS,
                                   fill=t.SURFACE, outline=t.LINE, width=1)
            r = t.s(20)
            cx, cy = x0 + t.s(14) + r, y + h // 2
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=t.LINE, width=t.s(3))
            if erledigt:
                draw.pieslice((cx - r, cy - r, cx + r, cy + r), -90,
                              -90 + int(360 * erledigt / gesamt),
                              outline=t.ACCENT, width=t.s(3))
            label = "%d von %d" % (erledigt, gesamt)
            draw.text((cx + r + t.s(8), cy - t.font_md.size / 2 - t.s(1)),
                      label, font=t.font_md, fill=t.FG)
            draw.text((cx + r + t.s(8), cy + t.s(4)),
                      "wird gebucht", font=t.font_sm, fill=t.FG_DIM)
            return

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
        inner_x1 = (x1 - pad - undo_w - t.s(7)) if res.get("undoable") else (x1 - pad)

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

    # ---------- Lagerort ----------

    def locations(self, draw, state, rects):
        """Scrollende Liste. Gezeichnet wird mit visual_offset, damit das
        Ueberziehen am Rand sichtbar ist.

        Reihenfolge ist wichtig: erst die Zeilen, dann Kopf- und Unterzeile
        darueber. PIL kennt keinen Klippbereich, deshalb ragt der Text einer
        halb herausgescrollten Zeile sonst in die Unterzeile hinein. Beide
        Leisten malen deckend und decken das zu.
        """
        t = self.t
        y0 = t.HEADER_H

        sv = state["scroll"]
        items = state["items"]
        view_h = t.height - y0
        off = sv.visual_offset
        row_rects = []

        for i, item in enumerate(items):
            ry = y0 + i * t.ROW_H - off
            if ry + t.ROW_H < y0 or ry > t.height:
                row_rects.append(None)
                continue
            vy = max(ry, y0)
            vh = min(ry + t.ROW_H, t.height) - vy
            if vh <= 0:
                row_rects.append(None)
                continue
            gewaehlt = (state.get("selected_id", 0) == item["id"])
            draw.rectangle((0, vy, t.width, vy + vh),
                           fill=t.SELECTED if gewaehlt
                           else (t.SURFACE if i % 2 == 0 else t.SURFACE_ALT))
            if gewaehlt:
                draw.rectangle((0, vy, t.s(3), vy + vh), fill=t.ACCENT)
            draw.line((t.s(5), vy + vh - 1, t.width - t.s(5), vy + vh - 1), fill=t.LINE)
            ty = ry + (t.ROW_H - t.font_md.size) / 2 - t.s(1)
            if y0 - t.ROW_H < ty < t.height:
                draw.text((t.s(10), ty),
                          ellipsize(draw, item["name"], t.font_md, t.width - t.s(24)),
                          font=t.font_md,
                          fill=t.ACCENT if (item["id"] is None or gewaehlt) else t.FG)
            row_rects.append((0, vy, t.width, vy + vh))
        rects["rows"] = row_rects

        # Scrollbalken nur waehrend der Bewegung -- im Ruhezustand stoert er.
        total = len(items) * t.ROW_H
        if total > view_h and state["scrolling"]:
            bh = max(t.s(14), int(view_h * view_h / total))
            by = y0 + int(max(0.0, min(1.0, off / max(1, sv.max_offset))) * (view_h - bh))
            draw.rounded_rectangle((t.width - t.s(3), by, t.width - t.s(1), by + bh),
                                   radius=t.s(1), fill=t.FG_DIM)

        self.listheader(draw, "Lagerort wählen", state["api_ok"], rects)

    # ---------- Verlauf ----------

    def history(self, draw, state, rects):
        """Scrollt wie die Lagerortliste -- die Spezifikation verspricht 20
        Eintraege, ohne Scrollen waeren vier davon erreichbar."""
        t = self.t
        y0 = t.HEADER_H
        entries = state["entries"]
        sv = state["scroll"]
        off = sv.visual_offset if sv is not None else 0

        if not entries:
            self.listheader(draw, "Letzte Scans", state["api_ok"], rects)
            _center(draw, "noch nichts gescannt", t.font_sm, t.FG_DIM,
                    y0 + t.s(30), t.width)
            rects["hrows"] = []
            return

        bw, bh = t.s(42), t.s(42)
        row_rects = []
        for i, e in enumerate(entries):
            ry = y0 + i * t.ROW_H - off
            if ry + t.ROW_H < y0 or ry > t.height:
                row_rects.append(None)
                continue
            vy = max(ry, y0)
            vh = min(ry + t.ROW_H, t.height) - vy
            if vh <= 0:
                row_rects.append(None)
                continue
            draw.rectangle((0, vy, t.width, vy + vh),
                           fill=t.SURFACE if i % 2 == 0 else t.SURFACE_ALT)
            draw.line((t.s(5), vy + vh - 1, t.width - t.s(5), vy + vh - 1), fill=t.LINE)

            bx = t.width - t.PAD - bw
            by = ry + (t.ROW_H - bh) // 2
            draw.rounded_rectangle((bx, by, bx + bw, by + bh), radius=t.RADIUS_SM,
                                   fill=t.SURFACE_ALT, outline=t.LINE, width=1)
            w = draw.textlength("\u21b6", font=t.font_sm)
            draw.text((bx + (bw - w) / 2, by + (bh - t.font_sm.size) / 2 - t.s(1)),
                      "\u21b6", font=t.font_sm, fill=t.FG)

            ty = ry + (t.ROW_H - t.font_md.size) / 2 - t.s(1)
            ago = _ago(state["now"] - e.at)
            aw = draw.textlength(ago, font=t.font_sm)
            draw.text((bx - t.s(6) - aw, ry + (t.ROW_H - t.font_sm.size) / 2 - t.s(1)),
                      ago, font=t.font_sm, fill=t.FG_DIM)

            # Bei Teilbuchung zaehlt die tatsaechlich gebuchte Menge, nicht die
            # gewuenschte -- sonst steht im Verlauf eine Zahl, die nie gebucht wurde.
            menge = ("\u00d7%d von %d" % (e.booked, e.count)) if e.partial \
                else ("\u00d7%d" % e.count)
            mw = draw.textlength(menge, font=t.font_md)
            mx = bx - t.s(6) - aw - t.s(6) - mw
            draw.text((mx, ty), menge, font=t.font_md,
                      fill=t.WARN if e.partial else t.ACCENT)
            draw.text((t.s(8), ty),
                      ellipsize(draw, e.name, t.font_md, mx - t.s(14)),
                      font=t.font_md, fill=t.FG)
            row_rects.append((bx, by, bx + bw, by + bh))
        rects["hrows"] = row_rects

        total = len(entries) * t.ROW_H
        view_h = t.height - y0
        if sv is not None and total > view_h and state.get("scrolling"):
            sbh = max(t.s(14), int(view_h * view_h / total))
            sby = y0 + int(max(0.0, min(1.0, off / max(1, sv.max_offset)))
                           * (view_h - sbh))
            draw.rounded_rectangle((t.width - t.s(3), sby, t.width - t.s(1), sby + sbh),
                                   radius=t.s(1), fill=t.FG_DIM)

        self.listheader(draw, "Letzte Scans", state["api_ok"], rects)


    # ---------- Mengenauswahl ----------

    def multiplier_sheet(self, draw, rects):
        """x1 bis x12 als 4x3-Raster ueber dem Scan-Bildschirm.

        Vier Spalten, weil das Raster damit 420x264 px misst und bequem ins
        Bild passt; bei drei Spalten kaeme es mit der Ueberschrift der
        Unterkante zu nahe.
        """
        t = self.t
        draw.rectangle((0, 0, t.width, t.height), fill=t.SCRIM)
        cw, ch, gap = t.s(48), t.s(40), t.s(6)
        gw = 4 * cw + 3 * gap
        gh = 3 * ch + 2 * gap
        x0 = (t.width - gw) // 2
        y0 = (t.height - gh) // 2 + t.s(8)

        _center(draw, "Menge je Scan", t.font_sm, t.FG_DIM, y0 - t.s(22), t.width)
        cells = []
        for n in range(1, 13):
            r, c = divmod(n - 1, 4)
            x = x0 + c * (cw + gap)
            y = y0 + r * (ch + gap)
            draw.rounded_rectangle((x, y, x + cw, y + ch), radius=t.RADIUS_SM,
                                   fill=t.SURFACE_ALT, outline=t.LINE, width=2)
            label = "\u00d7%d" % n
            w = draw.textlength(label, font=t.font_md)
            draw.text((x + (cw - w) / 2, y + (ch - t.font_md.size) / 2 - t.s(1)),
                      label, font=t.font_md, fill=t.FG)
            cells.append((x, y, x + cw, y + ch))
        rects["mcells"] = cells


def _ago(seconds):
    if seconds < 60:
        return "gerade"
    minutes = int(seconds // 60)
    if minutes < 60:
        return "vor %d min" % minutes
    return "vor %d h" % (minutes // 60)
