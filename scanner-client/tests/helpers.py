"""Testdoppel: kein Netz, kein Display, kein evdev."""
from PIL import Image

from scannerlib.app import App
from scannerlib.scanlog import ScanLog
from scannerlib.theme import Theme


class FakeAPI:
    def __init__(self, fail_at=None, deleted_on_scan_out=False):
        self.fail_at = fail_at          # 1-basiert: der wievielte Aufruf scheitert
        self.deleted_on_scan_out = deleted_on_scan_out
        self.calls = []

    def get_locations(self):
        return [{"id": 1, "name": "Küche oben"}]

    def _fail(self):
        return self.fail_at is not None and len(self.calls) == self.fail_at

    def scan_out(self, barcode):
        self.calls.append(("out", barcode))
        if self._fail():
            return (None, "Verbindung abgebrochen")
        return (200, {"status": "ok", "name": "Milch", "barcode": barcode,
                      "remaining_quantity": 0 if self.deleted_on_scan_out else 3,
                      "deleted": self.deleted_on_scan_out})

    def scan_in(self, barcode, storage_location_id=None):
        self.calls.append(("in", barcode))
        if self._fail():
            return (None, "Verbindung abgebrochen")
        return (200, {"status": "ok", "name": "Milch", "barcode": barcode,
                      "quantity": 1, "storage_location": None,
                      "created": self.deleted_on_scan_out})


class FakeDisplay:
    width, height = 640, 480

    def __init__(self):
        self.flushes = 0

    def flush(self, img):
        self.flushes += 1

    def wake(self):
        return False

    def tick_backlight(self, now):
        return False

    def new_frame(self):
        return Image.new("RGB", (self.width, self.height))


def make_app(api, **kw):
    """App ohne __init__ -- der wuerde Geraete oeffnen."""
    app = App.__new__(App)
    app.cfg = {"screen_width": 640, "screen_height": 480}
    app.api = api
    app.display = FakeDisplay()
    app.theme = Theme(640)
    app.theme.height = 480
    app.log = ScanLog()
    app.mode = "out"
    app.location = None
    app.locations = []
    app.multiplier = 1
    app.api_ok = True
    app.scanner_connected = True
    app.busy = False
    app.last_result = None
    app.result_deadline = None
    app.idle_reset_s = 600
    app.last_activity = 0.0
    app.screen = "scan"
    app.scroll = None
    app._dirty = False
    app._rects = {}
    app._last_location_fetch = 0.0
    app._location_fetch_running = False
    for k, v in kw.items():
        setattr(app, k, v)
    return app
