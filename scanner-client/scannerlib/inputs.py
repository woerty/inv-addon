"""Barcode-Leser und Touch, jeweils als Thread in eine Warteschlange."""
import time

import evdev


SCANCODES = {
    2: "1", 3: "2", 4: "3", 5: "4", 6: "5",
    7: "6", 8: "7", 9: "8", 10: "9", 11: "0",
    28: "\n",
    30: "a", 31: "b", 32: "c", 33: "d", 34: "e",
    35: "f", 36: "g", 37: "h", 38: "i", 39: "j",
    40: "k", 41: "l", 42: "m", 43: "n", 44: "o",
    45: "p", 46: "q", 47: "r", 48: "s", 49: "t",
    50: "u", 51: "v", 52: "w", 53: "x", 54: "y",
    55: "z", 57: " ", 12: "-",
}


def barcode_reader(device_path, q):
    """Read barcodes and put them in the queue."""
    while True:
        try:
            dev = evdev.InputDevice(device_path)
            dev.grab()
            barcode = ""
            for event in dev.read_loop():
                if event.type == evdev.ecodes.EV_KEY and event.value == 1:
                    char = SCANCODES.get(event.code)
                    if char is None:
                        continue
                    if char == "\n":
                        if barcode:
                            q.put(("barcode", barcode))
                            barcode = ""
                    else:
                        barcode += char
        except (OSError, IOError) as e:
            print(f"Scanner error: {e}, retrying in 2s...")
            time.sleep(2)


# --- Touch reading ---

# Der GT911 ist kapazitiv und meldet fertige Bildschirmkoordinaten im
# selben Raster, in dem die App zeichnet (0..639 x 0..479). Deshalb
# keinerlei Kalibrierung, Mittelung oder Entprellung -- das war alles nur
# noetig, um das Rauschen des alten resistiven Panels zu baendigen.

def touch_reader(device_path, q, cfg):
    """Read touch events and put screen coordinates in queue."""
    W = cfg["screen_width"]
    H = cfg["screen_height"]
    SWAP = bool(cfg.get("touch_swap_xy", 0))
    FLIP_X = bool(cfg.get("touch_flip_x", 0))
    FLIP_Y = bool(cfg.get("touch_flip_y", 0))

    def axis_ranges(dev):
        """Wertebereiche vom Treiber erfragen statt sie anzunehmen.

        Der GT911 meldet hier 0..639 bzw. 0..479, und diese Achsen sind
        gegenueber dem Panel vertauscht. Normiert man zuerst auf 0..1,
        faellt die Skalierung von selbst richtig aus.
        """
        rng = {}
        for code, info in dev.capabilities(absinfo=True).get(
                evdev.ecodes.EV_ABS, []):
            if code in (evdev.ecodes.ABS_X, evdev.ecodes.ABS_MT_POSITION_X):
                rng.setdefault("x", (info.min, info.max))
            elif code in (evdev.ecodes.ABS_Y, evdev.ecodes.ABS_MT_POSITION_Y):
                rng.setdefault("y", (info.min, info.max))
        return rng.get("x", (0, W - 1)), rng.get("y", (0, H - 1))

    while True:
        try:
            dev = evdev.InputDevice(device_path)
            (x_lo, x_hi), (y_lo, y_hi) = axis_ranges(dev)
            x_span = max(1, x_hi - x_lo)
            y_span = max(1, y_hi - y_lo)

            def to_screen(rx, ry):
                nx = (rx - x_lo) / x_span          # 0..1
                ny = (ry - y_lo) / y_span
                if SWAP:
                    nx, ny = ny, nx
                if FLIP_X:
                    nx = 1.0 - nx
                if FLIP_Y:
                    ny = 1.0 - ny
                return (max(0, min(W - 1, int(round(nx * (W - 1))))),
                        max(0, min(H - 1, int(round(ny * (H - 1))))))

            x, y = None, None
            touching = False
            last_move_time = 0

            for event in dev.read_loop():
                if event.type == evdev.ecodes.EV_ABS:
                    if event.code in (evdev.ecodes.ABS_X,
                                      evdev.ecodes.ABS_MT_POSITION_X):
                        x = event.value
                    elif event.code in (evdev.ecodes.ABS_Y,
                                        evdev.ecodes.ABS_MT_POSITION_Y):
                        y = event.value
                elif event.type == evdev.ecodes.EV_KEY:
                    if event.code == evdev.ecodes.BTN_TOUCH:
                        if event.value == 1:
                            touching = True
                        else:
                            touching = False
                            if x is not None and y is not None:
                                px, py = to_screen(x, y)
                                q.put(("touch_up", px, py))
                elif event.type == evdev.ecodes.EV_SYN and touching:
                    if x is None or y is None:
                        continue
                    now = time.monotonic()
                    if now - last_move_time > 0.05:
                        px, py = to_screen(x, y)
                        q.put(("touch_move", px, py))
                        last_move_time = now
        except (OSError, IOError) as e:
            print(f"Touch error: {e}, retrying in 2s...")
            time.sleep(2)


