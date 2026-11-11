import csv
import io
import json

import pytest
from conftest import changed

from terratwin.export.csv_export import export_analysis
from terratwin.models import FEATURES, ScoringConfig
from terratwin.scoring.engine import rank_candidates


def test_identical_and_monotonic(reference, earth_sites, scoring_config):
    results = rank_candidates(reference, earth_sites, scoring_config)
    assert len(results) == 12
    assert results[0]["similarity_index"] == pytest.approx(100)
    assert results[0]["feature_coverage"] == pytest.approx(1)
    assert all(a["similarity_index"] > b["similarity_index"] for a, b in zip(results, results[1:]))


def test_missing_high_weight_features_ineligible(reference, earth_sites, scoring_config):
    site = changed(earth_sites[0], slope_median_deg=None, relief_p90_p10_m=None)
    result = rank_candidates(reference, [site], scoring_config)[0]
    assert result["feature_coverage"] == pytest.approx(0.3)
    assert not result["eligible"]
    assert result["rank"] is None
    assert result["components"][FEATURES[0]]["missing"]


def test_missing_reference_disclosed_conservative_coverage(reference, earth_sites, scoring_config):
    ref = changed(reference, slope_median_deg=None)
    result = rank_candidates(ref, earth_sites[:1], scoring_config)[0]
    assert result["reference_feature_coverage"] == pytest.approx(0.6)
    assert result["feature_coverage"] == pytest.approx(0.6)
    assert "Missing reference" in result["warning"]
    assert not result["eligible"]


def test_all_missing_candidate(reference, earth_sites, scoring_config):
    site = changed(earth_sites[0], qa_pass=False, **dict.fromkeys(FEATURES))
    result = rank_candidates(reference, [site], scoring_config)[0]
    assert result["similarity_index"] is None
    assert result["feature_coverage"] == 0
    assert not result["eligible"]


@pytest.mark.parametrize(
    "field,value",
    [
        ("common_grid_m", 2000),
        ("roi_size_km", 30),
        ("roughness_kernel_cells", 5),
        ("features_version", "different"),
    ],
)
def test_incompatible_physical_scale_rejected(reference, earth_sites, scoring_config, field, value):
    with pytest.raises(ValueError, match="Incompatible"):
        rank_candidates(reference, [changed(earth_sites[0], **{field: value})], scoring_config)


def test_stable_ties_and_permutation(reference, earth_sites, scoring_config):
    sites = [changed(site, slope_median_deg=10) for site in earth_sites]
    first = rank_candidates(reference, sites, scoring_config)
    assert first == rank_candidates(reference, list(reversed(sites)), scoring_config)
    assert [r["site_id"] for r in first] == sorted(site.site_id for site in sites)


@pytest.mark.parametrize(
    "updates",
    [
        {"weights": dict.fromkeys(FEATURES, 0)},
        {"weights": dict.fromkeys(FEATURES, -1)},
        {"weights": dict.fromkeys(FEATURES, float("nan"))},
        {"tolerances": dict.fromkeys(FEATURES, 0)},
        {"tolerances": dict.fromkeys(FEATURES, float("inf"))},
        {"weights": {"unknown": 1}},
    ],
)
def test_invalid_scoring_config(scoring_config, updates):
    with pytest.raises(ValueError):
        ScoringConfig.model_validate({**scoring_config.model_dump(), **updates})


def test_weights_normalized(reference, earth_sites, scoring_config):
    config = ScoringConfig.model_validate(
        {
            **scoring_config.model_dump(),
            "weights": {n: w * 100 for n, w in scoring_config.weights.items()},
        }
    )
    assert rank_candidates(reference, earth_sites, config) == rank_candidates(
        reference,
        earth_sites,
        scoring_config,
    )


def test_qa_gating(reference, earth_sites, scoring_config):
    site = changed(earth_sites[0], valid_cell_fraction=0.89)
    assert not rank_candidates(reference, [site], scoring_config)[0]["eligible"]
    with pytest.raises(ValueError, match="Reference"):
        rank_candidates(changed(reference, qa_pass=False), earth_sites, scoring_config)


def test_export_matches_scores_and_active_config(reference, earth_sites, scoring_config):
    results = rank_candidates(reference, earth_sites, scoring_config)
    exported = export_analysis(reference, earth_sites, results, scoring_config)
    rows = list(csv.DictReader(io.StringIO(exported)))
    assert len(rows) == len(results)
    for row, result in zip(rows, results):
        assert float(row["similarity_index"]) == result["similarity_index"]
        assert float(row["feature_coverage"]) == result["feature_coverage"]
        assert json.loads(row["weights"]) == scoring_config.normalized_weights
        assert json.loads(row["tolerances"]) == scoring_config.tolerances
        assert row["reference_profile_id"] == reference.profile_id
        assert "SYNTHETIC_SOURCE" in row["source_ids"]
    assert exported == export_analysis(
        reference, list(reversed(earth_sites)), results, scoring_config
    )


def test_duplicate_sites_rejected(reference, earth_sites, scoring_config):
    with pytest.raises(ValueError, match="Duplicate"):
        rank_candidates(reference, earth_sites[:1] * 2, scoring_config)
