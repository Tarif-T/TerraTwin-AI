"""Features on a square metric grid; full valid derivative stencils only."""

from dataclasses import dataclass

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from terratwin.models import Measurements


@dataclass(frozen=True)
class FeatureResult:
    measurements: Measurements
    valid_cell_fraction: float
    valid_elevation_count: int
    valid_slope_count: int
    valid_roughness_count: int


def extract_features(
    elevation: np.ndarray,
    pixel_size_m: float,
    valid_mask: np.ndarray | None = None,
    roughness_kernel_cells: int = 3,
) -> FeatureResult:
    """Central differences; roughness uses population std on fully valid windows.

    Edge cells are excluded from both derivative metrics. Elevation quantiles use
    all valid ROI cells. No interpolation or nodata replacement is performed.
    """
    z = np.asarray(np.ma.getdata(elevation), dtype=float)
    if z.ndim != 2 or min(z.shape) < 3:
        raise ValueError("DEM must be a 2D array with at least 3x3 cells")
    if not np.isfinite(pixel_size_m) or pixel_size_m <= 0:
        raise ValueError("pixel_size_m must be finite and positive")
    k = roughness_kernel_cells
    if not isinstance(k, int) or k < 3 or k % 2 != 1 or k > min(z.shape):
        raise ValueError("Roughness kernel must be odd, >=3, and fit within the DEM")
    mask = np.isfinite(z) & ~np.ma.getmaskarray(elevation)
    if valid_mask is not None:
        if np.shape(valid_mask) != z.shape:
            raise ValueError("Validity mask must match DEM shape")
        mask &= np.asarray(valid_mask, dtype=bool)
    # NaN in invalid cells propagates only within a stencil; it never becomes sea level.
    z = np.where(mask, z, np.nan)
    stencil = mask[1:-1, 1:-1] & mask[1:-1, :-2] & mask[1:-1, 2:] & mask[:-2, 1:-1] & mask[2:, 1:-1]
    dx = (z[1:-1, 2:] - z[1:-1, :-2]) / (2 * pixel_size_m)
    dy = (z[2:, 1:-1] - z[:-2, 1:-1]) / (2 * pixel_size_m)
    slopes = np.degrees(np.arctan(np.hypot(dx, dy)))[stencil]
    windows = sliding_window_view(z, (k, k))
    window_mask = sliding_window_view(mask, (k, k)).all(axis=(-1, -2))
    roughness = np.std(windows[window_mask], axis=(-1, -2))
    values = z[mask]
    measurements = Measurements(
        slope_median_deg=float(np.median(slopes)) if slopes.size else None,
        relief_p90_p10_m=float(np.diff(np.percentile(values, [10, 90]))[0])
        if values.size
        else None,
        roughness_local_std_m=float(np.median(roughness)) if roughness.size else None,
        steep_fraction_15deg=float(np.mean(slopes > 15)) if slopes.size else None,
    )
    return FeatureResult(measurements, float(mask.mean()), values.size, slopes.size, roughness.size)
