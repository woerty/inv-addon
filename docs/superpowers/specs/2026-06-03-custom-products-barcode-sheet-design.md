# Eigene Produkte + A4-Barcode-Blatt — Design

**Datum:** 2026-06-03
**Status:** Genehmigt (Brainstorming)

## Kontext & Ziel

Zwei eng verwandte, aber unabhängige Features rund um die Inventar-Seite:

- **Feature A — Eigene Produkte:** Produkte selbst anlegen (z. B. „Banane"), die keinen echten EAN/Verpackungs-Barcode haben. Das System vergibt automatisch eine kollisionsfreie Nummer. Über das A4-Blatt (Feature B) gedruckt, an den Kühlschrank geklebt und gescannt zum Hinzufügen/Entfernen.
- **Feature B — A4-Barcode-Blatt:** Druckbares A4-PDF mit Barcodes. Pro Inventar-Produkt umschaltbar, ob es aufs Blatt soll. Gilt für eigene *und* echte Produkte — z. B. Pizza, deren Pappe mit dem Barcode weggeworfen wird.

Beide Features werden zusammen gebaut und getestet, weil sie sich die Inventar-Seite und das Barcode-Thema teilen.

Nicht Teil dieser Spec: Picnic-Auto-Nachbestellungs-Bug (#1, wird separat getestet/debuggt) und Bundle-Angebote-Untersuchung (#2, separate Untersuchung danach).

## Feature A — Eigene Produkte

### Workflow
1. Auf der Inventar-Seite: Button „Eigenes Produkt anlegen" → Dialog mit **Name** (Pflicht) sowie optional **Kategorie** und **Lagerort**.
2. Backend erzeugt eine kollisionsfreie Barcode-Nummer nach dem im Code etablierten synthetischen Muster (analog `picnic:<id>`): **`EIGEN-<token>`**, wobei `<token>` ein eindeutiger, gegen vorhandene Barcodes kollisionsfreier Wert ist (z. B. `uuid4().hex[:12]`).
3. Es wird **kein externer Barcode-Lookup** (OpenFoodFacts etc.) durchgeführt — Name/Kategorie kommen direkt vom Nutzer.
4. Das Item wird wie ein normales `InventoryItem` gespeichert (Menge initial 0 oder vom Dialog gesetzt).

### Scannen
- Beim Scannen (`scan-in`, `scan-out`, `barcode`) erkennt das Backend am Präfix `EIGEN-`, dass es ein eigenes Produkt ist, und **überspringt den `lookup_barcode()`-Aufruf**.
- Hinzufügen/Entfernen läuft sonst exakt wie bei normalen Produkten; der bestehende Modus-Schalter der Scan-Station (`ScanStationPage`) entscheidet add/remove. Kein zweiter Barcode nötig.
- Scannt man einen `EIGEN-`-Code, der **nicht** existiert (z. B. nach versehentlichem Löschen) → klare Fehlermeldung („Unbekanntes eigenes Produkt — bitte erst anlegen"), **kein** Auto-Anlegen (Name unbekannt).

### Löschen bei Menge 0 (eigene Produkte erhalten)
- Aktuell löscht `_apply_decrement` (`routers/inventory.py:89`) ein Item bei Menge ≤ 0, außer es existiert eine `TrackedProduct`-Regel (→ „Zombie"-Zeile bleibt).
- **Erweiterung:** Eigene Produkte (`EIGEN-`-Präfix) werden bei Menge 0 **ebenfalls als Zombie-Zeile behalten**, nie gelöscht. Damit bleibt der gedruckte Code am Kühlschrank gültig.
- `include_in_sheet` hat **keinen** Einfluss aufs Löschen. Geflaggte **echte** Produkte (Pizza) werden wie alle anderen behandelt — beim erneuten Scannen ihres echten EANs werden sie ohnehin per Lookup neu angelegt, es verwaist nichts.

## Feature B — A4-Barcode-Blatt

### Auswahl
- Neue Spalte `include_in_sheet: bool` (default `false`) auf `InventoryItem`.
- Pro Zeile in der Inventar-Tabelle ein Schalter „auf PDF" (an/aus). Gilt für eigene *und* echte Produkte.

### Erzeugen
- Button „Barcode-Blatt herunterladen" auf der Inventar-Seite → `GET /api/inventory/barcode-sheet.pdf`.
- Rendert alle Items mit `include_in_sheet=true` als A4-Raster.
- Pro Zelle: ein **Code128-Barcode** des Barcode-Werts + der Produktname als Beschriftung darunter.
- Code128 funktioniert mit demselben Generator für echte EANs *und* `EIGEN-`-Codes.
- Bei leerer Auswahl: PDF mit Hinweis oder 400 mit klarer Meldung (Implementierung: leeres Blatt mit Hinweistext bevorzugt, damit der Download nie „kaputt" wirkt).

### Bibliothek
- **`reportlab`** (neue Dependency in `pyproject.toml`). reportlab bringt Code128 über `reportlab.graphics.barcode.code128.Code128` eingebaut mit — **keine** zusätzliche `python-barcode`-Dependency nötig.

## Komponenten & Schnittstellen

### Backend
- **Migration:** Alembic-Revision fügt `include_in_sheet` (bool, default false, not null) zu `inventory_items` hinzu.
- **Helper:** `app/services/custom_products.py` (oder Erweiterung von `tracked_products.py`): `CUSTOM_BARCODE_PREFIX = "EIGEN-"`, `is_custom_barcode(barcode)`, `make_custom_barcode()`.
- **Endpoint `POST /api/inventory/custom`:** Body `CustomProductCreate {name, category?, storage_location?, quantity?}`. Generiert `EIGEN-`-Barcode, legt Item ohne Lookup an, gibt `InventoryItemResponse` zurück.
- **Scan-Pfade (`scan-in`, `scan-out`, `barcode`):** Lookup überspringen, wenn `is_custom_barcode(barcode)`. Bei `scan-in` eines unbekannten `EIGEN-`-Codes Fehler statt Auto-Anlage.
- **`_apply_decrement`:** Lösch-Bedingung (Zeile 89) erweitern: behalten, wenn `tracked is not None` **oder** `is_custom_barcode(item.barcode)`.
- **Update-Pfad (`InventoryUpdateRequest`):** Feld `include_in_sheet: bool | None` ergänzen, im Update-Endpoint setzen.
- **Endpoint `GET /api/inventory/barcode-sheet.pdf`:** Erzeugt PDF aus allen geflaggten Items via reportlab, `Content-Type: application/pdf`.

### Frontend
- **Inventar-Seite (`InventoryPage.tsx`):**
  - Button „Eigenes Produkt anlegen" → Dialog (Name + optional Kategorie/Lagerort).
  - Pro Zeile Schalter/Checkbox „auf PDF" (toggelt `include_in_sheet`).
  - Button „Barcode-Blatt herunterladen" → öffnet/downloadet `barcode-sheet.pdf`.
- **API-Client (`api/client.ts`):** `createCustomProduct()`, `updateInventoryItem()` um `include_in_sheet` erweitern, `barcodeSheetUrl()`/Download-Helper.
- **Hook (`useInventory`):** ggf. um Create-Custom + Toggle erweitern.

## Datenfluss
1. Anlegen: UI-Dialog → `POST /inventory/custom` → `EIGEN-`-Item in DB.
2. Flaggen: UI-Toggle → Update-Endpoint setzt `include_in_sheet`.
3. Drucken: UI-Button → `GET barcode-sheet.pdf` → reportlab rendert geflaggte Items → Download.
4. Scannen: Kamera/Eingabe → Scan-Endpoint erkennt `EIGEN-` → ohne Lookup add/remove; bei Menge 0 bleibt eigenes Produkt erhalten.

## Fehlerbehandlung
- Anlegen ohne Name → 422 (Pydantic).
- Scan eines unbekannten `EIGEN-`-Codes → 404/klare Meldung.
- Barcode-Sheet ohne geflaggte Items → PDF mit Hinweistext (kein harter Fehler).
- PDF-Erzeugung schlägt fehl → 500 mit Log; Frontend zeigt Fehlermeldung.

## Tests
- **Backend:**
  - `POST /inventory/custom` erzeugt `EIGEN-`-Barcode, ruft `lookup_barcode` **nicht** auf, legt Item an.
  - Scan-in/out eines eigenen Produkts funktioniert ohne externen Lookup.
  - Scan-in eines unbekannten `EIGEN-`-Codes → Fehler.
  - Zombie-Verhalten: eigenes Produkt bei Menge 0 bleibt erhalten; echtes (nur geflaggtes) Produkt ohne Tracking-Regel wird wie bisher gelöscht.
  - `include_in_sheet`-Toggle persistiert.
  - `GET /inventory/barcode-sheet.pdf` → 200, `Content-Type: application/pdf`, nicht-leerer Body; enthält nur geflaggte Items (Prüfung über Item-Anzahl/leichten Smoke-Test, PDF-Inhalt nicht tief assertet).
- **Frontend:** manueller Smoke-Test (Anlegen, Flaggen, Download, Scannen).

## Bewusst weggelassen (YAGNI)
- Mengen-/Lieferanten-Verwaltung für eigene Produkte.
- Auswahl der Barcode-Symbologie (Code128 fest).
- Konfigurierbares Blatt-Layout (festes A4-Raster).
- Bearbeiten der auto-vergebenen `EIGEN-`-Nummer.
