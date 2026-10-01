"""Verlauf der letzten Scans, mit Zusammenfassung gleicher Artikel."""
import time
from dataclasses import dataclass, field


@dataclass
class ScanEntry:
    barcode: str
    name: str
    mode: str                 # "out" oder "in"
    count: int = 1            # gewuenschte Menge
    at: float = field(default_factory=time.monotonic)
    booked: int = 0           # tatsaechlich gebucht; bei Abbruch kleiner als count
    location_lost: bool = False

    @property
    def partial(self):
        return self.booked < self.count


class ScanLog:
    def __init__(self, limit=20):
        self.limit = limit
        self._entries = []        # aelteste zuerst

    @property
    def entries(self):
        """Neueste zuerst -- so wird die Liste auch gezeichnet."""
        return list(reversed(self._entries))

    @property
    def latest(self):
        return self._entries[-1] if self._entries else None

    def add(self, barcode, name, mode, count=1, at=None, booked=None):
        at = time.monotonic() if at is None else at
        booked = count if booked is None else booked
        last = self._entries[-1] if self._entries else None
        # Nur direkt aufeinanderfolgende, gleiche Scans zusammenfassen. Ein
        # dazwischenliegender anderer Artikel wuerde sonst die zeitliche
        # Ordnung verfaelschen. Teilbuchungen bleiben ebenfalls eigenstaendig,
        # sonst verschwindet die abgebrochene Menge im naechsten Eintrag.
        if (last is not None and last.barcode == barcode and last.mode == mode
                and not last.partial and booked == count):
            last.count += count
            last.booked += booked
            last.at = at
            return last
        entry = ScanEntry(barcode, name, mode, count, at, booked)
        self._entries.append(entry)
        if len(self._entries) > self.limit:
            self._entries.pop(0)
        return entry

    def remove(self, entry):
        if entry in self._entries:
            self._entries.remove(entry)
