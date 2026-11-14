"""Register public LOLA polar and REMA data at fixed, documented study footprints.

Original damaged ldem_64.img is preserved. Acquisitions are cached and bounded.
Run build_profiles.py and validate_real_slice.py after registration.
"""

import csv
import json
from datetime import datetime, timezone

import rasterio
import requests
import yaml
from pyproj import Transformer

from terratwin.config import ROOT, read_yaml
from terratwin.geo.regions import geographic_ring
from terratwin.ingest.manifest import load_manifest, sha256_file
from terratwin.models import SourceRecord

LOLA = (
    "https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/polar/img/"
)
REMA = "https://pgc-opendata-dems.s3.us-west-2.amazonaws.com/rema/mosaics/v2.0/32m/18_35/"


def obtain(url, path, limit=150_000_000):
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(path.suffix + ".part")
    try:
        with requests.get(url, stream=True, timeout=(15, 60)) as response:
            response.raise_for_status()
            with partial.open("wb") as stream:
                size = 0
                for block in response.iter_content(1024 * 1024):
                    size += len(block)
                    if size > limit:
                        raise ValueError("Source exceeded the expected acquisition bound")
                    stream.write(block)
        partial.replace(path)
    finally:
        partial.unlink(missing_ok=True)


def prepare():
    sources = load_manifest(ROOT / "data/metadata/sources.csv")
    pipeline = read_yaml(ROOT / "config/pipeline.yaml")
    catalog_path = ROOT / "data/catalog/earth_sites.geojson"
    catalog = json.loads(catalog_path.read_text())
    planetary_path = ROOT / "data/catalog/planetary_rois.json"
    planetary = json.loads(planetary_path.read_text())
    now = datetime.now(timezone.utc).isoformat()
    bounds = [-30000, -30000, 30000, 30000]
    for body, dataset, stem, base, folder, center, region in [
        (
            "Moon",
            "LOLA_GDR",
            "ldem_875s_20m",
            LOLA,
            "Moon/LOLA_polar",
            (-89.67, 129.78),
            "Shackleton south-pole 60 km terrain study",
        ),
        (
            "Earth",
            "REMA",
            "18_35_32m_v2.0",
            REMA,
            "Earth/REMA_18_35",
            None,
            "Antarctic REMA 18_35 tile-centered polar ROI",
        ),
    ]:
        raw = ROOT / "data/raw" / folder
        if body == "Moon":
            image, label = raw / f"{stem}.img", raw / f"{stem}.xml"
            for ext in ("xml", "lbl", "img"):
                obtain(base + stem + "." + ext, raw / (stem + "." + ext))
            if image.stat().st_size != 115034112:
                raise ValueError("LOLA image does not match the declared 7584-square int16 array")
            raster = label
            lat, lon = center
            crs = f"+proj=aeqd +lat_0={lat} +lon_0={lon} +R=1737400 +units=m +type=crs"
            roi_id, profile_id, source_id = (
                "moon_shackleton_roi_60km_v1",
                "moon_shackleton_60km_v1",
                "LOLA_LDEM_875S_20M",
            )
            horizontal, vertical = (
                "DE421 mean Earth/polar axis; sphere R=1737400 m",
                ("Height above 1737400 m lunar reference sphere"),
            )
            notes = (
                "Original LOLA PDS4/PDS3 HEIGHT=DN*0.5; radius offset 1737400 m is "
                "not added to height. Polar stereographic 20 m source. Interpolated "
                "altimetry is not direct-shot coverage. Study center from USGS/IAU "
                "Shackleton feature 5450 (-89.67,129.78); not a designated base site."
            )
            location_url = "https://planetarynames.wr.usgs.gov/Feature/5450"
            identity = dict(profile_id=profile_id, roi_id=roi_id, region_name=region)
        else:
            image, label = raw / f"{stem}_dem.tif", raw / f"{stem}.json"
            obtain(base + label.name, label)
            item = json.loads(label.read_text())
            if item["properties"]["proj:code"] != "EPSG:3031":
                raise ValueError("Unexpected REMA projection")
            obtain(item["assets"]["dem"]["href"], image)
            lat_lon = Transformer.from_crs(3031, 4326, always_xy=True).transform(450000, -1250000)
            lon, lat = lat_lon
            crs = f"+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m +type=crs"
            roi_id, profile_id, source_id = (
                "earth_rema_18_35_roi_60km_v1",
                "earth_rema_18_35_60km_v1",
                "REMA_18_35_32M",
            )
            horizontal, vertical = "WGS84", "WGS84 ellipsoid"
            notes = (
                "REMA v2 mosaic 32 m digital surface model; WGS84 ellipsoidal metre "
                "heights. May include snow/ice surfaces; not an exposed-rock mask. "
                "Center fixed at EPSG:3031 (450000,-1250000), tile midpoint before "
                "scoring. DOI 10.7910/DVN/EBW8UC; credit Howat et al. and PGC."
            )
            location_url, raster = base + label.name, image
            identity = dict(
                profile_id=profile_id,
                roi_id=roi_id,
                region_name=region,
                site_id="earth_rema_18_35",
                site_name=region,
                country="Antarctica",
                centroid_lat=lat,
                centroid_lon=lon,
            )
        with rasterio.open(raster) as ds:
            source_crs, nodata = ds.crs.to_wkt(), ds.nodata
        digest = sha256_file(image)
        if source_id in sources and sources[source_id].checksum_sha256 != digest:
            raise ValueError(f"Registered source changed: {source_id}")
        record = SourceRecord(
            source_id=source_id,
            provider="NASA PDS / LOLA team" if body == "Moon" else "PGC",
            dataset=dataset,
            version="2.0",
            product_url=base + label.name,
            download_url=base + image.name,
            accessed_utc=now,
            doi="" if body == "Moon" else "10.7910/DVN/EBW8UC",
            license_or_rights=(
                "PDS public data; credit LRO LOLA team"
                if body == "Moon"
                else "CC-BY-4.0; cite Howat et al., REMA mosaics v2 and PGC"
            ),
            checksum_sha256=digest,
            planetary_body=body,
            horizontal_datum=horizontal,
            vertical_datum=vertical,
            pixel_size_m=20 if body == "Moon" else 32,
            processing_version=pipeline["processing_version"],
            roi_id=roi_id,
            processing_notes=notes + " Full public file locally SHA256 hashed; no independent "
            "publisher checksum supplied. accessed_utc is acquisition verification time.",
        )
        # Preserve access timestamp and record on repeated registrations.
        sources.setdefault(source_id, record)
        sidecar = ROOT / f"data/metadata/interpretations/{profile_id}.yaml"
        metadata = dict(
            body=body,
            product_type="topographic_elevation",
            sample_unit="m",
            source_crs=source_crs,
            horizontal_datum=horizontal,
            vertical_datum=vertical,
            latitude_type="planetocentric" if body == "Moon" else "geodetic",
            longitude_convention="0_360" if body == "Moon" else "-180_180",
            scale=0.5 if body == "Moon" else 1,
            offset=0,
            nodata=nodata,
            value_interpretation="lola_height" if body == "Moon" else "standard",
            latitude_bounds_deg=[-90, 90] if body == "Moon" else [-90, -60],
            label_path="../../" + label.relative_to(ROOT / "data").as_posix(),
            label_sha256=sha256_file(label),
            interpretation_evidence=notes,
        )
        if body == "Moon":
            metadata["raster_data_path"] = "../../" + image.relative_to(ROOT / "data").as_posix()
        sidecar.write_text(yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8")
        if not any(j["identity"]["profile_id"] == profile_id for j in pipeline["jobs"]):
            pipeline["jobs"].append(
                dict(
                    raster_path=raster.relative_to(ROOT).as_posix(),
                    interpretation_path=sidecar.relative_to(ROOT).as_posix(),
                    source_id=source_id,
                    destination_crs=crs,
                    bounds_m=bounds,
                    identity=identity,
                    warnings=["Scientific analog suitability unvalidated.", notes],
                )
            )
        ring = geographic_ring(crs, body, bounds)
        if body == "Earth" and not any(
            f["properties"]["site_id"] == identity["site_id"] for f in catalog["features"]
        ):
            catalog["features"].append(
                dict(
                    type="Feature",
                    geometry=dict(type="Polygon", coordinates=[ring]),
                    properties=dict(
                        **{
                            k: identity[k]
                            for k in (
                                "site_id",
                                "site_name",
                                "country",
                                "roi_id",
                                "centroid_lat",
                                "centroid_lon",
                            )
                        },
                        seed_or_candidate="exploratory",
                        reason_selected="Pre-score polar tile midpoint; snow/ice included.",
                        analysis_crs=crs,
                        analysis_bounds_m=bounds,
                        area_km2=3600,
                        known_analog_reference="",
                        geolocation_source=location_url,
                    ),
                )
            )
        if body == "Moon" and not any(r["profile_id"] == profile_id for r in planetary["regions"]):
            planetary["regions"].append(
                dict(
                    profile_id=profile_id,
                    roi_id=roi_id,
                    center_lat=lat,
                    center_lon=lon,
                    geolocation_source=location_url,
                    body="Moon",
                    coordinate_system="Moon planetocentric; positive East; NOT WGS84",
                    analysis_crs=crs,
                    bounds_m=bounds,
                    area_km2=3600,
                    body_geographic_ring=ring,
                )
            )
        print(f"Registered {profile_id}", flush=True)
    planetary["coordinate_system"] = "Per-region body-specific coordinates; NOT Earth GeoJSON"
    for path, value in ((catalog_path, catalog), (planetary_path, planetary)):
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    (ROOT / "config/pipeline.yaml").write_text(
        yaml.safe_dump(pipeline, sort_keys=False), encoding="utf-8"
    )
    with (ROOT / "data/metadata/sources.csv").open("w", encoding="utf-8", newline="") as stream:
        rows = [s.model_dump(mode="json") for s in sources.values()]
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    targets = read_yaml(ROOT / "config/targets.yaml")
    targets["targets"][1].update(
        profile_id="moon_shackleton_60km_v1",
        region_name="Shackleton south-pole 60 km terrain study",
        processing_status="configured_for_preparation",
        center_lat=-89.67,
        center_lon=129.78,
        geolocation_source="https://planetarynames.wr.usgs.gov/Feature/5450",
    )
    (ROOT / "config/targets.yaml").write_text(
        yaml.safe_dump(targets, sort_keys=False), encoding="utf-8"
    )


if __name__ == "__main__":
    prepare()
