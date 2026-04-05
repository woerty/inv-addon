from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from rapidfuzz import fuzz

CONFIDENT_THRESHOLD = 92
UNCERTAIN_THRESHOLD = 75
WEAK_THRESHOLD = 60
UNIT_BONUS = 10.0
UNIT_PENALTY = 15.0
UNIT_TOLERANCE = 0.10  # 10 percent

# Regex patterns for normalization
_PAREN_RE = re.compile(r"\([^)]*\)")
_PERCENT_RE = re.compile(r"\d+(?:[.,]\d+)?\s*%")
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
    """Lowercase, strip brand-in-parens, strip percentage annotations, strip
    unit strings, collapse whitespace, and transliterate German umlauts."""
    if not raw:
        return ""
    s = raw.lower().translate(_UMLAUT_MAP)
    s = _PAREN_RE.sub(" ", s)
    s = _PERCENT_RE.sub(" ", s)
    s = _MULTI_RE.sub(" ", s)
    s = _UNIT_RE.sub(" ", s)
    s = _PUNCT_RE.sub(" ", s)
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
    """Return top-5 matches, sorted by score desc, filtered to score >= WEAK_THRESHOLD.

    Scoring rules:
    - Base: token_set_ratio on normalized names.
    - +UNIT_BONUS  if picnic_unit and candidate unit are both present and agree.
    - -UNIT_PENALTY if picnic_unit and candidate unit are both present and disagree.
    - Candidates whose unit cannot be parsed receive no bonus or penalty.
    """
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
            elif cand_unit is not None:
                score = max(0.0, score - UNIT_PENALTY)
                reason_parts.append("unit mismatch")

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
