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
        # Name matches but units differ - no +10 bonus
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
