"""Konfiguration aus scanner.conf, mit Vorgaben."""
from pathlib import Path

CONFIG_PATH = Path("/home/dstn/scanner.conf")

DEFAULT_CONFIG = {
    "api_url": "http://192.168.178.25:8099/api",
    "scanner_token": "",
    "input_device": "/dev/input/event0",
    "touch_device": "/dev/input/event1",
    "fb_device": "/dev/fb0",
    "backlight": "/sys/class/backlight/rpi_backlight/bl_power",
    # Das Panel haengt hochkant am DPI-Bus (480x640). Gezeichnet wird quer,
    # gedreht wird erst beim Schreiben in den Framebuffer -- siehe flush().
    "screen_width": 640,
    "screen_height": 480,
    "fb_rotate": 90,
    # Nach so vielen Minuten ohne Beruehrung zurueck in den Auslagern-Modus.
    # 0 schaltet den Ruecksprung ab.
    "idle_reset_minutes": 10,
    # Wie das Touchglas gegenueber dem Panel verbaut ist, steht in keinem
    # Datenblatt -- gemessen mit orient.py, siehe scanner.conf.
    "touch_swap_xy": 0,
    "touch_flip_x": 0,
    "touch_flip_y": 0,
    "backlight_timeout": 10,
    # Beim Start direkt in einen Modus springen, statt das Modus-Menue zu
    # zeigen: "out" (Auslagern), "in" (Einlagern, mit Lagerortauswahl),
    # oder leer fuer das bisherige Verhalten.
    "start_mode": "",
}


def load_config():
    cfg = DEFAULT_CONFIG.copy()
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    cfg[k.strip()] = v.strip()
    for k in ("screen_width", "screen_height", "backlight_timeout",
              "fb_rotate", "idle_reset_minutes", "touch_swap_xy", "touch_flip_x",
              "touch_flip_y"):
        cfg[k] = int(cfg[k])
    return cfg


