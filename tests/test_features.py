import numpy as np
import pytest

from terratwin.geo.features import extract_features
from terratwin.geo.quality import quality_reasons


def test_constant_terrain():
    result = extract_features(np.full((8, 8), 1500.0), 1000)
    assert all(value == 0 for value in result.measurements.model_dump().values())
    assert result.valid_slope_count == 36
    assert result.valid_roughness_count == 36
    assert not quality_reasons(result)


@pytest.mark.parametrize("a,b", [(0.1, 0.2), (0, 0), (1, 0), (-0.4, 0.2)])
def test_analytic_plane(a, b):
    y, x = np.mgrid[:12, :12] * 1000
    result = extract_features(a * x + b * y + 2500, 1000)
    slope = np.degrees(np.arctan(np.hypot(a, b)))
    assert result.measurements.slope_median_deg == pytest.approx(slope)
    assert result.measurements.steep_fraction_15deg == (1 if slope > 15 else 0)
    # Variance of coordinates [-1000, 0, 1000] is 2/3 * 1000**2.
    assert result.measurements.roughness_local_std_m == pytest.approx(
        np.sqrt((a * a + b * b) * 2 / 3) * 1000,
    )


def test_masked_cells_excluded_from_all_metrics():
    z = np.full((7, 7), 2000.0)
    z[3, 3] = -9999
    result = extract_features(z, 1000, z != -9999)
    assert result.valid_cell_fraction == pytest.approx(48 / 49)
    assert result.valid_slope_count == 20
    assert result.valid_roughness_count == 16
    assert result.measurements.relief_p90_p10_m == 0
    assert result.measurements.slope_median_deg == 0
    assert result.measurements.roughness_local_std_m == 0


def test_native_mask_and_nonfinite_cells():
    z = np.ma.array(np.ones((5, 5)), mask=False)
    z.mask[1, 1] = True
    z[3, 3] = np.inf
    assert extract_features(z, 1000).valid_elevation_count == 23


def test_known_relief_and_datum_offset_invariance():
    z = np.arange(100).reshape(10, 10).astype(float)
    base = extract_features(z, 1000)
    shifted = extract_features(z + 100_000, 1000)
    assert base.measurements.relief_p90_p10_m == pytest.approx(79.2)
    assert base.measurements.model_dump() == pytest.approx(shifted.measurements.model_dump())


def test_no_data_is_insufficient_not_zero():
    result = extract_features(np.full((5, 5), np.nan), 1000)
    assert result.valid_cell_fraction == 0
    assert all(v is None for v in result.measurements.model_dump().values())
    assert len(quality_reasons(result)) == 5


@pytest.mark.parametrize("spacing", [0, -1, np.inf, np.nan])
def test_invalid_spacing(spacing):
    with pytest.raises(ValueError):
        extract_features(np.zeros((5, 5)), spacing)


def test_invalid_mask_and_kernel():
    with pytest.raises(ValueError, match="mask"):
        extract_features(np.zeros((5, 5)), 1000, np.ones((4, 4)))
    with pytest.raises(ValueError, match="kernel"):
        extract_features(np.zeros((5, 5)), 1000, roughness_kernel_cells=4)


def test_coverage_quality_threshold():
    z = np.zeros((10, 10))
    z[:2] = np.nan
    assert "coverage" in quality_reasons(extract_features(z, 1000))[0]
