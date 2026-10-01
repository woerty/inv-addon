"""Scroll-Physik: Momentum und Rubberbanding.

Reine Mathematik ohne Ein-/Ausgabe, damit sich das Scrollgefuehl pruefen
laesst statt es nur zu erfuehlen. Alle Konstanten sind benannt, weil sie am
echten Geraet nachjustiert werden.
"""
import math


class ScrollView:
    def __init__(self, view_h, content_h, friction=3.0, spring=12.0,
                 damp=None, drag_threshold=25, min_velocity=20.0):
        self.view_h = view_h
        self.content_h = content_h
        self.friction = friction        # 1/s, Abklingen des Schwungs
        self.spring = spring            # 1/s, Haerte der Randfeder
        self.damp = damp if damp is not None else view_h
        self.drag_threshold = drag_threshold
        self.min_velocity = min_velocity

        self.offset = 0.0
        self.velocity = 0.0
        self.is_dragging = False
        self.was_drag = False
        self._y0 = 0.0
        self._off0 = 0.0
        self._started = False
        self._samples = []

    @property
    def max_offset(self):
        return max(0, self.content_h - self.view_h)

    def set_content_h(self, h):
        self.content_h = h
        self.offset = float(max(0, min(self.offset, self.max_offset)))

    def _damped(self, over):
        """Je weiter ueber den Rand, desto zaeher. Naehert sich damp, ohne es
        je zu erreichen -- weiter als eine Ansichtshoehe geht es nicht."""
        d = self.damp
        return d * (1 - 1 / (over / d + 1))

    @property
    def visual_offset(self):
        """Was gezeichnet wird. Innerhalb der Grenzen gleich offset,
        darueber hinaus gedaempft."""
        if self.offset < 0:
            return -self._damped(-self.offset)
        m = self.max_offset
        if self.offset > m:
            return m + self._damped(self.offset - m)
        return self.offset

    def on_down(self, y, now=0.0):
        self.is_dragging = True
        self._started = False
        self.was_drag = False
        self._y0 = y
        self._off0 = self.offset
        self.velocity = 0.0          # Beruehrung stoppt das Gleiten sofort
        self._samples = [(y, now)]

    def on_move(self, y, now=0.0):
        """True, wenn sich der Inhalt bewegt hat."""
        if not self.is_dragging or self.max_offset <= 0:
            return False
        dy = self._y0 - y
        if not self._started:
            # Erst ab der Schwelle ziehen, sonst wackelt jeder Tipp die Liste.
            if abs(dy) < self.drag_threshold:
                return False
            self._started = True
            # Anker genau dort, wo die Schwelle ueberschritten wurde: kein
            # Sprung um die Schwellenbreite, aber die Strecke darueber hinaus
            # zaehlt sofort. Wuerde man auf y verankern, bliebe der erste
            # Move wirkungslos und meldete trotzdem "bewegt".
            crossing = self.drag_threshold if dy > 0 else -self.drag_threshold
            self._y0 -= crossing
            self._off0 = self.offset
            dy -= crossing
        self.offset = self._off0 + dy
        self._samples.append((y, now))
        while len(self._samples) > 2 and now - self._samples[0][1] > 0.1:
            self._samples.pop(0)
        return True

    def on_up(self, now=0.0):
        if not self.is_dragging:
            return
        self.is_dragging = False
        self.was_drag = self._started
        if self._started and len(self._samples) > 1:
            # Geschwindigkeit aus den letzten ~100 ms, nicht aus dem letzten
            # Einzelwert -- der ist beim Abheben verrauscht.
            (ya, ta), (yb, tb) = self._samples[0], self._samples[-1]
            dt = tb - ta
            self.velocity = (ya - yb) / dt if dt > 0.004 else 0.0
            self.velocity = max(-4000.0, min(4000.0, self.velocity))
        self.offset = self.visual_offset

    def advance(self, dt):
        """Einen Zeitschritt weiter. True, solange etwas in Bewegung ist."""
        if self.is_dragging or self.max_offset <= 0:
            return False
        m = self.max_offset
        moving = False

        if abs(self.velocity) > self.min_velocity:
            self.offset += self.velocity * dt
            self.velocity *= math.exp(-self.friction * dt)
            moving = True
            if self.offset < 0 or self.offset > m:
                self.offset = max(-self.damp, min(m + self.damp, self.offset))
                self.velocity *= 0.5
        else:
            self.velocity = 0.0

        target = 0 if self.offset < 0 else (m if self.offset > m else None)
        if target is not None:
            self.offset += (target - self.offset) * (1 - math.exp(-self.spring * dt))
            if abs(target - self.offset) < 0.5:
                self.offset = float(target)
                self.velocity = 0.0
            else:
                moving = True
        return moving
