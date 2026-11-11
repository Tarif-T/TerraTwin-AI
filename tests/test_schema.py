import pytest
from conftest import changed

from terratwin.ingest.manifest import load_manifest
from terratwin.models import Profile


@pytest.mark.parametrize(
    "field,value",
    [
        ("slope_median_deg", 90),
        ("relief_p90_p10_m", -1),
        ("roughness_local_std_m", float("nan")),
        ("steep_fraction_15deg", 1.1),
        ("valid_cell_fraction", -0.1),
        ("source_ids", []),
        ("config_sha256", "unknown"),
    ],
)
def test_invalid_profile(reference, field, value):
    with pytest.raises(ValueError):
        changed(reference, **{field: value})


def test_unknown_columns_rejected(reference):
    with pytest.raises(ValueError):
        Profile.model_validate({**reference.model_dump(), "invented_feature": 1})


def test_null_not_coerced(reference):
    assert changed(reference, slope_median_deg=None).slope_median_deg is None


def test_manifest_required(tmp_path):
    path = tmp_path / "sources.csv"
    path.write_text("source_id,provider\n", encoding="utf-8")
    with pytest.raises(ValueError, match="empty"):
        load_manifest(path)
