"""Acquire public metadata and validate NASADEM archives before registration."""

import re
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

import requests

from terratwin.geo.regions import geographic_ring
from terratwin.ingest.manifest import sha256_file

CMR_SEARCH = "https://cmr.earthdata.nasa.gov/search/granules.umm_json"
CMR_CONCEPT = "https://cmr.earthdata.nasa.gov/search/concepts/"
SIZES = {"hgt": 3601 * 3601 * 2, "swb": 3601 * 3601, "num": 3601 * 3601}


def tile_center(tile):
    if not re.fullmatch(r"[ns]\d{2}[ew]\d{3}", tile):
        raise ValueError("Invalid NASADEM tile ID")
    south = int(tile[1:3]) * (1 if tile[0] == "n" else -1)
    west = int(tile[4:7]) * (1 if tile[3] == "e" else -1)
    if not (-56 <= south < 60 and -180 <= west < 180):
        raise ValueError("Tile outside NASADEM coverage")
    return south + 0.5, west + 0.5


def validate_metadata(item, tile):
    umm = item["umm"]
    if umm["GranuleUR"] != f"NASADEM_HGT_{tile}":
        raise ValueError("CMR granule identity mismatch")
    if umm["CollectionReference"] != {"ShortName": "NASADEM_HGT", "Version": "001"}:
        raise ValueError("CMR collection mismatch")
    lat, lon = tile_center(tile)
    rectangle = umm["SpatialExtent"]["HorizontalSpatialDomain"]["Geometry"]["BoundingRectangles"][0]
    expected = {"South": lat - 0.5, "North": lat + 0.5, "West": lon - 0.5, "East": lon + 0.5}
    for direction, value in expected.items():
        if abs(rectangle[f"{direction}BoundingCoordinate"] - value) > 0.001:
            raise ValueError("CMR extent disagrees with tile identity")
    crs = f"+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m +type=crs"
    ring = geographic_ring(crs, "Earth", [-30000, -30000, 30000, 30000])
    if not all(lon - 0.5 < x < lon + 0.5 and lat - 0.5 < y < lat + 0.5 for x, y in ring):
        raise ValueError("60 km ROI requires more than one source tile")
    urls = [r["URL"] for r in umm["RelatedUrls"] if r.get("Type") == "GET DATA"]
    expected_path = f"/lp-prod-protected/NASADEM_HGT.001/NASADEM_HGT_{tile}/"
    expected_path += f"NASADEM_HGT_{tile}.zip"
    for url in urls:
        parts = urlsplit(url)
        if (
            parts.scheme == "https"
            and parts.netloc == "data.lpdaac.earthdatacloud.nasa.gov"
            and parts.path == expected_path
            and not parts.query
        ):
            return url, lat, lon, crs, ring
    raise ValueError("CMR did not provide the expected official archive URL")


def download_archive(session, url, destination):
    """Requests uses an existing local .netrc; never logs credentials or redirects."""
    destination = Path(destination)
    partial = destination.with_suffix(".zip.part")
    try:
        with session.get(url, stream=True, timeout=(15, 60)) as response:
            if response.status_code in (401, 403):
                raise PermissionError("NASA Earthdata authentication is required")
            response.raise_for_status()
            with partial.open("wb") as stream:
                size = 0
                for block in response.iter_content(1024 * 1024):
                    size += len(block)
                    if size > 64 * 1024 * 1024:
                        raise ValueError("Unexpectedly large NASADEM archive")
                    stream.write(block)
        if not zipfile.is_zipfile(partial):
            raise PermissionError("NASA returned a login page instead of a ZIP archive")
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)


def extract_archive(archive, destination, tile):
    """Whitelist exact names/sizes, verify ZIP CRC, and preserve existing raw members."""
    destination = Path(destination)
    with zipfile.ZipFile(archive) as bundle:
        required = {f"{tile}.{ext}": size for ext, size in SIZES.items()}
        for name, size in required.items():
            matches = [info for info in bundle.infolist() if info.filename == name]
            if len(matches) != 1 or matches[0].file_size != size:
                raise ValueError(f"Missing, duplicate or incorrect-size NASADEM member: {name}")
        # Read all required members before writing anything; read verifies CRC.
        payloads = {name: bundle.read(name) for name in required}
    for name, payload in payloads.items():
        path = destination / name
        if path.exists() and path.read_bytes() != payload:
            raise ValueError(f"Refusing to overwrite changed raw file: {name}")
    destination.mkdir(parents=True, exist_ok=True)
    for name, payload in payloads.items():
        path = destination / name
        if not path.exists():
            path.write_bytes(payload)
    return {ext: sha256_file(destination / f"{tile}.{ext}") for ext in SIZES}


def validate_extracted(directory, tile):
    """Check complete native member sets without claiming unavailable ZIP integrity."""
    import numpy as np
    import rasterio

    directory = Path(directory)
    lat, lon = tile_center(tile)
    for ext, size in SIZES.items():
        path = directory / f"{tile}.{ext}"
        if not path.is_file() or path.stat().st_size != size:
            raise ValueError(f"Missing or incorrect-size extracted NASADEM member: {path.name}")
    with rasterio.open(directory / f"{tile}.hgt") as dataset:
        if (dataset.width, dataset.height, dataset.count) != (3601, 3601, 1):
            raise ValueError("Unexpected NASADEM raster dimensions")
        if dataset.crs != rasterio.crs.CRS.from_epsg(4326) or dataset.dtypes != ("int16",):
            raise ValueError("Unexpected NASADEM raster CRS or sample type")
        x, y = dataset.xy(1800, 1800)
        if abs(x - lon) > 1e-8 or abs(y - lat) > 1e-8:
            raise ValueError("NASADEM raster center disagrees with metadata")
        if not np.any(dataset.read(1, masked=True).compressed() != -32768):
            raise ValueError("NASADEM elevation has no valid samples")
    water = np.memmap(directory / f"{tile}.swb", dtype="uint8", mode="r")
    if not np.all((water == 0) | (water == 255)):
        raise ValueError("Unexpected NASADEM SWB classes; expected 0=land and 255=water")
    del water
    return {ext: sha256_file(directory / f"{tile}.{ext}") for ext in SIZES}


def retrieve_metadata(session: requests.Session, tile):
    response = session.get(
        CMR_SEARCH,
        params={
            "short_name": "NASADEM_HGT",
            "version": "001",
            "readable_granule_name": f"NASADEM_HGT_{tile}",
            "page_size": 2,
        },
        timeout=(15, 30),
    )
    response.raise_for_status()
    items = response.json()["items"]
    if len(items) != 1:
        raise ValueError(f"Expected exactly one NASADEM granule for {tile}")
    validate_metadata(items[0], tile)
    return items[0]
