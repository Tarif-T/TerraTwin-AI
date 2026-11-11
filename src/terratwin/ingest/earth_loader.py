from pathlib import Path

from terratwin.ingest.raster_input import validate_local_raster
from terratwin.models import SourceRecord


def load_nasadem(raster_path: Path, interpretation_path: Path, source: SourceRecord):
    if source.dataset != "NASADEM_HGT" or source.version != "001":
        raise ValueError("Earth adapter requires NASADEM_HGT version 001")
    return validate_local_raster(raster_path, interpretation_path, source, "Earth")
