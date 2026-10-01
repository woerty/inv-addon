"""HTTP-Client fuer die Addon-API."""
import json
import time

import requests


class API:
    def __init__(self, base_url, token=""):
        self.base_url = base_url.rstrip("/")
        self.token = token

    def _headers(self):
        h = {"Content-Type": "application/json"}
        if self.token:
            h["X-Scanner-Token"] = self.token
        return h

    def _retry_request(self, method, url, **kwargs):
        """Request mit Wiederholung -- nur bei Netzfehlern und 5xx.

        Ein unlesbarer Rumpf wird NICHT wiederholt: scan-in ist nicht
        idempotent, und eine Wiederholung nach einer bereits verarbeiteten
        Anfrage bucht ein zweites Mal. Bei x12 waeren das bis zu 36 Anfragen.
        """
        for attempt in range(3):
            try:
                r = method(url, headers=self._headers(), timeout=5, **kwargs)
            except requests.RequestException as e:
                if attempt < 2:
                    time.sleep(0.5)
                    continue
                return None, str(e)
            if r.status_code >= 500 and attempt < 2:
                time.sleep(0.5)
                continue
            try:
                return r.status_code, r.json()
            except ValueError:
                # Der Server hat die Anfrage verarbeitet, nur die Antwort ist
                # unlesbar. Nicht wiederholen.
                return r.status_code, None
        return None, "max retries exceeded"


    def get_locations(self):
        """Returns list of {id, name} or None on error."""
        try:
            r = requests.get(f"{self.base_url}/storage-locations/",
                             headers=self._headers(), timeout=5)
            if r.status_code == 200:
                return r.json()
            return None
        except requests.RequestException:
            return None

    def scan_out(self, barcode):
        return self._retry_request(
            requests.post,
            f"{self.base_url}/inventory/scan-out",
            data=json.dumps({"barcode": barcode}),
        )

    def scan_in(self, barcode, storage_location_id=None):
        body = {"barcode": barcode}
        if storage_location_id is not None:
            body["storage_location_id"] = storage_location_id
        return self._retry_request(
            requests.post,
            f"{self.base_url}/inventory/scan-in",
            data=json.dumps(body),
        )


