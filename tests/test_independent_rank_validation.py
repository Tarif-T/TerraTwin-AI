"""Independent validation must cover multiple sites, ties and rejected measurements."""

import pytest
from conftest import changed

from scripts.validate_real_slice import independent_ranking
from terratwin.models import FEATURES
from terratwin.scoring.engine import rank_candidates


def test_independent_order_score_coverage_and_rejections(reference, earth_sites, scoring_config):
    sites = [*reversed(earth_sites)]
    sites[0] = changed(sites[0], **dict.fromkeys(FEATURES), qa_pass=False)
    sites[1] = changed(sites[1], slope_median_deg=None, relief_p90_p10_m=None)
    # Same measurements, deliberately reverse ID order; ties must be deterministic.
    sites[2] = changed(sites[-1], site_id="SYNTHETIC_Z_TIE")
    sites[3] = changed(sites[-1], site_id="SYNTHETIC_A_TIE")
    actual = rank_candidates(reference, sites, scoring_config)
    independent = independent_ranking(reference, sites, scoring_config)
    for row, expected in zip(actual, independent, strict=True):
        for key in ("site_id", "rank", "eligible"):
            assert row[key] == expected[key]
        for key in ("similarity_index", "feature_coverage"):
            assert (
                row[key] == pytest.approx(expected[key])
                if expected[key] is not None
                else row[key] is None
            )
    assert sum(row["eligible"] for row in independent) == 10
