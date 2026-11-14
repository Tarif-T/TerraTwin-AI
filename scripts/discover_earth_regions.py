"""Systematically propose new polar Earth ROIs from public ArcticDEM tile coverage.

Search is bounded by a geographic box and download count, not by hand-picked
analog names. Candidate centers are fixed before terrain scores are computed.
Unknown novelty is never interpreted as proof of a previously unknown analog.
"""

import argparse
import csv
import json
from datetime import datetime, timezone
from xml.etree import ElementTree as ET

import rasterio
import yaml
from pyproj import Transformer

from scripts.prepare_challenge_data import obtain
from terratwin.config import ROOT, read_yaml
from terratwin.geo.regions import geographic_ring
from terratwin.ingest.manifest import load_manifest, sha256_file
from terratwin.models import SourceRecord

BASE = "https://pgc-opendata-dems.s3.us-west-2.amazonaws.com/"


def tile_proposals(vrt_text, bbox):
    root = ET.fromstring(vrt_text)
    transform = [float(v) for v in root.findtext("GeoTransform").split(",")]
    to_geo = Transformer.from_crs(3413, 4326, always_xy=True)
    west, south, east, north = bbox
    if not (-180 <= west < east <= 180 and 50 <= south < north <= 90):
        raise ValueError("Search box must be a non-dateline Arctic region")
    rows = {}
    for source in root.findall(".//ComplexSource"):
        name = source.findtext("SourceFilename")
        if not name or not name.endswith("_dem.tif"):
            continue
        rectangle = source.find("DstRect").attrib
        left = transform[0] + float(rectangle["xOff"]) * transform[1]
        top = transform[3] + float(rectangle["yOff"]) * transform[5]
        x = left + float(rectangle["xSize"]) * transform[1] / 2
        y = top + float(rectangle["ySize"]) * transform[5] / 2
        lon, lat = to_geo.transform(x, y)
        if west <= lon <= east and south <= lat <= north:
            key = name.removeprefix("/vsis3/pgc-opendata-dems/")
            rows[key] = dict(
                tile=key.split("/")[-2],
                longitude=lon,
                latitude=lat,
                source_url=BASE + key,
                x=x,
                y=y,
            )
    return [rows[key] for key in sorted(rows)]


def discover(bbox, max_tiles):
    if not 1 <= max_tiles <= 10:
        raise ValueError("Download count must be 1..10")
    raw = ROOT / "data/raw/Earth/ArcticDEM_discovery"
    raw.mkdir(exist_ok=True)
    index = raw / "arcticdem_v4.1_32m.vrt"
    obtain(BASE + "arcticdem/mosaics/v4.1/32m_dem_tiles.vrt", index, limit=5_000_000)
    proposals = tile_proposals(index.read_text(), bbox)
    pipeline_path = ROOT / "config/pipeline.yaml"
    pipeline = read_yaml(pipeline_path)
    catalog_path = ROOT / "data/catalog/earth_sites.geojson"
    catalog = json.loads(catalog_path.read_text())
    sources = load_manifest(ROOT / "data/metadata/sources.csv")
    now = datetime.now(timezone.utc).isoformat()
    accepted = []
    for proposal in proposals:
        if len(accepted) >= max_tiles:
            break
        tile = proposal["tile"]
        source_id, site_id = f"ARCTICDEM_{tile}_32M", f"earth_arctic_{tile}"
        profile_id, roi_id = f"{site_id}_60km_v1", f"{site_id}_roi_60km_v1"
        metadata_url = proposal["source_url"].replace("_dem.tif", ".json")
        label = raw / f"{tile}_32m_v4.1.json"
        obtain(metadata_url, label, limit=2_000_000)
        item = json.loads(label.read_text())
        # This threshold selects source coverage, never terrain similarity.
        if item["properties"].get("pgc:data_perc", 0) < 0.9:
            continue
        image = raw / f"{tile}_32m_v4.1_dem.tif"
        obtain(proposal["source_url"], image, limit=100_000_000)
        with rasterio.open(image) as dataset:
            if dataset.crs != rasterio.crs.CRS.from_epsg(3413) or dataset.res != (32, 32):
                raise ValueError("ArcticDEM source grid differs from the expected 32 m EPSG:3413")
            source_crs, nodata = dataset.crs.to_wkt(), dataset.nodata
        mask_tif = raw / f"{tile}_32m_v4.1_datamask.tif"
        obtain(item["assets"]["datamask"]["href"], mask_tif, limit=20_000_000)
        mask_binary = raw / f"{tile}_32m_v4.1_datamask_uint8.bin"
        with rasterio.open(mask_tif) as mask_ds, rasterio.open(image) as dem_ds:
            if (
                mask_ds.shape != dem_ds.shape
                or mask_ds.transform != dem_ds.transform
                or mask_ds.crs != dem_ds.crs
            ):
                raise ValueError("ArcticDEM source mask is not aligned with elevation")
            mask_values = mask_ds.read(1)
            import numpy as np

            if not np.isin(mask_values, [0, 1]).all():
                raise ValueError("Unexpected ArcticDEM datamask classes")
            mask_binary.write_bytes(mask_values.astype("uint8").tobytes())
        lat, lon = proposal["latitude"], proposal["longitude"]
        crs = f"+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m +type=crs"
        bounds = [-30000, -30000, 30000, 30000]
        notes = (
            "Systematic ArcticDEM v4.1 source-tile midpoint selected inside search box "
            f"{bbox} before computing terrain scores. Source coverage >=90%; ROI QA "
            "is assessed independently. WGS84 ellipsoidal metre surface heights may "
            "include snow/ice. Novelty and field suitability unreviewed. "
            "PGC datamask retains only original SETSM values (1); filled/merged "
            "and water-flattened values (0) are excluded. This is not a bare-rock mask. "
            "Credit Porter et al., ArcticDEM mosaics v4.1 and PGC; DOI 10.7910/DVN/3VDC4W."
        )
        record = SourceRecord(
            source_id=source_id,
            provider="PGC",
            dataset="ArcticDEM",
            version="4.1",
            product_url=metadata_url,
            download_url=proposal["source_url"],
            accessed_utc=now,
            doi="10.7910/DVN/3VDC4W",
            license_or_rights="CC-BY-4.0; credit Porter et al. and PGC",
            checksum_sha256=sha256_file(image),
            planetary_body="Earth",
            horizontal_datum="WGS84",
            vertical_datum="WGS84 ellipsoid",
            pixel_size_m=32,
            processing_version=pipeline["processing_version"],
            roi_id=roi_id,
            processing_notes=notes,
        )
        if source_id in sources and sources[source_id].checksum_sha256 != record.checksum_sha256:
            raise ValueError("Registered ArcticDEM source changed")
        sources.setdefault(source_id, record)
        supporting = {}
        for suffix, path in (("DATAMASK", mask_tif), ("MASK_UINT8", mask_binary)):
            mask_id = f"{source_id}_{suffix}"
            mask_record = SourceRecord.model_validate(
                {
                    **record.model_dump(mode="json"),
                    "source_id": mask_id,
                    "dataset": "ArcticDEM_datamask",
                    "download_url": item["assets"]["datamask"]["href"],
                    "checksum_sha256": sha256_file(path),
                    "processing_notes": "PGC original SETSM datamask: 1=retain, 0=exclude. "
                    + (
                        "Decoded as row-major uint8 with unchanged values and source alignment. "
                        if suffix == "MASK_UINT8"
                        else "Original mask GeoTIFF. "
                    )
                    + notes,
                }
            )
            sources[mask_id] = mask_record
            supporting[mask_id] = path.relative_to(ROOT).as_posix()
        sidecar = ROOT / f"data/metadata/interpretations/{site_id}.yaml"
        sidecar.write_text(
            yaml.safe_dump(
                dict(
                    body="Earth",
                    product_type="topographic_elevation",
                    source_crs=source_crs,
                    horizontal_datum="WGS84",
                    vertical_datum="WGS84 ellipsoid",
                    latitude_type="geodetic",
                    longitude_convention="-180_180",
                    sample_unit="m",
                    scale=1,
                    offset=0,
                    nodata=nodata,
                    latitude_bounds_deg=[50, 90],
                    label_path="../../" + label.relative_to(ROOT / "data").as_posix(),
                    label_sha256=sha256_file(label),
                    mask_path="../../" + mask_binary.relative_to(ROOT / "data").as_posix(),
                    mask_sha256=sha256_file(mask_binary),
                    mask_land_value=1,
                    interpretation_evidence=notes,
                ),
                sort_keys=False,
            ),
            encoding="utf-8",
        )
        name = f"ArcticDEM search candidate {tile}"
        existing_job = next(
            (j for j in pipeline["jobs"] if j["identity"]["profile_id"] == profile_id), None
        )
        if existing_job is not None:
            existing_job["supporting_files"] = supporting
            existing_job["warnings"] = [
                "Only original SETSM data retained; snow/ice may remain. "
                "Novelty and suitability unreviewed."
            ]
        if existing_job is None:
            pipeline["jobs"].append(
                dict(
                    raster_path=image.relative_to(ROOT).as_posix(),
                    interpretation_path=sidecar.relative_to(ROOT).as_posix(),
                    source_id=source_id,
                    supporting_files=supporting,
                    destination_crs=crs,
                    bounds_m=bounds,
                    identity=dict(
                        profile_id=profile_id,
                        roi_id=roi_id,
                        region_name=name,
                        site_id=site_id,
                        site_name=name,
                        country="Canadian Arctic"
                        if -100 <= lon <= -80 and 72 <= lat <= 78
                        else "Arctic region; jurisdiction unverified",
                        centroid_lat=lat,
                        centroid_lon=lon,
                    ),
                    warnings=[
                        "Surface model may include snow/ice. Novelty and suitability unreviewed."
                    ],
                )
            )
            catalog["features"].append(
                dict(
                    type="Feature",
                    geometry=dict(
                        type="Polygon", coordinates=[geographic_ring(crs, "Earth", bounds)]
                    ),
                    properties=dict(
                        site_id=site_id,
                        site_name=name,
                        country="Canadian Arctic"
                        if -100 <= lon <= -80 and 72 <= lat <= 78
                        else "Arctic region; jurisdiction unverified",
                        roi_id=roi_id,
                        seed_or_candidate="systematic_candidate",
                        centroid_lat=lat,
                        centroid_lon=lon,
                        reason_selected=notes,
                        analysis_crs=crs,
                        analysis_bounds_m=bounds,
                        area_km2=3600,
                        known_analog_reference="",
                        geolocation_source=metadata_url,
                    ),
                )
            )
        accepted.append(dict(**proposal, profile_id=profile_id))
        print(f"Registered systematic candidate {tile}", flush=True)
    pipeline_path.write_text(yaml.safe_dump(pipeline, sort_keys=False), encoding="utf-8")
    catalog_path.write_text(json.dumps(catalog, indent=2) + "\n", encoding="utf-8")
    with (ROOT / "data/metadata/sources.csv").open("w", encoding="utf-8", newline="") as stream:
        records = [s.model_dump(mode="json") for s in sources.values()]
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    report = dict(
        searched_utc=now,
        bbox=bbox,
        source_index_sha256=sha256_file(index),
        source="ArcticDEM v4.1 32 m",
        proposed_tile_count=len(proposals),
        registered=accepted,
        novelty="Unreviewed; systematic candidate discovery is not literature novelty proof",
        max_downloads=max_tiles,
        coverage_threshold=0.9,
    )
    (ROOT / "data/metadata/discovery_report.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bbox",
        nargs=4,
        type=float,
        default=[-100, 72, -80, 78],
        metavar=("WEST", "SOUTH", "EAST", "NORTH"),
    )
    parser.add_argument("--max-tiles", type=int, default=3)
    args = parser.parse_args()
    discover(args.bbox, args.max_tiles)
