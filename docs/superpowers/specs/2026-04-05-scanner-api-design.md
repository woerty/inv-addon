# Scanner API Design

**Status:** API contract only. Pi-client design (TUI, config, autostart) lives in a separate spec once that track is ready to be finalized.

**Purpose:** Define the HTTP contract between a remote barcode-scanner client (initially a Raspberry Pi) and the Recipe Assistant backend, so the scanner and backend tracks can progress in parallel without ambiguity.

**Scope:** Scan-**out** only. No scan-in, no multi-quantity, no inventory browse.

---

## Constraints and assumptions

- Backend runs inside the Home Assistant addon container and binds to port 8080.
- Scanner client is on the same local LAN as the HA host. It does **not** go through HA ingress.
- HA host is reachable from the internet on ports the user's router forwards (typically 8123). The scanner port is **not** forwarded, so the scan endpoint is LAN-only by default.
- The rest of the inventory API is unauthenticated today — it relies on HA ingress auth. The scanner endpoint must not weaken that posture, and should allow opt-in auth for users who want LAN-hardening.

---

## Network path

A new host port is exposed by the HA addon via a `ports` mapping in `config.json`:

```json
"ports": {
  "8080/tcp": 8099
}
```

The scanner client reaches the backend at:

```
http://<ha-host-ip>:8099/api/inventory/scan-out
```

Port 8099 is the default; users can remap on the HA side. The choice avoids common collisions (80, 8080, 8123).

Ingress continues to work unchanged — the addon still listens on 8080 internally and HA ingress still proxies to it. The `ports` mapping is purely additive.

---

## Endpoint

### `POST /api/inventory/scan-out`

Decrements the inventory count for the given barcode by exactly one. If the remaining quantity would drop to zero, the item is deleted from inventory.

A new, dedicated endpoint (not an extension of `/inventory/remove`) because:

1. `/inventory/remove` returns `{"message": "<free German text>"}` — not parseable by a terminal client that needs to show item name and remaining count.
2. A dedicated endpoint gives us a stable contract we can version separately from the web UI's API.
3. Leaving `/remove` untouched guarantees no regression in the existing frontend.

---

## Request

**Headers:**

| Header | Required | Description |
|---|---|---|
| `Content-Type` | yes | `application/json` |
| `X-Scanner-Token` | conditional | Required **only** if `scanner_token` is configured non-empty in HA addon options. Otherwise ignored. |

**Body:**

```json
{
  "barcode": "4000417025005"
}
```

| Field | Type | Required | Description |
|---|---|---|---|
| `barcode` | string | yes | EAN / UPC / arbitrary code from the scanner. Backend does not validate format. |

**Quantity semantics:** one request = one decrement. Multiple units require multiple requests. No `quantity` field. This matches physical scanning behavior and keeps the contract trivial.

---

## Responses

All responses are JSON. The `status` field is a stable enum the client can branch on without parsing text.

### 200 OK — successful decrement, item still in stock

```json
{
  "status": "ok",
  "barcode": "4000417025005",
  "name": "Spaghetti Barilla 500g",
  "remaining_quantity": 3,
  "deleted": false
}
```

### 200 OK — successful decrement, last unit removed

```json
{
  "status": "ok",
  "barcode": "4000417025005",
  "name": "Spaghetti Barilla 500g",
  "remaining_quantity": 0,
  "deleted": true
}
```

When the scanned item had `quantity == 1` before the request, the row is deleted from inventory. The response still echoes the item's `name` so the client can show the user what was just removed.

### 404 Not Found — barcode not in inventory

```json
{
  "status": "not_found",
  "barcode": "4000417025005",
  "error": "Kein Artikel mit diesem Barcode im Inventar"
}
```

The client should treat this as a user-facing warning (not an error), display it as "unknown barcode", and continue to accept the next scan.

### 401 Unauthorized — token check failed

```json
{
  "status": "unauthorized",
  "error": "Invalid or missing X-Scanner-Token"
}
```

Returned only when `scanner_token` is configured non-empty on the backend and the request header does not match. The client should treat this as a configuration error, show it prominently, and **not** retry automatically.

### 5xx — server error

Standard FastAPI error envelope. The client should retry (see "Retry policy" below).

---

## Response schema (all fields)

| Field | Type | When present |
|---|---|---|
| `status` | `"ok"` \| `"not_found"` \| `"unauthorized"` | always |
| `barcode` | string | `ok`, `not_found` |
| `name` | string | `ok` |
| `remaining_quantity` | integer (≥0) | `ok` |
| `deleted` | boolean | `ok` |
| `error` | string | `not_found`, `unauthorized` |

`name` is the item's display name as stored in `inventory_items.name`.

---

## Auth

The scanner endpoint supports an optional shared-secret token, controlled by a new HA addon option:

```json
// config.json options
{
  "scanner_token": ""
}
```

Schema: `"scanner_token": "password?"` (optional, treated as secret in HA UI).

**Behavior:**

- If `scanner_token` is **empty** (default): the endpoint accepts requests with or without `X-Scanner-Token`. Posture matches the rest of the inventory API — LAN trust only.
- If `scanner_token` is **non-empty**: every request must include a matching `X-Scanner-Token` header. Comparison uses `hmac.compare_digest` (constant-time).

The token check applies **only** to `POST /api/inventory/scan-out`. All other endpoints are unchanged.

Rationale: zero-friction default for the common home-LAN case, opt-in hardening for users on shared/IoT VLANs. No breaking change, no required client config.

---

## Retry policy (client-side contract)

The client SHOULD implement this retry behavior. It is documented here so both tracks agree on the HTTP semantics.

| Response | Retry? | Notes |
|---|---|---|
| Network error / timeout | yes, 2× with 500 ms delay | transient |
| 5xx | yes, 2× with 500 ms delay | transient |
| 200 | no | done |
| 404 | **no** | user-facing outcome, not an error |
| 401 | **no** | config error, needs human intervention |

After exhausting retries the client surfaces a "network error" state and accepts the next scan. No offline queue in v1 — losing an occasional scan when the addon is down is acceptable.

The backend is idempotent in the sense that a 404 will never mutate state, but it is **not** idempotent on `ok` — retrying after a 200 would decrement twice. The client must therefore only retry on network failures and 5xx, never on 2xx or 4xx.

---

## Backend implementation outline

Files touched (for the implementation track — not binding for the scanner track):

- `recipe-assistant/backend/app/schemas/inventory.py` — add `ScanOutRequest`, `ScanOutResponse`, `ScanOutErrorResponse`.
- `recipe-assistant/backend/app/routers/inventory.py` — add the `POST /scan-out` handler. Reuses the same SELECT / decrement / delete logic as the existing `/remove` handler, but returns structured JSON.
- `recipe-assistant/backend/app/config.py` — add `scanner_token: str = ""`.
- `recipe-assistant/backend/app/deps.py` (new) — `verify_scanner_token` dependency, no-op when token is empty.
- `recipe-assistant/config.json` — add `"scanner_token": ""` under `options`, `"scanner_token": "password?"` under `schema`, and the `"ports": {"8080/tcp": 8099}` mapping.

## Tests (backend)

Added to the existing backend pytest suite:

1. `test_scan_out_decrements_quantity` — item with quantity 3, one scan, expect 200 with `remaining_quantity: 2`, `deleted: false`.
2. `test_scan_out_deletes_last_unit` — item with quantity 1, one scan, expect 200 with `remaining_quantity: 0`, `deleted: true`, row gone from DB.
3. `test_scan_out_returns_404_for_unknown_barcode` — expect 404 with `status: "not_found"`.
4. `test_scan_out_requires_token_when_configured` — with `scanner_token` set, request without header → 401.
5. `test_scan_out_accepts_correct_token` — with `scanner_token` set, matching header → 200.
6. `test_scan_out_ignores_token_when_unconfigured` — with empty `scanner_token`, request with arbitrary header → 200 (header ignored).

---

## Out of scope

- Scan-**in** (adding items). Existing `/inventory/barcode` handles that path for the web UI.
- Multi-quantity per request.
- Any kind of cursor/browse API for the scanner client.
- Offline queueing on the client.
- Long-lived HA access tokens as an alternative auth method.
- Rate limiting. The scanner is human-driven, a few scans per minute at most.
