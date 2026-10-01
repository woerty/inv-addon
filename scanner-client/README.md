# Scanner-Client

Läuft auf dem Barcode-Terminal (`scanner.local`, Raspberry Pi 3A+, 2,8" DPI-Panel).

    scanner.py            Einstiegspunkt, vom systemd-Dienst gestartet
    scannerlib/           die Logik
    scanner.conf          Konfiguration (Gerätepfade, Kalibrierung, Startmodus)
    tests/                unittest, läuft auf dem Gerät

Aufspielen:

    scp -r scannerlib scanner.py scanner.conf dstn@scanner.local:~/
    ssh dstn@scanner.local 'sudo systemctl restart scanner'

Tests:

    ssh dstn@scanner.local 'cd ~ && python3 -m unittest discover tests -v'
