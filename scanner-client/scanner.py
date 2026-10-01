#!/usr/bin/env python3
"""Barcode-Scanner-Client. Die Logik liegt in scannerlib/."""
import sys

from scannerlib.app import App
from scannerlib.config import load_config


def main():
    # systemd haengt stdout an eine Pipe -- ohne das hier puffert Python
    # blockweise und im Journal steht tagelang gar nichts.
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except (AttributeError, OSError):
        pass
    App(load_config()).run()


if __name__ == "__main__":
    main()
