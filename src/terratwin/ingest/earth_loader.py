from pathlib import Path

from terratwin.ingest.raster_input import validate_local_raster
from terratwin.models import SourceRecord


def load_nasadem(raster_path: Path, interpretation_path: Path, source: SourceRecord):
    if source.dataset != "NASADEM_HGT" or source.version != "001":
        raise ValueError("Earth adapter requires NASADEM_HGT version 001")
    metadata = validate_local_raster(raster_path, interpretation_path, source, "Earth")
    if metadata.latitude_bounds_deg != (-56, 60):
        raise ValueError("NASADEM source coverage must remain 56 S to 60 N")
    return metadata


def load_earth(raster_path: Path, interpretation_path: Path, source: SourceRecord):
    if source.dataset == "NASADEM_HGT":
        return load_nasadem(raster_path, interpretation_path, source)
    if source.dataset == "USGS_3DEP":
        metadata = validate_local_raster(raster_path, interpretation_path, source, "Earth")
        if (
            metadata.horizontal_datum != "NAD83"
            or metadata.vertical_datum != "NAVD88"
            or metadata.latitude_bounds_deg != (24, 50)
            or metadata.scale != 1
            or metadata.offset != 0
            or metadata.mask_path is None
        ):
            raise ValueError("USGS CONUS intake requires audited NAD83/NAVD88 metres and land mask")
        return metadata
    if source.dataset not in ("REMA", "ArcticDEM"):
        raise ValueError("Unsupported Earth elevation source")
    metadata = validate_local_raster(raster_path, interpretation_path, source, "Earth")
    if metadata.vertical_datum != "WGS84 ellipsoid" or metadata.scale != 1 or metadata.offset != 0:
        raise ValueError("PGC DEMs require unmodified WGS84 ellipsoidal metre heights")
    expected = (-90, -60) if source.dataset == "REMA" else (50, 90)
    if metadata.latitude_bounds_deg != expected:
        raise ValueError("PGC source latitude domain differs from audited interpretation")
    return metadata
