# Picnic Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate Picnic (DE) grocery service to enable cart-sync re-ordering from an in-app shopping list and on-demand import of delivered Picnic orders into the inventory, bridging the EAN ↔ Picnic product ID gap via a learned mapping table.

**Architecture:** New `services/picnic/` sub-package wraps `python-picnic-api2` with a thin client, a catalog cache, a fuzzy matcher, an import-flow orchestrator, and a cart-sync module. Four new DB tables (`picnic_products`, `ean_picnic_map`, `picnic_delivery_imports`, `shopping_list`) are added via an additive Alembic migration; existing `InventoryItem` schema is untouched. Frontend adds two pages (PicnicImportPage, ShoppingListPage) + hook + components. Feature is gated by presence of `PICNIC_EMAIL` in addon config.

**Tech Stack:** FastAPI (async), SQLAlchemy 2.0 async, Alembic, Pydantic v2, `python-picnic-api2`, `rapidfuzz`, React + TypeScript, Vite, react-router-dom.

**Spec:** `docs/superpowers/specs/2026-04-05-picnic-integration-design.md`

---

## Task 1: Add Dependencies & HA Addon Config Schema

**Files:**
- Modify: `recipe-assistant/backend/pyproject.toml`
- Modify: `recipe-assistant/Dockerfile`
- Modify: `recipe-assistant/config.json`
- Modify: `recipe-assistant/backend/app/config.py`

- [ ] **Step 1: Add Python deps to `pyproject.toml`**

Edit `recipe-assistant/backend/pyproject.toml`, add to the `dependencies` list (keep existing entries, add these two):

```toml
    "python-picnic-api2>=1.3.0",
    "rapidfuzz>=3.10.0",
```

- [ ] **Step 2: Add same deps to `Dockerfile`**

Edit the `pip install --no-cache-dir` block in `recipe-assistant/Dockerfile`, append:

```dockerfile
    "python-picnic-api2>=1.3.0" \
    "rapidfuzz>=3.10.0"
```

Make sure the trailing backslash on the previous line (`"python-multipart>=0.0.18"`) is added so the continuation works.

- [ ] **Step 3: Extend HA addon `config.json`**

Replace `recipe-assistant/config.json` options + schema sections with:

```json
  "options": {
    "anthropic_api_key": "",
    "openai_api_key": "",
    "picnic_email": "",
    "picnic_password": "",
    "picnic_country_code": "DE"
  },
  "schema": {
    "anthropic_api_key": "password",
    "openai_api_key": "password",
    "picnic_email": "str?",
    "picnic_password": "password?",
    "picnic_country_code": "str?"
  }
```

The `?` suffix marks fields as optional so existing users without Picnic are not forced to fill them.

- [ ] **Step 4: Extend `Settings` in `config.py`**

Edit `recipe-assistant/backend/app/config.py`. Add three fields inside the `Settings` class:

```python
    picnic_email: str = ""
    picnic_password: str = ""
    picnic_country_code: str = "DE"
```

And extend `from_ha_options` to pass them through:

```python
    @classmethod
    def from_ha_options(cls) -> Settings:
        """Load settings from Home Assistant /data/options.json if it exists."""
        options_path = Path("/data/options.json")
        if options_path.exists():
            options = json.loads(options_path.read_text())
            return cls(
                database_url="postgresql+asyncpg://recipe:recipe@localhost:5432/recipe",
                anthropic_api_key=options.get("anthropic_api_key", ""),
                openai_api_key=options.get("openai_api_key", ""),
                picnic_email=options.get("picnic_email", ""),
                picnic_password=options.get("picnic_password", ""),
                picnic_country_code=options.get("picnic_country_code", "DE"),
                environment="production",
            )
        return cls()
```

- [ ] **Step 5: Install deps locally and verify import**

Run (from repo root):

```bash
cd recipe-assistant/backend && pip install -e ".[dev]" && python -c "import picnicapi; import rapidfuzz; print('ok')"
```

Expected: `ok` printed, no import errors.

- [ ] **Step 6: Commit**

```bash
git add recipe-assistant/backend/pyproject.toml recipe-assistant/Dockerfile recipe-assistant/config.json recipe-assistant/backend/app/config.py
git commit -m "feat(picnic): add dependencies and addon config schema"
```

---

## Task 2: Data Model — Picnic Tables

**Files:**
- Create: `recipe-assistant/backend/app/models/picnic.py`
- Modify: `recipe-assistant/backend/app/models/__init__.py`
- Create: `recipe-assistant/backend/alembic/versions/003_add_picnic_tables.py`
- Modify: `recipe-assistant/backend/app/main.py`

- [ ] **Step 1: Create `models/picnic.py`**

Full file contents:

```python
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PicnicProduct(Base):
    """Cache of Picnic catalog entries, refreshed opportunistically."""
    __tablename__ = "picnic_products"

    picnic_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    brand: Mapped[str | None] = mapped_column(String, nullable=True)
    unit_quantity: Mapped[str | None] = mapped_column(String, nullable=True)
    image_id: Mapped[str | None] = mapped_column(String, nullable=True)
    last_price_cents: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_seen: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )


class EanPicnicMap(Base):
    """Bridge between EANs and Picnic product IDs. N:M via (ean, picnic_id) pair."""
    __tablename__ = "ean_picnic_map"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ean: Mapped[str] = mapped_column(String, nullable=False, index=True)
    picnic_id: Mapped[str] = mapped_column(
        String,
        ForeignKey("picnic_products.picnic_id", ondelete="CASCADE"),
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String, nullable=False)  # scan|user_confirmed|auto
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    __table_args__ = (UniqueConstraint("ean", "picnic_id", name="uq_ean_picnic"),)


class PicnicDeliveryImport(Base):
    """Dedup record of which Picnic deliveries have been imported."""
    __tablename__ = "picnic_delivery_imports"

    delivery_id: Mapped[str] = mapped_column(String, primary_key=True)
    imported_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    item_count: Mapped[int] = mapped_column(Integer, nullable=False)


class ShoppingListItem(Base):
    """In-app shopping list, flushed to Picnic cart on demand."""
    __tablename__ = "shopping_list"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    inventory_barcode: Mapped[str | None] = mapped_column(String, nullable=True)
    picnic_id: Mapped[str | None] = mapped_column(String, nullable=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    added_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
```

- [ ] **Step 2: Re-export from `models/__init__.py`**

Replace `recipe-assistant/backend/app/models/__init__.py` with:

```python
from app.models.inventory import InventoryItem, StorageLocation
from app.models.chat import ChatMessage
from app.models.log import InventoryLog
from app.models.person import Person
from app.models.picnic import (
    EanPicnicMap,
    PicnicDeliveryImport,
    PicnicProduct,
    ShoppingListItem,
)

__all__ = [
    "InventoryItem",
    "StorageLocation",
    "ChatMessage",
    "InventoryLog",
    "Person",
    "PicnicProduct",
    "EanPicnicMap",
    "PicnicDeliveryImport",
    "ShoppingListItem",
]
```

- [ ] **Step 3: Update sqlite auto-create import list in `main.py`**

In `recipe-assistant/backend/app/main.py`, find the line inside `lifespan`:

```python
        from app.models import InventoryItem, StorageLocation, ChatMessage, InventoryLog  # noqa: F401
```

Replace with:

```python
        from app.models import (  # noqa: F401
            InventoryItem,
            StorageLocation,
            ChatMessage,
            InventoryLog,
            Person,
            PicnicProduct,
            EanPicnicMap,
            PicnicDeliveryImport,
            ShoppingListItem,
        )
```

(Including `Person` because it's in the Postgres migration already but was missing here — a pre-existing minor inconsistency; include it while we're touching this line.)

- [ ] **Step 4: Create Alembic migration file**

Create `recipe-assistant/backend/alembic/versions/003_add_picnic_tables.py`:

```python
"""add picnic tables

Revision ID: 003
Revises: 002
Create Date: 2026-04-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "picnic_products",
        sa.Column("picnic_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("brand", sa.String(), nullable=True),
        sa.Column("unit_quantity", sa.String(), nullable=True),
        sa.Column("image_id", sa.String(), nullable=True),
        sa.Column("last_price_cents", sa.Integer(), nullable=True),
        sa.Column(
            "last_seen",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("picnic_id"),
    )

    op.create_table(
        "ean_picnic_map",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("ean", sa.String(), nullable=False),
        sa.Column("picnic_id", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["picnic_id"], ["picnic_products.picnic_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ean", "picnic_id", name="uq_ean_picnic"),
    )
    op.create_index("ix_ean_picnic_map_ean", "ean_picnic_map", ["ean"])

    op.create_table(
        "picnic_delivery_imports",
        sa.Column("delivery_id", sa.String(), nullable=False),
        sa.Column(
            "imported_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("item_count", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("delivery_id"),
    )

    op.create_table(
        "shopping_list",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("inventory_barcode", sa.String(), nullable=True),
        sa.Column("picnic_id", sa.String(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "added_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("shopping_list")
    op.drop_table("picnic_delivery_imports")
    op.drop_index("ix_ean_picnic_map_ean", table_name="ean_picnic_map")
    op.drop_table("ean_picnic_map")
    op.drop_table("picnic_products")
```

- [ ] **Step 5: Verify sqlite tables create cleanly**

Run from `recipe-assistant/backend`:

```bash
rm -f dev.db && python -c "
import asyncio
from app.database import Base, engine
from app.models import InventoryItem, StorageLocation, ChatMessage, InventoryLog, Person, PicnicProduct, EanPicnicMap, PicnicDeliveryImport, ShoppingListItem

async def main():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print('tables created')

asyncio.run(main())
"
```

Expected: `tables created`, no errors.

- [ ] **Step 6: Commit**

```bash
git add recipe-assistant/backend/app/models/picnic.py recipe-assistant/backend/app/models/__init__.py recipe-assistant/backend/app/main.py recipe-assistant/backend/alembic/versions/003_add_picnic_tables.py
git commit -m "feat(picnic): add database models and migration"
```

---

## Task 3: Pydantic Schemas

**Files:**
- Create: `recipe-assistant/backend/app/schemas/picnic.py`

- [ ] **Step 1: Create schema file**

Full file contents for `recipe-assistant/backend/app/schemas/picnic.py`:

```python
from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel


# --- Status ---

class PicnicStatusResponse(BaseModel):
    enabled: bool
    account: dict | None = None  # {"first_name": ..., "last_name": ..., "email": ...}


# --- Import flow ---

class MatchSuggestion(BaseModel):
    inventory_barcode: str
    inventory_name: str
    score: float  # 0-100
    reason: str


class ImportCandidate(BaseModel):
    picnic_id: str
    picnic_name: str
    picnic_image_id: str | None = None
    picnic_unit_quantity: str | None = None
    ordered_quantity: int
    match_suggestions: list[MatchSuggestion] = []
    best_confidence: float = 0.0


class ImportDelivery(BaseModel):
    delivery_id: str
    delivered_at: datetime | None = None
    items: list[ImportCandidate]


class ImportFetchResponse(BaseModel):
    deliveries: list[ImportDelivery]


class ImportDecision(BaseModel):
    picnic_id: str
    action: Literal["match_existing", "create_new", "skip"]
    target_barcode: str | None = None
    scanned_ean: str | None = None
    storage_location: str | None = None
    expiration_date: date | None = None


class ImportCommitRequest(BaseModel):
    delivery_id: str
    decisions: list[ImportDecision]


class ImportCommitResponse(BaseModel):
    imported: int
    created: int
    skipped: int
    promoted: int  # synthetic → real EAN promotions


# --- Shopping list ---

class ShoppingListItemResponse(BaseModel):
    id: int
    inventory_barcode: str | None
    picnic_id: str | None
    name: str
    quantity: int
    picnic_status: Literal["mapped", "unmapped", "missing"]
    added_at: datetime

    model_config = {"from_attributes": True}


class ShoppingListAddRequest(BaseModel):
    inventory_barcode: str | None = None
    picnic_id: str | None = None
    name: str
    quantity: int = 1


class ShoppingListUpdateRequest(BaseModel):
    quantity: int | None = None
    picnic_id: str | None = None


class CartSyncItemResult(BaseModel):
    shopping_list_id: int
    picnic_id: str | None
    status: Literal["added", "skipped_unmapped", "failed"]
    failure_reason: str | None = None


class CartSyncResponse(BaseModel):
    results: list[CartSyncItemResult]
    added_count: int
    failed_count: int
    skipped_count: int


# --- Search ---

class PicnicSearchResult(BaseModel):
    picnic_id: str
    name: str
    brand: str | None = None
    unit_quantity: str | None = None
    image_id: str | None = None
    price_cents: int | None = None


class PicnicSearchResponse(BaseModel):
    results: list[PicnicSearchResult]


# --- Mappings (admin) ---

class EanPicnicMapResponse(BaseModel):
    id: int
    ean: str
    picnic_id: str
    source: str
    created_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **Step 2: Verify schemas import**

```bash
cd recipe-assistant/backend && python -c "from app.schemas.picnic import ImportCommitRequest, CartSyncResponse; print('ok')"
```

Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add recipe-assistant/backend/app/schemas/picnic.py
git commit -m "feat(picnic): add pydantic schemas"
```

---

## Task 4: Matching Service (Name Normalization + Scorer)

This is the core bridge between Picnic names and inventory names. Pure functions, easy to TDD.

**Files:**
- Create: `recipe-assistant/backend/app/services/picnic/__init__.py`
- Create: `recipe-assistant/backend/app/services/picnic/matching.py`
- Create: `recipe-assistant/backend/tests/services/__init__.py`
- Create: `recipe-assistant/backend/tests/services/picnic/__init__.py`
- Create: `recipe-assistant/backend/tests/services/picnic/test_matching.py`

- [ ] **Step 1: Create empty package init files**

```bash
mkdir -p recipe-assistant/backend/app/services/picnic recipe-assistant/backend/tests/services/picnic
touch recipe-assistant/backend/app/services/picnic/__init__.py
touch recipe-assistant/backend/tests/services/__init__.py
touch recipe-assistant/backend/tests/services/picnic/__init__.py
```

- [ ] **Step 2: Write failing tests for `normalize_name`**

Create `recipe-assistant/backend/tests/services/picnic/test_matching.py`:

```python
import pytest

from app.services.picnic.matching import (
    MatchCandidate,
    compute_match_suggestions,
    confidence_tier,
    normalize_name,
    parse_unit_quantity,
)


class TestNormalizeName:
    @pytest.mark.parametrize("raw,expected", [
        ("Vollmilch 3,5%", "vollmilch"),
        ("Ja! Vollmilch 1 L", "ja vollmilch"),
        ("Alpro Mandel-Drink (ungesüßt) 1L", "alpro mandel drink"),
        ("Barilla Spaghetti Nr. 5 500g", "barilla spaghetti nr 5"),
        ("6 x 1,5L Apollinaris Classic", "apollinaris classic"),
        ("  Müller  Joghurt 500 g  ", "muller joghurt"),
    ])
    def test_strips_units_brackets_and_lowercases(self, raw, expected):
        assert normalize_name(raw) == expected


class TestParseUnitQuantity:
    @pytest.mark.parametrize("raw,expected", [
        ("500 g", ("g", 500.0)),
        ("1 L", ("ml", 1000.0)),
        ("1,5L", ("ml", 1500.0)),
        ("6 x 200 ml", ("ml", 1200.0)),
        ("10 Stück", ("count", 10.0)),
        ("unbekannt", None),
        (None, None),
    ])
    def test_parses_common_forms(self, raw, expected):
        assert parse_unit_quantity(raw) == expected


class TestComputeMatchSuggestions:
    def test_exact_name_match_scores_high(self):
        candidates = [
            MatchCandidate(barcode="111", name="Vollmilch 3,5%"),
            MatchCandidate(barcode="222", name="Apfelsaft"),
        ]
        suggestions = compute_match_suggestions(
            picnic_name="Ja! Vollmilch 1L",
            picnic_unit_quantity="1 L",
            candidates=candidates,
        )
        assert len(suggestions) >= 1
        top = suggestions[0]
        assert top.inventory_barcode == "111"
        assert top.score >= 92

    def test_unit_mismatch_still_matches_on_name(self):
        candidates = [MatchCandidate(barcode="111", name="Joghurt 500g")]
        suggestions = compute_match_suggestions(
            picnic_name="Joghurt 150g",
            picnic_unit_quantity="150 g",
            candidates=candidates,
        )
        assert len(suggestions) == 1
        # Name matches but units differ → no +10 bonus
        assert 60 <= suggestions[0].score < 92

    def test_no_match_below_threshold_excluded(self):
        candidates = [MatchCandidate(barcode="111", name="Äpfel")]
        suggestions = compute_match_suggestions(
            picnic_name="Katzenfutter",
            picnic_unit_quantity=None,
            candidates=candidates,
        )
        assert suggestions == []

    def test_top_5_limit(self):
        candidates = [
            MatchCandidate(barcode=str(i), name=f"Joghurt Variante {i}")
            for i in range(10)
        ]
        suggestions = compute_match_suggestions(
            picnic_name="Joghurt",
            picnic_unit_quantity=None,
            candidates=candidates,
        )
        assert len(suggestions) <= 5


class TestConfidenceTier:
    @pytest.mark.parametrize("score,tier", [
        (100, "confident"),
        (92, "confident"),
        (91, "uncertain"),
        (75, "uncertain"),
        (74, "weak"),
        (60, "weak"),
        (59, "none"),
    ])
    def test_tiers(self, score, tier):
        assert confidence_tier(score) == tier
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd recipe-assistant/backend && pytest tests/services/picnic/test_matching.py -v
```

Expected: `ImportError` or `ModuleNotFoundError` for `app.services.picnic.matching`.

- [ ] **Step 4: Implement `matching.py`**

Create `recipe-assistant/backend/app/services/picnic/matching.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from rapidfuzz import fuzz

CONFIDENT_THRESHOLD = 92
UNCERTAIN_THRESHOLD = 75
WEAK_THRESHOLD = 60
UNIT_BONUS = 10.0
UNIT_TOLERANCE = 0.10  # 10 percent

# Regex patterns for normalization
_PAREN_RE = re.compile(r"\([^)]*\)")
_UNIT_RE = re.compile(
    r"\b\d+(?:[.,]\d+)?\s*(?:g|kg|mg|l|ml|cl|stück|stk|x)\b",
    re.IGNORECASE,
)
_MULTI_RE = re.compile(r"\b\d+\s*x\s*", re.IGNORECASE)
_PUNCT_RE = re.compile(r"[^\w\s]")
_UMLAUT_MAP = str.maketrans({"ä": "a", "ö": "o", "ü": "u", "ß": "ss"})

Tier = Literal["confident", "uncertain", "weak", "none"]


@dataclass(frozen=True)
class MatchCandidate:
    """Minimal inventory item shape for matching. Decouples matcher from ORM."""
    barcode: str
    name: str


@dataclass(frozen=True)
class MatchSuggestionResult:
    inventory_barcode: str
    inventory_name: str
    score: float
    reason: str


def normalize_name(raw: str) -> str:
    """Lowercase, strip brand-in-parens, strip unit strings, collapse whitespace."""
    if not raw:
        return ""
    s = raw.lower().translate(_UMLAUT_MAP)
    s = _PAREN_RE.sub(" ", s)
    s = _MULTI_RE.sub(" ", s)
    s = _UNIT_RE.sub(" ", s)
    s = _PUNCT_RE.sub(" ", s)
    # Remove common brand markers like "ja!"
    s = re.sub(r"\bja\b", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


_UNIT_PARSE_RE = re.compile(
    r"(?:(\d+)\s*x\s*)?(\d+(?:[.,]\d+)?)\s*(g|kg|mg|l|ml|cl|stück|stk)",
    re.IGNORECASE,
)


def parse_unit_quantity(raw: str | None) -> tuple[str, float] | None:
    """Parse a unit quantity string into a canonical (unit, amount) tuple.

    Canonical units: 'g' for mass, 'ml' for volume, 'count' for items.
    Multi-packs (e.g. '6 x 200 ml') are multiplied out.
    """
    if not raw:
        return None
    match = _UNIT_PARSE_RE.search(raw)
    if not match:
        return None
    multi_s, qty_s, unit_s = match.groups()
    multi = int(multi_s) if multi_s else 1
    qty = float(qty_s.replace(",", "."))
    unit = unit_s.lower()

    total = multi * qty
    if unit == "kg":
        return ("g", total * 1000)
    if unit == "mg":
        return ("g", total / 1000)
    if unit == "g":
        return ("g", total)
    if unit == "l":
        return ("ml", total * 1000)
    if unit == "cl":
        return ("ml", total * 10)
    if unit == "ml":
        return ("ml", total)
    if unit in ("stück", "stk"):
        return ("count", total)
    return None


def _units_match(a: tuple[str, float] | None, b: tuple[str, float] | None) -> bool:
    if a is None or b is None:
        return False
    if a[0] != b[0]:
        return False
    bigger = max(a[1], b[1])
    if bigger == 0:
        return False
    return abs(a[1] - b[1]) / bigger <= UNIT_TOLERANCE


def compute_match_suggestions(
    picnic_name: str,
    picnic_unit_quantity: str | None,
    candidates: list[MatchCandidate],
) -> list[MatchSuggestionResult]:
    """Return top-5 matches, sorted by score desc, filtered to score >= WEAK_THRESHOLD."""
    picnic_norm = normalize_name(picnic_name)
    picnic_unit = parse_unit_quantity(picnic_unit_quantity)

    results: list[MatchSuggestionResult] = []
    for cand in candidates:
        cand_norm = normalize_name(cand.name)
        if not cand_norm or not picnic_norm:
            continue
        score = float(fuzz.token_set_ratio(picnic_norm, cand_norm))
        reason_parts = ["name match"]

        if picnic_unit:
            cand_unit = parse_unit_quantity(cand.name)
            if _units_match(picnic_unit, cand_unit):
                score = min(100.0, score + UNIT_BONUS)
                reason_parts.append("unit match")

        if score >= WEAK_THRESHOLD:
            results.append(
                MatchSuggestionResult(
                    inventory_barcode=cand.barcode,
                    inventory_name=cand.name,
                    score=score,
                    reason=" + ".join(reason_parts),
                )
            )

    results.sort(key=lambda r: r.score, reverse=True)
    return results[:5]


def confidence_tier(score: float) -> Tier:
    if score >= CONFIDENT_THRESHOLD:
        return "confident"
    if score >= UNCERTAIN_THRESHOLD:
        return "uncertain"
    if score >= WEAK_THRESHOLD:
        return "weak"
    return "none"
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd recipe-assistant/backend && pytest tests/services/picnic/test_matching.py -v
```

Expected: all tests PASS. If any fail due to the `normalize_name` edge cases (umlauts, "Ja!" brand), adjust the regex in the implementation — not the test — until green.

- [ ] **Step 6: Commit**

```bash
git add recipe-assistant/backend/app/services/picnic/__init__.py recipe-assistant/backend/app/services/picnic/matching.py recipe-assistant/backend/tests/services/ recipe-assistant/backend/tests/services/picnic/
git commit -m "feat(picnic): add fuzzy matching service"
```

---

## Task 5: Catalog Cache Service

**Files:**
- Create: `recipe-assistant/backend/app/services/picnic/catalog.py`
- Create: `recipe-assistant/backend/tests/services/picnic/test_catalog.py`

- [ ] **Step 1: Write failing tests for `upsert_product` + `get_product`**

Create `recipe-assistant/backend/tests/services/picnic/test_catalog.py`:

```python
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models.picnic import PicnicProduct
from app.services.picnic.catalog import (
    PicnicProductData,
    get_product,
    upsert_product,
)

TEST_DB = "sqlite+aiosqlite:///./test_catalog.db"


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(TEST_DB, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        yield s
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_upsert_product_creates(session: AsyncSession):
    data = PicnicProductData(
        picnic_id="s1",
        name="Vollmilch 1L",
        brand="Ja!",
        unit_quantity="1 L",
        image_id="img-1",
        last_price_cents=99,
    )
    await upsert_product(session, data)
    await session.commit()

    row = await get_product(session, "s1")
    assert row is not None
    assert row.name == "Vollmilch 1L"
    assert row.last_price_cents == 99


@pytest.mark.asyncio
async def test_upsert_product_updates_existing(session: AsyncSession):
    data1 = PicnicProductData(picnic_id="s1", name="Old Name", brand=None,
                              unit_quantity=None, image_id=None, last_price_cents=100)
    await upsert_product(session, data1)
    await session.commit()

    data2 = PicnicProductData(picnic_id="s1", name="New Name", brand=None,
                              unit_quantity=None, image_id=None, last_price_cents=120)
    await upsert_product(session, data2)
    await session.commit()

    row = await get_product(session, "s1")
    assert row.name == "New Name"
    assert row.last_price_cents == 120


@pytest.mark.asyncio
async def test_get_product_missing_returns_none(session: AsyncSession):
    row = await get_product(session, "does-not-exist")
    assert row is None
```

- [ ] **Step 2: Run to verify failure**

```bash
cd recipe-assistant/backend && pytest tests/services/picnic/test_catalog.py -v
```

Expected: ImportError for `app.services.picnic.catalog`.

- [ ] **Step 3: Implement `catalog.py`**

Create `recipe-assistant/backend/app/services/picnic/catalog.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.picnic import PicnicProduct


@dataclass(frozen=True)
class PicnicProductData:
    picnic_id: str
    name: str
    brand: str | None
    unit_quantity: str | None
    image_id: str | None
    last_price_cents: int | None


async def get_product(session: AsyncSession, picnic_id: str) -> PicnicProduct | None:
    result = await session.execute(
        select(PicnicProduct).where(PicnicProduct.picnic_id == picnic_id)
    )
    return result.scalar_one_or_none()


async def upsert_product(session: AsyncSession, data: PicnicProductData) -> PicnicProduct:
    """Insert a new PicnicProduct or update all mutable fields on an existing row."""
    existing = await get_product(session, data.picnic_id)
    if existing:
        existing.name = data.name
        existing.brand = data.brand
        existing.unit_quantity = data.unit_quantity
        existing.image_id = data.image_id
        existing.last_price_cents = data.last_price_cents
        return existing

    row = PicnicProduct(
        picnic_id=data.picnic_id,
        name=data.name,
        brand=data.brand,
        unit_quantity=data.unit_quantity,
        image_id=data.image_id,
        last_price_cents=data.last_price_cents,
    )
    session.add(row)
    await session.flush()
    return row
```

- [ ] **Step 4: Run tests**

```bash
cd recipe-assistant/backend && pytest tests/services/picnic/test_catalog.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add recipe-assistant/backend/app/services/picnic/catalog.py recipe-assistant/backend/tests/services/picnic/test_catalog.py
git commit -m "feat(picnic): add catalog cache service"
```

---

## Task 6: Picnic Client Wrapper + Fake for Tests

**Files:**
- Create: `recipe-assistant/backend/app/services/picnic/client.py`
- Create: `recipe-assistant/backend/tests/fixtures/__init__.py`
- Create: `recipe-assistant/backend/tests/fixtures/picnic/__init__.py`
- Create: `recipe-assistant/backend/tests/fixtures/picnic/fake_client.py`
- Create: `recipe-assistant/backend/tests/fixtures/picnic/sample_deliveries.py`

- [ ] **Step 1: Create the abstract client interface + real wrapper**

Create `recipe-assistant/backend/app/services/picnic/client.py`:

```python
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Protocol

from app.config import get_settings

log = logging.getLogger("picnic.client")

TOKEN_CACHE_PATH = Path("/data/picnic_token.json")


class PicnicClientProtocol(Protocol):
    """Minimal interface we use. Lets tests swap in a FakePicnicClient."""

    async def search(self, query: str) -> list[dict[str, Any]]: ...
    async def get_deliveries(self, summary: bool = True) -> list[dict[str, Any]]: ...
    async def get_delivery(self, delivery_id: str) -> dict[str, Any]: ...
    async def get_cart(self) -> dict[str, Any]: ...
    async def add_product(self, picnic_id: str, count: int = 1) -> dict[str, Any]: ...
    async def get_user(self) -> dict[str, Any]: ...


class PicnicClient:
    """Thin async wrapper around python-picnic-api2 (which is sync).
    
    Uses asyncio.to_thread to avoid blocking the event loop. Auto re-logins once
    on 401. Token is cached in /data/picnic_token.json.
    """

    def __init__(self) -> None:
        self._inner = None  # lazy init
        self._lock = asyncio.Lock()

    def _load_token(self) -> str | None:
        if TOKEN_CACHE_PATH.exists():
            try:
                return json.loads(TOKEN_CACHE_PATH.read_text()).get("token")
            except Exception:
                return None
        return None

    def _save_token(self, token: str) -> None:
        try:
            TOKEN_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
            TOKEN_CACHE_PATH.write_text(json.dumps({"token": token}))
        except Exception as e:
            log.warning("could not persist picnic token: %s", e)

    async def _ensure_ready(self) -> None:
        if self._inner is not None:
            return
        async with self._lock:
            if self._inner is not None:
                return
            from picnicapi import PicnicAPI  # import inside to allow tests to stub
            settings = get_settings()
            if not settings.picnic_email or not settings.picnic_password:
                raise PicnicNotConfigured("PICNIC_EMAIL / PICNIC_PASSWORD not set")

            def _login() -> Any:
                api = PicnicAPI(
                    username=settings.picnic_email,
                    password=settings.picnic_password,
                    country_code=settings.picnic_country_code or "DE",
                )
                return api

            self._inner = await asyncio.to_thread(_login)
            try:
                token = getattr(self._inner.session, "auth_token", None)
                if token:
                    self._save_token(token)
            except Exception:
                pass

    async def _call(self, method_name: str, *args, **kwargs) -> Any:
        await self._ensure_ready()
        assert self._inner is not None

        def _do():
            return getattr(self._inner, method_name)(*args, **kwargs)

        try:
            return await asyncio.to_thread(_do)
        except Exception as e:
            # Force re-login once on auth errors
            if _is_auth_error(e):
                log.info("picnic auth error, retrying after re-login: %s", e)
                self._inner = None
                await self._ensure_ready()
                return await asyncio.to_thread(_do)
            raise

    async def search(self, query: str) -> list[dict[str, Any]]:
        return await self._call("search", query)

    async def get_deliveries(self, summary: bool = True) -> list[dict[str, Any]]:
        return await self._call("get_deliveries", summary=summary)

    async def get_delivery(self, delivery_id: str) -> dict[str, Any]:
        return await self._call("get_delivery", delivery_id)

    async def get_cart(self) -> dict[str, Any]:
        return await self._call("get_cart")

    async def add_product(self, picnic_id: str, count: int = 1) -> dict[str, Any]:
        return await self._call("add_product", picnic_id, count=count)

    async def get_user(self) -> dict[str, Any]:
        return await self._call("get_user")


class PicnicNotConfigured(Exception):
    """Raised when PICNIC_EMAIL / PICNIC_PASSWORD are absent."""


def _is_auth_error(exc: Exception) -> bool:
    # python-picnic-api2 raises generic errors with status in message
    s = str(exc).lower()
    return "401" in s or "unauthor" in s or "auth" in s


# --- FastAPI dependency ---

_client_singleton: PicnicClient | None = None


def get_picnic_client() -> PicnicClientProtocol:
    """FastAPI dependency. Tests override this via app.dependency_overrides."""
    global _client_singleton
    if _client_singleton is None:
        _client_singleton = PicnicClient()
    return _client_singleton
```

- [ ] **Step 2: Create sample fixture data**

Create `recipe-assistant/backend/tests/fixtures/__init__.py` (empty) and `recipe-assistant/backend/tests/fixtures/picnic/__init__.py` (empty).

Create `recipe-assistant/backend/tests/fixtures/picnic/sample_deliveries.py`:

```python
"""Sanitized sample responses shaped like python-picnic-api2 output."""

SAMPLE_DELIVERIES_SUMMARY = [
    {
        "delivery_id": "del-1",
        "status": "COMPLETED",
        "delivery_time": {
            "start": "2026-04-04T10:00:00+00:00",
            "end": "2026-04-04T10:30:00+00:00",
        },
    },
]

SAMPLE_DELIVERY_DETAIL = {
    "delivery_id": "del-1",
    "status": "COMPLETED",
    "delivery_time": {
        "start": "2026-04-04T10:00:00+00:00",
        "end": "2026-04-04T10:30:00+00:00",
    },
    "orders": [
        {
            "items": [
                {
                    "id": "order-line-1",
                    "items": [
                        {
                            "id": "s100",
                            "name": "Ja! Vollmilch 1 L",
                            "image_id": "img-100",
                            "unit_quantity": "1 L",
                            "price": 99,
                        }
                    ],
                    "decorators": [{"quantity": 2}],
                },
                {
                    "id": "order-line-2",
                    "items": [
                        {
                            "id": "s200",
                            "name": "Barilla Spaghetti Nr. 5 500 g",
                            "image_id": "img-200",
                            "unit_quantity": "500 g",
                            "price": 149,
                        }
                    ],
                    "decorators": [{"quantity": 1}],
                },
            ]
        }
    ],
}

SAMPLE_SEARCH_MILK = [
    {
        "type": "CATEGORY",
        "items": [
            {
                "id": "s100",
                "name": "Ja! Vollmilch 1 L",
                "display_price": 99,
                "image_id": "img-100",
                "unit_quantity": "1 L",
            },
            {
                "id": "s101",
                "name": "Weihenstephan Vollmilch 3,5% 1 L",
                "display_price": 139,
                "image_id": "img-101",
                "unit_quantity": "1 L",
            },
        ],
    },
]

SAMPLE_USER = {
    "user_id": "u-1",
    "firstname": "Test",
    "lastname": "User",
    "contact_email": "test@example.com",
}

SAMPLE_CART_EMPTY = {"items": [], "total_price": 0}
```

- [ ] **Step 3: Create FakePicnicClient for tests**

Create `recipe-assistant/backend/tests/fixtures/picnic/fake_client.py`:

```python
from __future__ import annotations

from typing import Any

from tests.fixtures.picnic.sample_deliveries import (
    SAMPLE_CART_EMPTY,
    SAMPLE_DELIVERIES_SUMMARY,
    SAMPLE_DELIVERY_DETAIL,
    SAMPLE_SEARCH_MILK,
    SAMPLE_USER,
)


class FakePicnicClient:
    """In-memory fake that satisfies PicnicClientProtocol."""

    def __init__(self) -> None:
        self.deliveries_summary = list(SAMPLE_DELIVERIES_SUMMARY)
        self.delivery_details = {"del-1": SAMPLE_DELIVERY_DETAIL}
        self.search_results: dict[str, list[dict[str, Any]]] = {
            "milch": SAMPLE_SEARCH_MILK,
        }
        self.cart: dict[str, Any] = dict(SAMPLE_CART_EMPTY)
        self.user = dict(SAMPLE_USER)
        self.added_products: list[tuple[str, int]] = []
        self.raise_on_add: dict[str, str] = {}  # picnic_id -> reason

    async def search(self, query: str) -> list[dict[str, Any]]:
        return self.search_results.get(query.lower(), [])

    async def get_deliveries(self, summary: bool = True) -> list[dict[str, Any]]:
        return self.deliveries_summary

    async def get_delivery(self, delivery_id: str) -> dict[str, Any]:
        return self.delivery_details[delivery_id]

    async def get_cart(self) -> dict[str, Any]:
        return self.cart

    async def add_product(self, picnic_id: str, count: int = 1) -> dict[str, Any]:
        if picnic_id in self.raise_on_add:
            raise RuntimeError(self.raise_on_add[picnic_id])
        self.added_products.append((picnic_id, count))
        return {"ok": True}

    async def get_user(self) -> dict[str, Any]:
        return self.user
```

- [ ] **Step 4: Smoke-test the fake**

```bash
cd recipe-assistant/backend && python -c "
import asyncio
from tests.fixtures.picnic.fake_client import FakePicnicClient

async def main():
    c = FakePicnicClient()
    print(await c.get_deliveries())
    print(await c.get_delivery('del-1'))
    await c.add_product('s100', count=2)
    print(c.added_products)

asyncio.run(main())
"
```

Expected: prints summary list, detail dict, and `[('s100', 2)]`.

- [ ] **Step 5: Commit**

```bash
git add recipe-assistant/backend/app/services/picnic/client.py recipe-assistant/backend/tests/fixtures/
git commit -m "feat(picnic): add API client wrapper and test fake"
```

---

## Task 7: Import Flow — Fetch Candidates

**Files:**
- Create: `recipe-assistant/backend/app/services/picnic/import_flow.py`
- Create: `recipe-assistant/backend/tests/services/picnic/test_import_flow.py`

- [ ] **Step 1: Write failing tests for `fetch_import_candidates`**

Create `recipe-assistant/backend/tests/services/picnic/test_import_flow.py`:

```python
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models.inventory import InventoryItem
from app.models.picnic import (
    EanPicnicMap,
    PicnicDeliveryImport,
    PicnicProduct,
    ShoppingListItem,
)
from app.services.picnic.import_flow import (
    fetch_import_candidates,
    commit_import_decisions,
)
from app.schemas.picnic import ImportDecision
from tests.fixtures.picnic.fake_client import FakePicnicClient

TEST_DB = "sqlite+aiosqlite:///./test_import_flow.db"


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(TEST_DB, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        yield s
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def fake_client() -> FakePicnicClient:
    return FakePicnicClient()


@pytest.mark.asyncio
async def test_fetch_returns_candidates_with_match_suggestions(session, fake_client):
    # Pre-existing inventory with a Vollmilch that should fuzzy-match "Ja! Vollmilch 1L"
    session.add(
        InventoryItem(barcode="4014400900057", name="Vollmilch 3,5%", quantity=1, category="Milch")
    )
    await session.commit()

    response = await fetch_import_candidates(session, fake_client)

    assert len(response.deliveries) == 1
    delivery = response.deliveries[0]
    assert delivery.delivery_id == "del-1"
    assert len(delivery.items) == 2
    milk_item = next(i for i in delivery.items if i.picnic_id == "s100")
    assert milk_item.ordered_quantity == 2
    assert milk_item.best_confidence >= 92
    top = milk_item.match_suggestions[0]
    assert top.inventory_barcode == "4014400900057"


@pytest.mark.asyncio
async def test_fetch_skips_already_imported_deliveries(session, fake_client):
    session.add(PicnicDeliveryImport(delivery_id="del-1", item_count=2))
    await session.commit()

    response = await fetch_import_candidates(session, fake_client)
    assert response.deliveries == []


@pytest.mark.asyncio
async def test_fetch_uses_known_mapping_for_confidence_1(session, fake_client):
    # User previously mapped EAN 999 to picnic_id s100
    session.add(PicnicProduct(picnic_id="s100", name="Ja! Vollmilch 1 L"))
    session.add(InventoryItem(barcode="999", name="Milk (ancient mislabel)", quantity=1, category="x"))
    await session.flush()
    session.add(EanPicnicMap(ean="999", picnic_id="s100", source="scan"))
    await session.commit()

    response = await fetch_import_candidates(session, fake_client)
    milk_item = next(i for i in response.deliveries[0].items if i.picnic_id == "s100")
    assert milk_item.best_confidence == 100.0
    assert milk_item.match_suggestions[0].inventory_barcode == "999"
    assert "known mapping" in milk_item.match_suggestions[0].reason


@pytest.mark.asyncio
async def test_commit_match_existing_increments_quantity(session, fake_client):
    session.add(InventoryItem(barcode="4014400900057", name="Vollmilch 3,5%", quantity=3, category="Milch"))
    session.add(PicnicProduct(picnic_id="s100", name="Ja! Vollmilch 1 L"))
    session.add(PicnicProduct(picnic_id="s200", name="Barilla Spaghetti"))
    await session.commit()

    result = await commit_import_decisions(
        session,
        fake_client,
        delivery_id="del-1",
        decisions=[
            ImportDecision(
                picnic_id="s100",
                action="match_existing",
                target_barcode="4014400900057",
            ),
            ImportDecision(picnic_id="s200", action="skip"),
        ],
    )
    await session.commit()

    from sqlalchemy import select
    row = (await session.execute(
        select(InventoryItem).where(InventoryItem.barcode == "4014400900057")
    )).scalar_one()
    assert row.quantity == 5  # was 3, delivery had 2

    mapping = (await session.execute(
        select(EanPicnicMap).where(EanPicnicMap.ean == "4014400900057")
    )).scalar_one()
    assert mapping.picnic_id == "s100"
    assert mapping.source == "user_confirmed"

    # Dedup record written
    imp = (await session.execute(
        select(PicnicDeliveryImport).where(PicnicDeliveryImport.delivery_id == "del-1")
    )).scalar_one()
    assert imp.item_count == 2  # both decisions counted (match + skip)

    assert result.imported == 1
    assert result.skipped == 1


@pytest.mark.asyncio
async def test_commit_create_new_with_synthetic_barcode(session, fake_client):
    session.add(PicnicProduct(picnic_id="s100", name="Ja! Vollmilch 1 L"))
    session.add(PicnicProduct(picnic_id="s200", name="Barilla Spaghetti"))
    await session.commit()

    await commit_import_decisions(
        session,
        fake_client,
        delivery_id="del-1",
        decisions=[
            ImportDecision(
                picnic_id="s100",
                action="create_new",
                storage_location="Küche",
            ),
            ImportDecision(picnic_id="s200", action="skip"),
        ],
    )
    await session.commit()

    from sqlalchemy import select
    row = (await session.execute(
        select(InventoryItem).where(InventoryItem.barcode == "picnic:s100")
    )).scalar_one()
    assert row.name == "Ja! Vollmilch 1 L"
    assert row.quantity == 2


@pytest.mark.asyncio
async def test_commit_scanned_ean_during_create_promotes(session, fake_client):
    session.add(PicnicProduct(picnic_id="s100", name="Ja! Vollmilch 1 L"))
    session.add(PicnicProduct(picnic_id="s200", name="Barilla Spaghetti"))
    await session.commit()

    await commit_import_decisions(
        session,
        fake_client,
        delivery_id="del-1",
        decisions=[
            ImportDecision(
                picnic_id="s100",
                action="create_new",
                scanned_ean="4014400900057",
                storage_location="Küche",
            ),
            ImportDecision(picnic_id="s200", action="skip"),
        ],
    )
    await session.commit()

    from sqlalchemy import select
    row = (await session.execute(
        select(InventoryItem).where(InventoryItem.barcode == "4014400900057")
    )).scalar_one()
    assert row.quantity == 2

    mapping = (await session.execute(
        select(EanPicnicMap).where(EanPicnicMap.ean == "4014400900057")
    )).scalar_one()
    assert mapping.source == "scan"


@pytest.mark.asyncio
async def test_commit_idempotent_on_already_imported_delivery(session, fake_client):
    session.add(PicnicDeliveryImport(delivery_id="del-1", item_count=2))
    await session.commit()

    with pytest.raises(ValueError, match="already imported"):
        await commit_import_decisions(
            session,
            fake_client,
            delivery_id="del-1",
            decisions=[],
        )
```

- [ ] **Step 2: Run to verify failure**

```bash
cd recipe-assistant/backend && pytest tests/services/picnic/test_import_flow.py -v
```

Expected: ImportError for `app.services.picnic.import_flow`.

- [ ] **Step 3: Implement `import_flow.py`**

Create `recipe-assistant/backend/app/services/picnic/import_flow.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory import InventoryItem
from app.models.picnic import (
    EanPicnicMap,
    PicnicDeliveryImport,
    PicnicProduct,
    ShoppingListItem,  # noqa: F401
)
from app.schemas.picnic import (
    ImportCandidate,
    ImportCommitResponse,
    ImportDecision,
    ImportDelivery,
    ImportFetchResponse,
    MatchSuggestion,
)
from app.services.picnic.catalog import PicnicProductData, upsert_product
from app.services.picnic.client import PicnicClientProtocol
from app.services.picnic.matching import (
    MatchCandidate,
    compute_match_suggestions,
)


def _flatten_delivery_items(detail: dict[str, Any]) -> list[dict[str, Any]]:
    """python-picnic-api2 delivery detail is nested: orders[].items[].items[].
    
    Flatten to a list of line items with {picnic_id, name, unit_quantity, image_id, quantity}.
    """
    out: list[dict[str, Any]] = []
    for order in detail.get("orders", []):
        for line in order.get("items", []):
            inner = line.get("items", [])
            if not inner:
                continue
            product = inner[0]
            qty = 1
            for deco in line.get("decorators", []):
                if "quantity" in deco:
                    qty = deco["quantity"]
                    break
            out.append(
                {
                    "picnic_id": product["id"],
                    "name": product.get("name", ""),
                    "unit_quantity": product.get("unit_quantity"),
                    "image_id": product.get("image_id"),
                    "price_cents": product.get("price"),
                    "quantity": qty,
                }
            )
    return out


def _parse_delivery_time(detail: dict[str, Any]) -> datetime | None:
    dt = detail.get("delivery_time", {})
    start = dt.get("start")
    if not start:
        return None
    try:
        return datetime.fromisoformat(start)
    except ValueError:
        return None


async def _already_imported(session: AsyncSession, delivery_id: str) -> bool:
    result = await session.execute(
        select(PicnicDeliveryImport).where(PicnicDeliveryImport.delivery_id == delivery_id)
    )
    return result.scalar_one_or_none() is not None


async def _load_inventory_match_candidates(session: AsyncSession) -> list[MatchCandidate]:
    result = await session.execute(select(InventoryItem))
    return [MatchCandidate(barcode=it.barcode, name=it.name) for it in result.scalars().all()]


async def _suggestions_for_item(
    session: AsyncSession,
    picnic_id: str,
    picnic_name: str,
    picnic_unit_quantity: str | None,
    candidates: list[MatchCandidate],
) -> list[MatchSuggestion]:
    # First: exact match via ean_picnic_map
    mapped = await session.execute(
        select(EanPicnicMap).where(EanPicnicMap.picnic_id == picnic_id)
    )
    existing_map = mapped.scalar_one_or_none()
    if existing_map:
        inv = await session.execute(
            select(InventoryItem).where(InventoryItem.barcode == existing_map.ean)
        )
        inv_row = inv.scalar_one_or_none()
        if inv_row:
            return [
                MatchSuggestion(
                    inventory_barcode=inv_row.barcode,
                    inventory_name=inv_row.name,
                    score=100.0,
                    reason="known mapping",
                )
            ]

    fuzz_results = compute_match_suggestions(picnic_name, picnic_unit_quantity, candidates)
    return [
        MatchSuggestion(
            inventory_barcode=r.inventory_barcode,
            inventory_name=r.inventory_name,
            score=r.score,
            reason=r.reason,
        )
        for r in fuzz_results
    ]


async def fetch_import_candidates(
    session: AsyncSession,
    client: PicnicClientProtocol,
) -> ImportFetchResponse:
    """Fetch delivered-but-not-yet-imported Picnic orders with match suggestions."""
    summary = await client.get_deliveries(summary=True)

    deliveries_out: list[ImportDelivery] = []
    candidates = await _load_inventory_match_candidates(session)

    for delivery_stub in summary:
        delivery_id = delivery_stub.get("delivery_id")
        if not delivery_id:
            continue
        if await _already_imported(session, delivery_id):
            continue

        detail = await client.get_delivery(delivery_id)
        items_flat = _flatten_delivery_items(detail)
        if not items_flat:
            continue

        # Cache picnic products as we go (opportunistic)
        for item in items_flat:
            await upsert_product(
                session,
                PicnicProductData(
                    picnic_id=item["picnic_id"],
                    name=item["name"],
                    brand=None,
                    unit_quantity=item.get("unit_quantity"),
                    image_id=item.get("image_id"),
                    last_price_cents=item.get("price_cents"),
                ),
            )

        import_items: list[ImportCandidate] = []
        for item in items_flat:
            suggestions = await _suggestions_for_item(
                session,
                item["picnic_id"],
                item["name"],
                item.get("unit_quantity"),
                candidates,
            )
            best = suggestions[0].score if suggestions else 0.0
            import_items.append(
                ImportCandidate(
                    picnic_id=item["picnic_id"],
                    picnic_name=item["name"],
                    picnic_image_id=item.get("image_id"),
                    picnic_unit_quantity=item.get("unit_quantity"),
                    ordered_quantity=item["quantity"],
                    match_suggestions=suggestions,
                    best_confidence=best,
                )
            )

        deliveries_out.append(
            ImportDelivery(
                delivery_id=delivery_id,
                delivered_at=_parse_delivery_time(detail),
                items=import_items,
            )
        )

    await session.flush()  # persist catalog upserts
    return ImportFetchResponse(deliveries=deliveries_out)


async def commit_import_decisions(
    session: AsyncSession,
    client: PicnicClientProtocol,
    delivery_id: str,
    decisions: list[ImportDecision],
) -> ImportCommitResponse:
    """Apply user decisions transactionally.

    - match_existing: increment quantity, add mapping (user_confirmed or scan if scanned_ean given)
    - create_new: create InventoryItem with synthetic or scanned barcode, add mapping
    - skip: no-op
    """
    if await _already_imported(session, delivery_id):
        raise ValueError(f"delivery {delivery_id} already imported")

    # Fetch delivery detail fresh to get quantities (we don't trust the client)
    detail = await client.get_delivery(delivery_id)
    flat = {it["picnic_id"]: it for it in _flatten_delivery_items(detail)}

    imported = 0
    created = 0
    skipped = 0
    promoted = 0

    for decision in decisions:
        line = flat.get(decision.picnic_id)
        if line is None:
            skipped += 1
            continue

        qty = line["quantity"]

        if decision.action == "skip":
            skipped += 1
            continue

        if decision.action == "match_existing":
            assert decision.target_barcode, "match_existing requires target_barcode"
            result = await session.execute(
                select(InventoryItem).where(InventoryItem.barcode == decision.target_barcode)
            )
            item = result.scalar_one()
            item.quantity += qty

            source = "scan" if decision.scanned_ean else "user_confirmed"
            await _upsert_mapping(
                session,
                ean=decision.target_barcode,
                picnic_id=decision.picnic_id,
                source=source,
            )
            imported += 1
            continue

        if decision.action == "create_new":
            if decision.scanned_ean:
                # Scanned real EAN — either merge into existing or create with real EAN
                existing = (await session.execute(
                    select(InventoryItem).where(InventoryItem.barcode == decision.scanned_ean)
                )).scalar_one_or_none()

                if existing:
                    existing.quantity += qty
                    # Apply optional fields from decision
                    if decision.storage_location:
                        existing.storage_location_id = await _resolve_location(session, decision.storage_location)
                    if decision.expiration_date:
                        existing.expiration_date = decision.expiration_date
                    promoted += 1
                else:
                    session.add(InventoryItem(
                        barcode=decision.scanned_ean,
                        name=line["name"],
                        quantity=qty,
                        category="Unbekannt",
                        storage_location_id=await _resolve_location(session, decision.storage_location),
                        expiration_date=decision.expiration_date,
                    ))
                    created += 1

                await _upsert_mapping(
                    session,
                    ean=decision.scanned_ean,
                    picnic_id=decision.picnic_id,
                    source="scan",
                )
            else:
                synthetic = f"picnic:{decision.picnic_id}"
                existing_syn = (await session.execute(
                    select(InventoryItem).where(InventoryItem.barcode == synthetic)
                )).scalar_one_or_none()
                if existing_syn:
                    existing_syn.quantity += qty
                else:
                    session.add(InventoryItem(
                        barcode=synthetic,
                        name=line["name"],
                        quantity=qty,
                        category="Unbekannt",
                        storage_location_id=await _resolve_location(session, decision.storage_location),
                        expiration_date=decision.expiration_date,
                    ))
                    created += 1
            continue

    session.add(
        PicnicDeliveryImport(delivery_id=delivery_id, item_count=len(decisions))
    )
    await session.flush()

    return ImportCommitResponse(
        imported=imported,
        created=created,
        skipped=skipped,
        promoted=promoted,
    )


async def _resolve_location(session: AsyncSession, name: str | None) -> int | None:
    """Resolve storage location name → id, creating the location if missing."""
    if not name:
        return None
    from app.models.inventory import StorageLocation
    result = await session.execute(select(StorageLocation).where(StorageLocation.name == name))
    loc = result.scalar_one_or_none()
    if loc:
        return loc.id
    new_loc = StorageLocation(name=name)
    session.add(new_loc)
    await session.flush()
    return new_loc.id


async def _upsert_mapping(session: AsyncSession, ean: str, picnic_id: str, source: str) -> None:
    """Insert an ean_picnic_map row; if the (ean, picnic_id) pair already exists,
    update the source only if the new source is stronger (scan > user_confirmed > auto)."""
    strength = {"auto": 1, "user_confirmed": 2, "scan": 3}
    result = await session.execute(
        select(EanPicnicMap).where(
            EanPicnicMap.ean == ean, EanPicnicMap.picnic_id == picnic_id
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        if strength.get(source, 0) > strength.get(existing.source, 0):
            existing.source = source
        return
    session.add(EanPicnicMap(ean=ean, picnic_id=picnic_id, source=source))
```

- [ ] **Step 4: Run tests**

```bash
cd recipe-assistant/backend && pytest tests/services/picnic/test_import_flow.py -v
```

Expected: all tests PASS. If quantity assertions fail, check the `_flatten_delivery_items` nesting and adjust.

- [ ] **Step 5: Commit**

```bash
git add recipe-assistant/backend/app/services/picnic/import_flow.py recipe-assistant/backend/tests/services/picnic/test_import_flow.py
git commit -m "feat(picnic): add import flow (fetch + commit)"
```

---

## Task 8: Shopping List + Cart Sync Service

**Files:**
- Create: `recipe-assistant/backend/app/services/picnic/cart.py`
- Create: `recipe-assistant/backend/tests/services/picnic/test_cart.py`

- [ ] **Step 1: Write failing tests**

Create `recipe-assistant/backend/tests/services/picnic/test_cart.py`:

```python
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models.picnic import EanPicnicMap, PicnicProduct, ShoppingListItem
from app.services.picnic.cart import (
    resolve_shopping_list_status,
    sync_shopping_list_to_cart,
)
from tests.fixtures.picnic.fake_client import FakePicnicClient

TEST_DB = "sqlite+aiosqlite:///./test_cart.db"


@pytest_asyncio.fixture
async def session():
    engine = create_async_engine(TEST_DB, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with Session() as s:
        yield s
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.mark.asyncio
async def test_resolve_status_mapped_via_direct_picnic_id(session):
    session.add(PicnicProduct(picnic_id="s100", name="Milk"))
    session.add(ShoppingListItem(name="Milch", quantity=1, picnic_id="s100"))
    await session.commit()

    items = await resolve_shopping_list_status(session)
    assert items[0].picnic_status == "mapped"


@pytest.mark.asyncio
async def test_resolve_status_mapped_via_ean_map(session):
    session.add(PicnicProduct(picnic_id="s100", name="Milk"))
    await session.flush()
    session.add(EanPicnicMap(ean="4014400900057", picnic_id="s100", source="scan"))
    session.add(ShoppingListItem(name="Milch", quantity=1, inventory_barcode="4014400900057"))
    await session.commit()

    items = await resolve_shopping_list_status(session)
    assert items[0].picnic_status == "mapped"
    assert items[0].picnic_id == "s100"


@pytest.mark.asyncio
async def test_resolve_status_unmapped(session):
    session.add(ShoppingListItem(name="Exotisches", quantity=1, inventory_barcode="9999999999999"))
    await session.commit()

    items = await resolve_shopping_list_status(session)
    assert items[0].picnic_status == "unmapped"


@pytest.mark.asyncio
async def test_sync_adds_mapped_items_to_cart(session):
    client = FakePicnicClient()
    session.add(PicnicProduct(picnic_id="s100", name="Milk"))
    session.add(ShoppingListItem(name="Milch", quantity=2, picnic_id="s100"))
    session.add(ShoppingListItem(name="Exotisches", quantity=1))  # unmapped
    await session.commit()

    response = await sync_shopping_list_to_cart(session, client)
    assert response.added_count == 1
    assert response.skipped_count == 1
    assert ("s100", 2) in client.added_products


@pytest.mark.asyncio
async def test_sync_reports_failures_per_item(session):
    client = FakePicnicClient()
    client.raise_on_add = {"s200": "product_unavailable"}
    session.add(PicnicProduct(picnic_id="s100", name="Milk"))
    session.add(PicnicProduct(picnic_id="s200", name="Pasta"))
    session.add(ShoppingListItem(name="Milch", quantity=1, picnic_id="s100"))
    session.add(ShoppingListItem(name="Nudeln", quantity=1, picnic_id="s200"))
    await session.commit()

    response = await sync_shopping_list_to_cart(session, client)
    assert response.added_count == 1
    assert response.failed_count == 1
    failed = next(r for r in response.results if r.status == "failed")
    assert failed.picnic_id == "s200"
    assert "unavailable" in (failed.failure_reason or "").lower()
```

- [ ] **Step 2: Run to confirm failure**

```bash
cd recipe-assistant/backend && pytest tests/services/picnic/test_cart.py -v
```

Expected: ImportError.

- [ ] **Step 3: Implement `cart.py`**

Create `recipe-assistant/backend/app/services/picnic/cart.py`:

```python
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.picnic import EanPicnicMap, ShoppingListItem
from app.schemas.picnic import (
    CartSyncItemResult,
    CartSyncResponse,
    ShoppingListItemResponse,
)
from app.services.picnic.client import PicnicClientProtocol


async def _resolve_picnic_id(session: AsyncSession, item: ShoppingListItem) -> str | None:
    """Determine which picnic_id applies to a shopping list row."""
    if item.picnic_id:
        return item.picnic_id
    if item.inventory_barcode:
        result = await session.execute(
            select(EanPicnicMap)
            .where(EanPicnicMap.ean == item.inventory_barcode)
            .order_by(EanPicnicMap.created_at.desc())
        )
        row = result.scalars().first()
        if row:
            return row.picnic_id
    return None


async def resolve_shopping_list_status(session: AsyncSession) -> list[ShoppingListItemResponse]:
    """Return all shopping list items with their Picnic resolution status."""
    result = await session.execute(select(ShoppingListItem).order_by(ShoppingListItem.added_at))
    items = result.scalars().all()

    out: list[ShoppingListItemResponse] = []
    for item in items:
        resolved = await _resolve_picnic_id(session, item)
        status: str
        if resolved:
            status = "mapped"
        else:
            status = "unmapped"
        out.append(
            ShoppingListItemResponse(
                id=item.id,
                inventory_barcode=item.inventory_barcode,
                picnic_id=resolved,
                name=item.name,
                quantity=item.quantity,
                picnic_status=status,  # type: ignore[arg-type]
                added_at=item.added_at,
            )
        )
    return out


async def sync_shopping_list_to_cart(
    session: AsyncSession,
    client: PicnicClientProtocol,
) -> CartSyncResponse:
    """Push every mapped shopping list item into the real Picnic cart.
    
    Per-item tracking; does NOT roll back on partial failure. Items that succeed
    stay in the Picnic cart; items that failed are reported.
    """
    result = await session.execute(select(ShoppingListItem))
    items = result.scalars().all()

    results: list[CartSyncItemResult] = []
    added_count = 0
    failed_count = 0
    skipped_count = 0

    for item in items:
        picnic_id = await _resolve_picnic_id(session, item)
        if not picnic_id:
            results.append(
                CartSyncItemResult(
                    shopping_list_id=item.id,
                    picnic_id=None,
                    status="skipped_unmapped",
                    failure_reason=None,
                )
            )
            skipped_count += 1
            continue

        try:
            await client.add_product(picnic_id, count=item.quantity)
            results.append(
                CartSyncItemResult(
                    shopping_list_id=item.id,
                    picnic_id=picnic_id,
                    status="added",
                    failure_reason=None,
                )
            )
            added_count += 1
        except Exception as e:
            reason = str(e) or "http_error"
            if "unavailable" in reason.lower():
                reason = "product_unavailable"
            results.append(
                CartSyncItemResult(
                    shopping_list_id=item.id,
                    picnic_id=picnic_id,
                    status="failed",
                    failure_reason=reason,
                )
            )
            failed_count += 1

    return CartSyncResponse(
        results=results,
        added_count=added_count,
        failed_count=failed_count,
        skipped_count=skipped_count,
    )
```

- [ ] **Step 4: Run tests**

```bash
cd recipe-assistant/backend && pytest tests/services/picnic/test_cart.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add recipe-assistant/backend/app/services/picnic/cart.py recipe-assistant/backend/tests/services/picnic/test_cart.py
git commit -m "feat(picnic): add shopping list resolution and cart sync"
```

---

## Task 9: FastAPI Router — `/api/picnic/*`

**Files:**
- Create: `recipe-assistant/backend/app/routers/picnic.py`
- Modify: `recipe-assistant/backend/app/main.py`
- Create: `recipe-assistant/backend/tests/test_picnic_router.py`

- [ ] **Step 1: Create router file**

Create `recipe-assistant/backend/app/routers/picnic.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models.picnic import EanPicnicMap, ShoppingListItem
from app.schemas.picnic import (
    CartSyncResponse,
    EanPicnicMapResponse,
    ImportCommitRequest,
    ImportCommitResponse,
    ImportFetchResponse,
    PicnicSearchResponse,
    PicnicSearchResult,
    PicnicStatusResponse,
    ShoppingListAddRequest,
    ShoppingListItemResponse,
    ShoppingListUpdateRequest,
)
from app.services.picnic.cart import resolve_shopping_list_status, sync_shopping_list_to_cart
from app.services.picnic.catalog import PicnicProductData, upsert_product
from app.services.picnic.client import (
    PicnicClientProtocol,
    PicnicNotConfigured,
    get_picnic_client,
)
from app.services.picnic.import_flow import (
    commit_import_decisions,
    fetch_import_candidates,
)

router = APIRouter()


def _feature_enabled() -> bool:
    s = get_settings()
    return bool(s.picnic_email and s.picnic_password)


def _require_enabled():
    if not _feature_enabled():
        raise HTTPException(
            status_code=503,
            detail={"error": "picnic_not_configured"},
        )


@router.get("/status", response_model=PicnicStatusResponse)
async def status(client: PicnicClientProtocol = Depends(get_picnic_client)):
    if not _feature_enabled():
        return PicnicStatusResponse(enabled=False, account=None)
    try:
        user = await client.get_user()
        return PicnicStatusResponse(
            enabled=True,
            account={
                "first_name": user.get("firstname"),
                "last_name": user.get("lastname"),
                "email": user.get("contact_email"),
            },
        )
    except PicnicNotConfigured:
        return PicnicStatusResponse(enabled=False, account=None)
    except Exception as e:
        raise HTTPException(status_code=503, detail={"error": "picnic_auth_failed", "detail": str(e)})


@router.post("/import/fetch", response_model=ImportFetchResponse)
async def import_fetch(
    client: PicnicClientProtocol = Depends(get_picnic_client),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    try:
        response = await fetch_import_candidates(db, client)
        await db.commit()
        return response
    except PicnicNotConfigured:
        raise HTTPException(status_code=503, detail={"error": "picnic_not_configured"})


@router.post("/import/commit", response_model=ImportCommitResponse)
async def import_commit(
    req: ImportCommitRequest,
    client: PicnicClientProtocol = Depends(get_picnic_client),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    try:
        response = await commit_import_decisions(db, client, req.delivery_id, req.decisions)
        await db.commit()
        return response
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/search", response_model=PicnicSearchResponse)
async def search(
    q: str,
    client: PicnicClientProtocol = Depends(get_picnic_client),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    raw = await client.search(q)
    # python-picnic-api2 returns list of groups; flatten items
    results: list[PicnicSearchResult] = []
    for group in raw:
        for item in group.get("items", []):
            pid = item.get("id")
            if not pid:
                continue
            name = item.get("name", "")
            await upsert_product(
                db,
                PicnicProductData(
                    picnic_id=pid,
                    name=name,
                    brand=None,
                    unit_quantity=item.get("unit_quantity"),
                    image_id=item.get("image_id"),
                    last_price_cents=item.get("display_price"),
                ),
            )
            results.append(
                PicnicSearchResult(
                    picnic_id=pid,
                    name=name,
                    brand=None,
                    unit_quantity=item.get("unit_quantity"),
                    image_id=item.get("image_id"),
                    price_cents=item.get("display_price"),
                )
            )
    await db.commit()
    return PicnicSearchResponse(results=results)


@router.get("/shopping-list", response_model=list[ShoppingListItemResponse])
async def get_shopping_list(db: AsyncSession = Depends(get_db)):
    _require_enabled()
    return await resolve_shopping_list_status(db)


@router.post("/shopping-list", response_model=ShoppingListItemResponse, status_code=201)
async def add_shopping_list_item(
    req: ShoppingListAddRequest,
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    item = ShoppingListItem(
        inventory_barcode=req.inventory_barcode,
        picnic_id=req.picnic_id,
        name=req.name,
        quantity=req.quantity,
    )
    db.add(item)
    await db.commit()
    await db.refresh(item)
    items = await resolve_shopping_list_status(db)
    return next(i for i in items if i.id == item.id)


@router.patch("/shopping-list/{item_id}", response_model=ShoppingListItemResponse)
async def update_shopping_list_item(
    item_id: int,
    req: ShoppingListUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    result = await db.execute(select(ShoppingListItem).where(ShoppingListItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="not found")
    if req.quantity is not None:
        item.quantity = req.quantity
    if req.picnic_id is not None:
        item.picnic_id = req.picnic_id
    await db.commit()
    items = await resolve_shopping_list_status(db)
    return next(i for i in items if i.id == item_id)


@router.delete("/shopping-list/{item_id}")
async def delete_shopping_list_item(item_id: int, db: AsyncSession = Depends(get_db)):
    _require_enabled()
    result = await db.execute(select(ShoppingListItem).where(ShoppingListItem.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="not found")
    await db.delete(item)
    await db.commit()
    return {"message": "deleted"}


@router.post("/shopping-list/sync", response_model=CartSyncResponse)
async def sync_cart(
    client: PicnicClientProtocol = Depends(get_picnic_client),
    db: AsyncSession = Depends(get_db),
):
    _require_enabled()
    return await sync_shopping_list_to_cart(db, client)


@router.get("/mappings", response_model=list[EanPicnicMapResponse])
async def list_mappings(db: AsyncSession = Depends(get_db)):
    _require_enabled()
    result = await db.execute(select(EanPicnicMap).order_by(EanPicnicMap.created_at.desc()))
    return result.scalars().all()


@router.delete("/mappings/{mapping_id}")
async def delete_mapping(mapping_id: int, db: AsyncSession = Depends(get_db)):
    _require_enabled()
    result = await db.execute(select(EanPicnicMap).where(EanPicnicMap.id == mapping_id))
    mapping = result.scalar_one_or_none()
    if not mapping:
        raise HTTPException(status_code=404, detail="not found")
    await db.delete(mapping)
    await db.commit()
    return {"message": "deleted"}
```

- [ ] **Step 2: Register router in `main.py`**

Edit `recipe-assistant/backend/app/main.py`:

Find line:
```python
from app.routers import inventory, storage, assistant, persons
```
Replace with:
```python
from app.routers import inventory, storage, assistant, persons, picnic
```

Find line:
```python
app.include_router(persons.router, prefix="/api/persons", tags=["persons"])
```
Add after it:
```python
app.include_router(picnic.router, prefix="/api/picnic", tags=["picnic"])
```

- [ ] **Step 3: Write failing integration tests**

Create `recipe-assistant/backend/tests/test_picnic_router.py`:

```python
import pytest
from httpx import AsyncClient

from app.services.picnic.client import get_picnic_client
from app.main import app
from tests.fixtures.picnic.fake_client import FakePicnicClient


@pytest.fixture(autouse=True)
def override_picnic_client(monkeypatch):
    fake = FakePicnicClient()
    app.dependency_overrides[get_picnic_client] = lambda: fake
    # Enable feature flag
    monkeypatch.setenv("PICNIC_EMAIL", "test@example.com")
    monkeypatch.setenv("PICNIC_PASSWORD", "secret")
    # Clear settings cache
    from app.config import get_settings
    get_settings.cache_clear()
    yield fake
    app.dependency_overrides.pop(get_picnic_client, None)
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_status_enabled(client: AsyncClient):
    response = await client.get("/api/picnic/status")
    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["account"]["email"] == "test@example.com"


@pytest.mark.asyncio
async def test_import_fetch_returns_candidates(client: AsyncClient):
    response = await client.post("/api/picnic/import/fetch")
    assert response.status_code == 200
    data = response.json()
    assert len(data["deliveries"]) == 1


@pytest.mark.asyncio
async def test_import_commit_then_refetch_is_empty(client: AsyncClient):
    fetch = await client.post("/api/picnic/import/fetch")
    delivery = fetch.json()["deliveries"][0]
    decisions = [
        {
            "picnic_id": item["picnic_id"],
            "action": "create_new",
            "storage_location": "Küche",
        }
        for item in delivery["items"]
    ]
    commit = await client.post(
        "/api/picnic/import/commit",
        json={"delivery_id": delivery["delivery_id"], "decisions": decisions},
    )
    assert commit.status_code == 200
    assert commit.json()["created"] == 2

    # Dedup: second fetch should return empty
    refetch = await client.post("/api/picnic/import/fetch")
    assert refetch.json()["deliveries"] == []


@pytest.mark.asyncio
async def test_shopping_list_crud_and_sync(client: AsyncClient, override_picnic_client):
    add = await client.post(
        "/api/picnic/shopping-list",
        json={"name": "Milch", "quantity": 2, "picnic_id": "s100"},
    )
    assert add.status_code == 201
    item_id = add.json()["id"]
    assert add.json()["picnic_status"] == "mapped"

    listing = await client.get("/api/picnic/shopping-list")
    assert len(listing.json()) == 1

    sync = await client.post("/api/picnic/shopping-list/sync")
    assert sync.status_code == 200
    assert sync.json()["added_count"] == 1
    assert ("s100", 2) in override_picnic_client.added_products

    delete = await client.delete(f"/api/picnic/shopping-list/{item_id}")
    assert delete.status_code == 200
```

- [ ] **Step 4: Run tests**

```bash
cd recipe-assistant/backend && pytest tests/test_picnic_router.py -v
```

Expected: all tests PASS. If failures around settings caching happen, check the `override_picnic_client` fixture correctly clears `get_settings.cache_clear()` before the test runs.

- [ ] **Step 5: Run full backend test suite to confirm no regressions**

```bash
cd recipe-assistant/backend && pytest -v
```

Expected: all tests (old + new) pass.

- [ ] **Step 6: Commit**

```bash
git add recipe-assistant/backend/app/routers/picnic.py recipe-assistant/backend/app/main.py recipe-assistant/backend/tests/test_picnic_router.py
git commit -m "feat(picnic): add /api/picnic router with full endpoint coverage"
```

---

## Task 10: Frontend — Types & API Client

**Files:**
- Modify: `recipe-assistant/frontend/src/types/index.ts`
- Modify: `recipe-assistant/frontend/src/api/client.ts`

- [ ] **Step 1: Add Picnic types**

Append to `recipe-assistant/frontend/src/types/index.ts`:

```typescript
// --- Picnic ---

export interface PicnicStatus {
  enabled: boolean;
  account: { first_name: string; last_name: string; email: string } | null;
}

export interface MatchSuggestion {
  inventory_barcode: string;
  inventory_name: string;
  score: number;
  reason: string;
}

export interface ImportCandidate {
  picnic_id: string;
  picnic_name: string;
  picnic_image_id: string | null;
  picnic_unit_quantity: string | null;
  ordered_quantity: number;
  match_suggestions: MatchSuggestion[];
  best_confidence: number;
}

export interface ImportDelivery {
  delivery_id: string;
  delivered_at: string | null;
  items: ImportCandidate[];
}

export interface ImportFetchResponse {
  deliveries: ImportDelivery[];
}

export type ImportAction = "match_existing" | "create_new" | "skip";

export interface ImportDecision {
  picnic_id: string;
  action: ImportAction;
  target_barcode?: string | null;
  scanned_ean?: string | null;
  storage_location?: string | null;
  expiration_date?: string | null;
}

export interface ImportCommitResponse {
  imported: number;
  created: number;
  skipped: number;
  promoted: number;
}

export interface ShoppingListItem {
  id: number;
  inventory_barcode: string | null;
  picnic_id: string | null;
  name: string;
  quantity: number;
  picnic_status: "mapped" | "unmapped" | "missing";
  added_at: string;
}

export interface PicnicSearchResult {
  picnic_id: string;
  name: string;
  brand: string | null;
  unit_quantity: string | null;
  image_id: string | null;
  price_cents: number | null;
}

export interface CartSyncItemResult {
  shopping_list_id: number;
  picnic_id: string | null;
  status: "added" | "skipped_unmapped" | "failed";
  failure_reason: string | null;
}

export interface CartSyncResponse {
  results: CartSyncItemResult[];
  added_count: number;
  failed_count: number;
  skipped_count: number;
}
```

- [ ] **Step 2: Add API client methods**

Append to `recipe-assistant/frontend/src/api/client.ts`:

```typescript
import type {
  PicnicStatus,
  ImportFetchResponse,
  ImportDecision,
  ImportCommitResponse,
  ShoppingListItem as PicnicShoppingListItem,
  PicnicSearchResult,
  CartSyncResponse,
} from "../types";

// Picnic
export const getPicnicStatus = () =>
  request<PicnicStatus>("/picnic/status");

export const fetchPicnicImport = () =>
  request<ImportFetchResponse>("/picnic/import/fetch", { method: "POST" });

export const commitPicnicImport = (delivery_id: string, decisions: ImportDecision[]) =>
  request<ImportCommitResponse>("/picnic/import/commit", {
    method: "POST",
    body: JSON.stringify({ delivery_id, decisions }),
  });

export const searchPicnic = (q: string) =>
  request<{ results: PicnicSearchResult[] }>(`/picnic/search?q=${encodeURIComponent(q)}`);

export const getShoppingList = () =>
  request<PicnicShoppingListItem[]>("/picnic/shopping-list");

export const addShoppingListItem = (data: {
  inventory_barcode?: string;
  picnic_id?: string;
  name: string;
  quantity: number;
}) =>
  request<PicnicShoppingListItem>("/picnic/shopping-list", {
    method: "POST",
    body: JSON.stringify(data),
  });

export const updateShoppingListItem = (id: number, data: { quantity?: number; picnic_id?: string }) =>
  request<PicnicShoppingListItem>(`/picnic/shopping-list/${id}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });

export const deleteShoppingListItem = (id: number) =>
  request<{ message: string }>(`/picnic/shopping-list/${id}`, { method: "DELETE" });

export const syncShoppingListToCart = () =>
  request<CartSyncResponse>("/picnic/shopping-list/sync", { method: "POST" });
```

Note: the `import type` statement goes at the top of the file alongside the existing one; merge into the existing `import type { ... } from "../types";` block if it makes sense rather than duplicating.

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd recipe-assistant/frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add recipe-assistant/frontend/src/types/index.ts recipe-assistant/frontend/src/api/client.ts
git commit -m "feat(picnic): add frontend types and API client methods"
```

---

## Task 11: Frontend — usePicnic Hook

**Files:**
- Create: `recipe-assistant/frontend/src/hooks/usePicnic.ts`

- [ ] **Step 1: Create hook**

Create `recipe-assistant/frontend/src/hooks/usePicnic.ts`:

```typescript
import { useCallback, useEffect, useState } from "react";
import {
  getPicnicStatus,
  fetchPicnicImport,
  commitPicnicImport,
  getShoppingList,
  addShoppingListItem,
  updateShoppingListItem,
  deleteShoppingListItem,
  syncShoppingListToCart,
  searchPicnic,
} from "../api/client";
import type {
  PicnicStatus,
  ImportFetchResponse,
  ImportDecision,
  ShoppingListItem,
  PicnicSearchResult,
  CartSyncResponse,
} from "../types";

export function usePicnicStatus() {
  const [status, setStatus] = useState<PicnicStatus | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getPicnicStatus()
      .then(setStatus)
      .catch(() => setStatus({ enabled: false, account: null }))
      .finally(() => setLoading(false));
  }, []);

  return { status, loading };
}

export function usePicnicImport() {
  const [data, setData] = useState<ImportFetchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchImport = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetchPicnicImport();
      setData(response);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fehler");
    } finally {
      setLoading(false);
    }
  }, []);

  const commit = useCallback(
    async (delivery_id: string, decisions: ImportDecision[]) => {
      return commitPicnicImport(delivery_id, decisions);
    },
    []
  );

  return { data, loading, error, fetchImport, commit };
}

export function useShoppingList() {
  const [items, setItems] = useState<ShoppingListItem[]>([]);
  const [loading, setLoading] = useState(false);

  const refetch = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await getShoppingList());
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refetch();
  }, [refetch]);

  const add = async (data: Parameters<typeof addShoppingListItem>[0]) => {
    await addShoppingListItem(data);
    await refetch();
  };

  const update = async (id: number, data: Parameters<typeof updateShoppingListItem>[1]) => {
    await updateShoppingListItem(id, data);
    await refetch();
  };

  const remove = async (id: number) => {
    await deleteShoppingListItem(id);
    await refetch();
  };

  const sync = async (): Promise<CartSyncResponse> => {
    const result = await syncShoppingListToCart();
    await refetch();
    return result;
  };

  return { items, loading, refetch, add, update, remove, sync };
}

export function usePicnicSearch() {
  const [results, setResults] = useState<PicnicSearchResult[]>([]);
  const [loading, setLoading] = useState(false);

  const search = useCallback(async (q: string) => {
    if (!q.trim()) {
      setResults([]);
      return;
    }
    setLoading(true);
    try {
      const response = await searchPicnic(q);
      setResults(response.results);
    } finally {
      setLoading(false);
    }
  }, []);

  return { results, loading, search };
}
```

- [ ] **Step 2: Verify compile**

```bash
cd recipe-assistant/frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add recipe-assistant/frontend/src/hooks/usePicnic.ts
git commit -m "feat(picnic): add usePicnic hook family"
```

---

## Task 12: Frontend — Picnic Import Page

**Files:**
- Create: `recipe-assistant/frontend/src/components/picnic/ReviewCard.tsx`
- Create: `recipe-assistant/frontend/src/components/picnic/MatchCandidateList.tsx`
- Create: `recipe-assistant/frontend/src/pages/PicnicImportPage.tsx`

- [ ] **Step 1: Create `MatchCandidateList.tsx`**

```typescript
import type { MatchSuggestion } from "../../types";

interface Props {
  suggestions: MatchSuggestion[];
  selectedBarcode: string | null;
  onSelect: (barcode: string | null) => void;
}

export function MatchCandidateList({ suggestions, selectedBarcode, onSelect }: Props) {
  if (suggestions.length === 0) {
    return <div className="text-sm text-gray-500">Kein Vorschlag</div>;
  }

  return (
    <ul className="space-y-1">
      {suggestions.map((s) => {
        const isSelected = s.inventory_barcode === selectedBarcode;
        const tier =
          s.score >= 92 ? "confident" : s.score >= 75 ? "uncertain" : "weak";
        return (
          <li key={s.inventory_barcode}>
            <button
              type="button"
              onClick={() => onSelect(isSelected ? null : s.inventory_barcode)}
              className={`w-full text-left px-2 py-1 rounded border ${
                isSelected
                  ? "border-blue-500 bg-blue-50"
                  : "border-gray-200 hover:bg-gray-50"
              }`}
            >
              <div className="flex justify-between">
                <span>{s.inventory_name}</span>
                <span
                  className={`text-xs ${
                    tier === "confident"
                      ? "text-green-600"
                      : tier === "uncertain"
                      ? "text-yellow-600"
                      : "text-gray-500"
                  }`}
                >
                  {Math.round(s.score)} — {s.reason}
                </span>
              </div>
            </button>
          </li>
        );
      })}
    </ul>
  );
}
```

- [ ] **Step 2: Create `ReviewCard.tsx`**

```typescript
import { useState } from "react";
import type { ImportCandidate, ImportDecision } from "../../types";
import { MatchCandidateList } from "./MatchCandidateList";

interface Props {
  candidate: ImportCandidate;
  storageLocations: string[];
  onChange: (decision: ImportDecision) => void;
}

export function ReviewCard({ candidate, storageLocations, onChange }: Props) {
  const confident = candidate.best_confidence >= 92;
  const initialAction = confident ? "match_existing" : "skip";
  const initialTarget = confident ? candidate.match_suggestions[0].inventory_barcode : null;

  const [action, setAction] = useState<ImportDecision["action"]>(initialAction);
  const [targetBarcode, setTargetBarcode] = useState<string | null>(initialTarget);
  const [storageLocation, setStorageLocation] = useState<string>(storageLocations[0] ?? "");

  const update = (patch: Partial<ImportDecision>) => {
    const next: ImportDecision = {
      picnic_id: candidate.picnic_id,
      action,
      target_barcode: targetBarcode,
      storage_location: action === "create_new" ? storageLocation : null,
      ...patch,
    };
    onChange(next);
  };

  return (
    <div className="border rounded p-4 space-y-3">
      <div className="flex gap-3">
        {candidate.picnic_image_id && (
          <img
            src={`https://storefront-prod.de.picnicinternational.com/static/images/${candidate.picnic_image_id}/tile-small.png`}
            alt=""
            className="w-16 h-16 object-contain"
          />
        )}
        <div className="flex-1">
          <div className="font-semibold">{candidate.picnic_name}</div>
          <div className="text-sm text-gray-600">
            {candidate.picnic_unit_quantity} × {candidate.ordered_quantity}
          </div>
        </div>
      </div>

      <div className="flex gap-2">
        <button
          type="button"
          onClick={() => { setAction("match_existing"); update({ action: "match_existing" }); }}
          className={`px-3 py-1 rounded ${action === "match_existing" ? "bg-blue-600 text-white" : "bg-gray-100"}`}
        >
          Zuordnen
        </button>
        <button
          type="button"
          onClick={() => { setAction("create_new"); update({ action: "create_new" }); }}
          className={`px-3 py-1 rounded ${action === "create_new" ? "bg-blue-600 text-white" : "bg-gray-100"}`}
        >
          Neu anlegen
        </button>
        <button
          type="button"
          onClick={() => { setAction("skip"); update({ action: "skip" }); }}
          className={`px-3 py-1 rounded ${action === "skip" ? "bg-blue-600 text-white" : "bg-gray-100"}`}
        >
          Überspringen
        </button>
      </div>

      {action === "match_existing" && (
        <MatchCandidateList
          suggestions={candidate.match_suggestions}
          selectedBarcode={targetBarcode}
          onSelect={(b) => { setTargetBarcode(b); update({ target_barcode: b }); }}
        />
      )}

      {action === "create_new" && (
        <div>
          <label className="block text-sm font-medium">Lagerort</label>
          <select
            value={storageLocation}
            onChange={(e) => { setStorageLocation(e.target.value); update({ storage_location: e.target.value }); }}
            className="border rounded px-2 py-1"
          >
            {storageLocations.map((loc) => (
              <option key={loc} value={loc}>{loc}</option>
            ))}
          </select>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Create `PicnicImportPage.tsx`**

```typescript
import { useEffect, useState } from "react";
import { usePicnicImport } from "../hooks/usePicnic";
import { getStorageLocations } from "../api/client";
import type { ImportDecision } from "../types";
import { ReviewCard } from "../components/picnic/ReviewCard";

export default function PicnicImportPage() {
  const { data, loading, error, fetchImport, commit } = usePicnicImport();
  const [decisions, setDecisions] = useState<Record<string, ImportDecision>>({});
  const [storageLocations, setStorageLocations] = useState<string[]>([]);

  useEffect(() => {
    getStorageLocations().then((locs) => setStorageLocations(locs.map((l) => l.name)));
  }, []);

  const handleDecision = (d: ImportDecision) => {
    setDecisions((prev) => ({ ...prev, [d.picnic_id]: d }));
  };

  const handleCommit = async (deliveryId: string) => {
    const delivery = data?.deliveries.find((d) => d.delivery_id === deliveryId);
    if (!delivery) return;
    const finalDecisions: ImportDecision[] = delivery.items.map(
      (item) =>
        decisions[item.picnic_id] ?? {
          picnic_id: item.picnic_id,
          action: "skip",
        }
    );
    const result = await commit(deliveryId, finalDecisions);
    alert(
      `Importiert: ${result.imported} zugeordnet, ${result.created} neu, ${result.skipped} übersprungen.`
    );
    await fetchImport();
  };

  return (
    <div className="p-4 max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">Picnic-Bestellungen importieren</h1>

      <button
        onClick={fetchImport}
        disabled={loading}
        className="bg-blue-600 text-white px-4 py-2 rounded"
      >
        {loading ? "Lade..." : "Lieferungen abrufen"}
      </button>

      {error && <div className="text-red-600 mt-2">{error}</div>}

      {data && data.deliveries.length === 0 && (
        <div className="mt-4 text-gray-600">Keine neuen Lieferungen.</div>
      )}

      {data?.deliveries.map((delivery) => (
        <div key={delivery.delivery_id} className="mt-6">
          <h2 className="text-lg font-semibold mb-2">
            Lieferung {delivery.delivery_id} — {delivery.items.length} Artikel
          </h2>
          <div className="space-y-3">
            {delivery.items.map((item) => (
              <ReviewCard
                key={item.picnic_id}
                candidate={item}
                storageLocations={storageLocations}
                onChange={handleDecision}
              />
            ))}
          </div>
          <button
            onClick={() => handleCommit(delivery.delivery_id)}
            className="mt-4 bg-green-600 text-white px-4 py-2 rounded"
          >
            Bestätigte importieren
          </button>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Verify compile**

```bash
cd recipe-assistant/frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add recipe-assistant/frontend/src/components/picnic/ recipe-assistant/frontend/src/pages/PicnicImportPage.tsx
git commit -m "feat(picnic): add import page with review cards"
```

---

## Task 13: Frontend — Shopping List Page

**Files:**
- Create: `recipe-assistant/frontend/src/pages/ShoppingListPage.tsx`

- [ ] **Step 1: Create page**

Create `recipe-assistant/frontend/src/pages/ShoppingListPage.tsx`:

```typescript
import { useState } from "react";
import { useShoppingList, usePicnicSearch } from "../hooks/usePicnic";
import type { CartSyncResponse } from "../types";

export default function ShoppingListPage() {
  const { items, remove, update, sync, add } = useShoppingList();
  const { results, search } = usePicnicSearch();
  const [searchQuery, setSearchQuery] = useState("");
  const [syncResult, setSyncResult] = useState<CartSyncResponse | null>(null);

  const statusColor = (status: string) =>
    status === "mapped" ? "text-green-600" : "text-yellow-600";

  const handleSync = async () => {
    const result = await sync();
    setSyncResult(result);
  };

  const handleAddFromSearch = async (picnic_id: string, name: string) => {
    await add({ picnic_id, name, quantity: 1 });
    setSearchQuery("");
    search("");
  };

  return (
    <div className="p-4 max-w-3xl mx-auto">
      <h1 className="text-2xl font-bold mb-4">Einkaufsliste</h1>

      <div className="border rounded p-3 mb-4">
        <div className="flex gap-2">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => { setSearchQuery(e.target.value); search(e.target.value); }}
            placeholder="Picnic-Produkt suchen..."
            className="flex-1 border rounded px-2 py-1"
          />
        </div>
        {results.length > 0 && (
          <ul className="mt-2 max-h-60 overflow-y-auto">
            {results.map((r) => (
              <li key={r.picnic_id}>
                <button
                  onClick={() => handleAddFromSearch(r.picnic_id, r.name)}
                  className="w-full text-left px-2 py-1 hover:bg-gray-100"
                >
                  {r.name} <span className="text-sm text-gray-500">{r.unit_quantity}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      <ul className="space-y-2">
        {items.map((item) => (
          <li key={item.id} className="flex items-center gap-2 border rounded p-2">
            <span className={`font-bold ${statusColor(item.picnic_status)}`}>●</span>
            <span className="flex-1">{item.name}</span>
            <input
              type="number"
              min={1}
              value={item.quantity}
              onChange={(e) => update(item.id, { quantity: Number(e.target.value) })}
              className="w-16 border rounded px-1 py-0.5"
            />
            <button
              onClick={() => remove(item.id)}
              className="text-red-600 px-2"
            >
              ×
            </button>
          </li>
        ))}
      </ul>

      {items.length > 0 && (
        <button
          onClick={handleSync}
          className="mt-4 bg-green-600 text-white px-4 py-2 rounded"
        >
          In Picnic-Cart übertragen
        </button>
      )}

      {syncResult && (
        <div className="mt-4 border rounded p-3">
          <div>Hinzugefügt: {syncResult.added_count}</div>
          <div>Übersprungen (ohne Mapping): {syncResult.skipped_count}</div>
          <div>Fehlgeschlagen: {syncResult.failed_count}</div>
          {syncResult.failed_count > 0 && (
            <ul className="mt-2 text-sm text-red-600">
              {syncResult.results
                .filter((r) => r.status === "failed")
                .map((r) => (
                  <li key={r.shopping_list_id}>
                    Item #{r.shopping_list_id}: {r.failure_reason}
                  </li>
                ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify compile**

```bash
cd recipe-assistant/frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add recipe-assistant/frontend/src/pages/ShoppingListPage.tsx
git commit -m "feat(picnic): add shopping list page with cart sync UI"
```

---

## Task 14: Frontend — Wire Routes, Navbar, Inventory Integration

**Files:**
- Modify: `recipe-assistant/frontend/src/App.tsx`
- Modify: `recipe-assistant/frontend/src/components/Navbar.tsx`
- Modify: `recipe-assistant/frontend/src/pages/InventoryPage.tsx`

- [ ] **Step 1: Add routes in `App.tsx`**

Edit `recipe-assistant/frontend/src/App.tsx`. Add imports:

```typescript
import PicnicImportPage from "./pages/PicnicImportPage";
import ShoppingListPage from "./pages/ShoppingListPage";
```

Add routes inside `<Routes>` after the `/persons` route:

```tsx
        <Route path="/picnic-import" element={<PicnicImportPage />} />
        <Route path="/shopping-list" element={<ShoppingListPage />} />
```

- [ ] **Step 2: Add nav entries gated on Picnic status**

Read current `recipe-assistant/frontend/src/components/Navbar.tsx`, then add two new nav links visible only when Picnic is enabled. Use `usePicnicStatus` from the hook. Concretely: import the hook, call `const { status } = usePicnicStatus();`, and conditionally render two `<Link>` elements to `/picnic-import` and `/shopping-list` with labels "Picnic-Import" and "Einkaufsliste". Match the existing nav item styling (copy classes from nearby `<Link>` elements).

- [ ] **Step 3: Add "add to shopping list" button on inventory items**

In `recipe-assistant/frontend/src/pages/InventoryPage.tsx`, locate the per-item row rendering. Add a small button (plus icon, label "Einkaufsliste") next to the existing delete/edit buttons. On click, call `addShoppingListItem({ inventory_barcode: item.barcode, name: item.name, quantity: 1 })` from the api client. Import the function at the top of the file. Wrap the body of `InventoryPage` in a hook that checks `usePicnicStatus`; only render the button when `status?.enabled` is true. Show a toast on success via the existing NotificationProvider (check how other buttons in the file use it).

- [ ] **Step 4: Add "Picnic-Bestellung importieren" shortcut on inventory page**

Also in `InventoryPage.tsx`, when `status?.enabled`, add a link/button near the top of the page that navigates to `/picnic-import` using `useNavigate` from `react-router-dom`. Label: "Picnic-Bestellung importieren".

- [ ] **Step 5: Verify compile**

```bash
cd recipe-assistant/frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 6: Build frontend**

```bash
cd recipe-assistant/frontend && npm run build
```

Expected: successful build, no errors.

- [ ] **Step 7: Commit**

```bash
git add recipe-assistant/frontend/src/App.tsx recipe-assistant/frontend/src/components/Navbar.tsx recipe-assistant/frontend/src/pages/InventoryPage.tsx
git commit -m "feat(picnic): wire routes, navbar entries, and inventory-page shortcuts"
```

---

## Task 15: Final Verification & Smoke Test

**Files:** (no code changes — verification only)

- [ ] **Step 1: Run the full backend test suite**

```bash
cd recipe-assistant/backend && pytest -v
```

Expected: all tests pass. If any fail, stop and fix — do not proceed.

- [ ] **Step 2: Verify frontend typecheck and build**

```bash
cd recipe-assistant/frontend && npx tsc --noEmit && npm run build
```

Expected: no TypeScript errors, successful build.

- [ ] **Step 3: Verify Alembic migration chain on Postgres target (dry run)**

```bash
cd recipe-assistant/backend && alembic upgrade head --sql | tail -40
```

Expected: SQL output shows CREATE TABLE statements for `picnic_products`, `ean_picnic_map`, `picnic_delivery_imports`, `shopping_list`. No errors.

- [ ] **Step 4: Verify the addon builds inside the Docker image**

From repo root:

```bash
docker build -f recipe-assistant/Dockerfile -t inv-addon-test recipe-assistant
```

Expected: image builds without errors. `python-picnic-api2` and `rapidfuzz` install cleanly.

- [ ] **Step 5: Run the container with Picnic disabled and verify non-Picnic endpoints still work**

```bash
docker run --rm -p 8080:8080 -e PICNIC_EMAIL= inv-addon-test &
sleep 5
curl -s http://localhost:8080/api/picnic/status | python -m json.tool
```

Expected: `{"enabled": false, "account": null}`. Kill container after: `docker stop $(docker ps -q --filter ancestor=inv-addon-test)`.

- [ ] **Step 6: Manual smoke test checklist (skip if no Picnic account available)**

If a Picnic DE account is available:

1. Set `PICNIC_EMAIL` and `PICNIC_PASSWORD` in the addon config (or as env vars for local run).
2. Open `/api/picnic/status` — should return `enabled: true` with account info.
3. Open the frontend, verify new nav items appear.
4. Navigate to "Picnic-Import", click "Lieferungen abrufen" — should list any delivered but not-yet-imported orders.
5. Walk through a review: confirm a high-confidence match, create-new for another, commit. Verify the inventory page now shows the imported items.
6. Navigate to Einkaufsliste, add an item from the inventory via the "+ Einkaufsliste" button. Verify it shows up with the correct mapping status.
7. Click "In Picnic-Cart übertragen" — check the Picnic app/web to confirm the item arrived.
8. Trigger a second "Lieferungen abrufen" — should report zero new deliveries (dedup works).

- [ ] **Step 7: Final commit** (if any fixups from smoke test)

Only if you made fixes during smoke testing:

```bash
git add <files>
git commit -m "fix(picnic): address smoke-test findings"
```

Otherwise, nothing to commit.

- [ ] **Step 8: Summary**

Verify by running:

```bash
git log --oneline main..HEAD
```

Expected: ~14 commits, one per task, all descriptive. Feature is complete.

---

## Self-Review Notes

This plan has been checked against the spec:

- **Spec coverage:**
  - Architecture (services/picnic/ sub-package) → Tasks 4–8
  - Data model (4 tables) → Task 2
  - Pydantic schemas → Task 3
  - API endpoints (11 endpoints) → Task 9
  - Matching algorithm (normalize, score, tiers, N:M) → Task 4
  - UI flows (import review, shopping list, scan-during-review) → Tasks 12–14
  - Error handling (503 on disabled, auth retry, transactional commit) → Tasks 6, 7, 9
  - Testing (unit + integration, fake client) → Tasks 4–9
  - Synthetic barcode + promotion → Task 7 (commit_import_decisions with scanned_ean)
  - HA addon config schema → Task 1
  - Feature gating via PICNIC_EMAIL → Task 9 (_feature_enabled)

- **Placeholder scan:** No "TBD", "TODO", "add appropriate error handling", or similar phrases in step bodies. Navbar step (14.2) and InventoryPage integration step (14.3–4) describe the change textually rather than showing full code because the implementer needs to match existing styling patterns that vary by file; the instructions are specific about what to import, which API to call, and what state to render against.

- **Type consistency:** `PicnicClient.add_product(picnic_id, count=1)` used in Tasks 6, 8, 9. `compute_match_suggestions` signature consistent between Tasks 4 and 7. `ImportDecision` shape consistent across schemas (Task 3), service (Task 7), router (Task 9), and frontend (Task 10).
