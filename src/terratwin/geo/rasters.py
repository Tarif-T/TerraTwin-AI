"""Bounded ROI reprojection with nodata preservation and no resolution invention."""

import numpy as np
import rasterio
from pyproj import Transformer
from rasterio.enums import Resampling
from rasterio.transform import from_origin
from rasterio.warp import reproject, transform_bounds
from rasterio.windows import Window, from_bounds

from terratwin.geo.coordinates import validate_body_crs
from terratwin.ingest.raster_input import RasterInterpretation


def metric_roi(
    raster_path,
    metadata: RasterInterpretation,
    destination_crs: str,
    bounds: tuple[float, float, float, float],
    grid_m: float,
    roi_size_km: float,
) -> np.ndarray:
    target = validate_body_crs(destination_crs, metadata.body, metric=True)
    left, bottom, right, top = bounds
    if not np.isfinite([*bounds, grid_m, roi_size_km]).all() or grid_m <= 0:
        raise ValueError("Bounds and grid must be finite, with positive grid size")
    width, height = right - left, top - bottom
    size_m = roi_size_km * 1000
    if not np.allclose([width, height], size_m, rtol=0, atol=0.001):
        raise ValueError("ROI bounds must match the declared square physical footprint")
    cells = size_m / grid_m
    if not np.isclose(cells, round(cells)) or not 3 <= cells <= 2000:
        raise ValueError("ROI must contain 3..2000 whole analysis cells per side")
    shape = (round(cells), round(cells))
    with rasterio.open(raster_path) as dataset:
        inverse = Transformer.from_crs(target, dataset.crs, always_xy=True)
        forward = Transformer.from_crs(dataset.crs, target, always_xy=True)
        geographic = target.geodetic_crs
        to_geographic = Transformer.from_crs(target, geographic, always_xy=True)
        # Check entire ROI latitude band, rather than centroid alone.
        lons, lats = to_geographic.transform(
            [left, right, left, right],
            [bottom, bottom, top, top],
        )
        if metadata.body == "Earth" and (min(lats) < -56 or max(lats) > 60):
            raise ValueError("NASADEM ROI extends beyond 56 S to 60 N coverage")
        # Source spacing is measured in destination metres at nine ROI locations.
        # Conservative maximum prevents upsampling in either axis.
        for x in np.linspace(left, right, 3):
            for y in np.linspace(bottom, top, 3):
                sx, sy = inverse.transform(x, y)
                row, col = dataset.index(sx, sy)
                points = [dataset.xy(row, col), dataset.xy(row, col + 1), dataset.xy(row + 1, col)]
                projected = [forward.transform(*point) for point in points]
                spacings = [
                    np.hypot(p[0] - projected[0][0], p[1] - projected[0][1]) for p in projected[1:]
                ]
                if not np.isfinite(spacings).all() or max(spacings) > grid_m * 1.001:
                    raise ValueError(
                        "Source resolution is coarser than analysis grid; choose a coarser grid"
                    )
        src_bounds = transform_bounds(target, dataset.crs, *bounds, densify_pts=21)
        window = from_bounds(*src_bounds, transform=dataset.transform)
        window = Window(
            np.floor(window.col_off) - 2,
            np.floor(window.row_off) - 2,
            np.ceil(window.width) + 4,
            np.ceil(window.height) + 4,
        )
        try:
            window.intersection(Window(0, 0, dataset.width, dataset.height))
        except rasterio.errors.WindowError as error:
            raise ValueError("ROI does not intersect source raster") from error
        if window.width * window.height > 25_000_000:
            raise ValueError("ROI input exceeds memory limit; pre-clip/mosaic the source offline")
        raw = dataset.read(1, window=window, masked=True, boundless=True).astype("float64")
        mask = np.ma.getmaskarray(raw) | (raw.data == metadata.nodata) | ~np.isfinite(raw.data)
        source = np.where(mask, np.nan, raw.data * metadata.scale + metadata.offset)
        output = np.full(shape, np.nan)
        reproject(
            source=source,
            destination=output,
            src_transform=dataset.window_transform(window),
            src_crs=dataset.crs,
            src_nodata=np.nan,
            dst_transform=from_origin(left, top, grid_m, grid_m),
            dst_crs=target,
            dst_nodata=np.nan,
            resampling=Resampling.average,
            num_threads=1,
        )
        ground_fraction = np.zeros(shape)
        reproject(
            source=(~mask).astype("float64"),
            destination=ground_fraction,
            src_transform=dataset.window_transform(window),
            src_crs=dataset.crs,
            dst_transform=from_origin(left, top, grid_m, grid_m),
            dst_crs=target,
            resampling=Resampling.average,
            num_threads=1,
        )
        # Do not count a partly masked aggregate as fully observed terrain.
        output[ground_fraction < 1 - 1e-6] = np.nan
    return output
