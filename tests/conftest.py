"""All measurements, coordinates and rasters in this directory are SYNTHETIC TEST DATA."""

from datetime import datetime, timezone

import pytest

from terratwin.config import load_scoring
from terratwin.models import Profile


@pytest.fixture
def scoring_config():
    return load_scoring()


@pytest.fixture
def reference():
    return Profile(
        profile_id="SYNTHETIC_MARS",
        body="Mars",
        region_name="Synthetic test plane",
        roi_id="SYNTHETIC_ROI",
        roi_size_km=60,
        common_grid_m=1000,
        valid_cell_fraction=1,
        qa_pass=True,
        source_ids=["SYNTHETIC_SOURCE"],
        processing_version="terrain_v1",
        config_sha256="0" * 64,
        created_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
        coordinate_convention="synthetic test only",
        processing_notes="SYNTHETIC TEST ONLY",
        synthetic=True,
        slope_median_deg=10,
        relief_p90_p10_m=1000,
        roughness_local_std_m=200,
        steep_fraction_15deg=0.1,
    )


def changed(profile, **updates):
    return Profile.model_validate({**profile.model_dump(), **updates})


@pytest.fixture
def earth_sites(reference):
    # Twelve structurally valid synthetic records; never saved under data/.
    return [
        changed(
            reference,
            profile_id=f"SYNTHETIC_EARTH_{i:02}",
            site_id=f"SYNTHETIC_{i:02}",
            site_name=f"Synthetic site {i}",
            country="TEST ONLY",
            body="Earth",
            centroid_lat=0,
            centroid_lon=0,
            slope_median_deg=10 + i,
        )
        for i in range(12)
    ]
