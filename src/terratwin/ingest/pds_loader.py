from pathlib import Path

from terratwin.ingest.raster_input import validate_local_raster
from terratwin.models import SourceRecord


def load_pds(raster_path: Path, interpretation_path: Path, source: SourceRecord):
    if source.planetary_body not in ("Mars", "Moon"):
        raise ValueError("PDS terrain adapter requires Mars or Moon")
    return validate_local_raster(raster_path, interpretation_path, source, source.planetary_body)
