"""Register the first real Mars/Earth slice from the user's existing downloads.

Downloads authoritative metadata and verifies the Mars image against the archive.
Never rewrites the original rasters. Regions are fixed before scores are computed.
"""

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone

import requests
import yaml

from terratwin.config import ROOT, read_yaml
from terratwin.geo.regions import geographic_ring
from terratwin.ingest.manifest import sha256_file
from terratwin.models import SourceRecord

MOLA = "https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/meg128/"
CMR = "https://cmr.earthdata.nasa.gov/search/concepts/G2816846943-LPCLOUD.umm_json"
JEZERO = "https://planetarynames.wr.usgs.gov/Feature/14300"
GUIDE = "https://lpdaac.usgs.gov/documents/1318/NASADEM_User_Guide_V12.pdf"


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def obtain(session, url, path):
    if not path.exists():
        response = session.get(url, timeout=(15, 60))
        response.raise_for_status()
        path.write_bytes(response.content)
    return sha256_file(path)


def prepare(verify_remote_mars=True):
    raw = ROOT / "data/raw"
    metadata_dir = ROOT / "data/metadata"
    evidence = metadata_dir / "evidence"
    interpretations = metadata_dir / "interpretations"
    evidence.mkdir(exist_ok=True)
    interpretations.mkdir(exist_ok=True)
    mars_image = raw / "Mars/megt44n000hb.img"
    mars_xml = raw / "Mars/megt44n000hb.xml"
    earth = raw / "Earth/NASADEM_HGT_s01w047"
    expected = {
        mars_image: "14022166079edafc99650f354e5a634e6eb2c2ea544b444c01cd8ee55437df36",
        mars_xml: "f6de640ed5603eb03395616214c9a5707c9d49273f699d2cbeec53e93df6bd08",
        earth / "n36w117.hgt": "31395a35998dd9787daa3cbd8f501b42ee74f7609bd361c202eeb0cdb220f442",
        earth / "n36w117.swb": "b32defe6d14e5fe87a10d6d3a63fec34d5160b921f1ad9a0ef8549db75dc7364",
        earth / "n36w117.num": "121ca398c6d1a459e1a4cba480b88f8a8822088909235b13066f2884c34a3d2a",
    }
    for path, digest in expected.items():
        if sha256_file(path) != digest:
            raise ValueError(f"File changed since the inspected download: {path.name}")
    pipeline_path = ROOT / "config/pipeline.yaml"
    current_jobs = read_yaml(pipeline_path).get("jobs", [])
    allowed = {"mars_jezero_60km_v1", "earth_n36w117_60km_v1"}
    if any(job["identity"]["profile_id"] not in allowed for job in current_jobs):
        raise ValueError("Refusing to replace a pipeline containing other study profiles")
    now = datetime.now(timezone.utc).isoformat()
    session = requests.Session()
    evidence_paths = {
        "mars_original_xml": (MOLA + "megt44n000hb.xml", evidence / "megt44n000hb.xml"),
        "nasadem_granule": (CMR, evidence / "NASADEM_HGT_n36w117.umm.json"),
        "nasadem_guide": (GUIDE, evidence / "NASADEM_User_Guide_V12.pdf"),
    }
    retrieved = {}
    for key, (url, path) in evidence_paths.items():
        print(f"Checking metadata: {key}", flush=True)
        digest = obtain(session, url, path)
        retrieved[key] = {"url": url, "local_path": str(path.relative_to(ROOT)), "sha256": digest}
    location_path = evidence / "jezero_location.json"
    save_json(
        location_path,
        {
            "source_url": JEZERO,
            "feature_id": 14300,
            "feature_name": "Jezero",
            "center_latitude_deg": 18.41,
            "center_longitude_deg": 77.69,
            "coordinate_system": "Planetocentric, positive East, 0-360",
            "verified_utc": now,
            "evidence_type": "Structured transcription of the USGS/IAU Gazetteer page "
            "checked with web research",
        },
    )
    retrieved["jezero_location"] = {
        "url": JEZERO,
        "local_path": str(location_path.relative_to(ROOT)),
        "sha256": sha256_file(location_path),
    }
    if sha256_file(evidence_paths["mars_original_xml"][1]) != expected[mars_xml]:
        raise ValueError("Local Mars XML differs from the currently served archive label")
    earth_metadata = json.loads(evidence_paths["nasadem_granule"][1].read_text())
    umm = earth_metadata.get("umm", earth_metadata)
    if umm["GranuleUR"] != "NASADEM_HGT_n36w117":
        raise ValueError("Unexpected Earth granule metadata")
    if umm["CollectionReference"] != {"ShortName": "NASADEM_HGT", "Version": "001"}:
        raise ValueError("Unexpected NASADEM collection/version")
    zip_url = next(url["URL"] for url in umm["RelatedUrls"] if url["Type"] == "GET DATA")
    remote_path = evidence / "mars_image_integrity.json"
    remote = json.loads(remote_path.read_text()) if remote_path.exists() else {}
    if verify_remote_mars and remote.get("sha256") != expected[mars_image]:
        print("Verifying the complete Mars raster against the PDS archive...", flush=True)
        digest = hashlib.sha256()
        size = 0
        with session.get(MOLA + mars_image.name, stream=True, timeout=(15, 60)) as response:
            response.raise_for_status()
            for block in response.iter_content(1024 * 1024):
                size += len(block)
                if size > 150_000_000:
                    raise ValueError("Unexpected oversized Mars response")
                digest.update(block)
        if size != mars_image.stat().st_size or digest.hexdigest() != expected[mars_image]:
            raise ValueError("Mars archive image does not match local bytes")
        remote = {
            "url": MOLA + mars_image.name,
            "sha256": digest.hexdigest(),
            "byte_count": size,
            "verified_utc": now,
            "full_byte_comparison": True,
        }
        save_json(remote_path, remote)
    mars_roi, earth_roi = "mars_jezero_roi_60km_v1", "earth_n36w117_roi_60km_v1"
    mars_crs = "+proj=aeqd +lat_0=18.41 +lon_0=77.69 +R=3396000 +units=m +type=crs"
    earth_crs = "+proj=aeqd +lat_0=36.5 +lon_0=-116.5 +datum=WGS84 +units=m +type=crs"
    bounds = [-30000, -30000, 30000, 30000]
    mars_notes = (
        "MOLA PDS4 SignedMSB2 metre topography; scale 1, offset 0; radius 3396000 m. "
        "XML declares no special missing constant; zero is valid elevation. "
        "Interpolated bins are present: nonmissing coverage is not direct-shot coverage."
    )
    earth_notes = (
        "NASADEM user guide v1.2 Table 1: HGT big-endian signed int16 metres relative to EGM96; "
        "WGS84 one-arc-second posts. SWB uint8 0=land, 255=water. "
        "Earth ROI is centered at the documented n36w117 tile midpoint before scoring."
    )
    common = dict(
        product_type="topographic_elevation",
        sample_unit="m",
        scale=1,
        offset=0,
        longitude_convention="-180_180",
        mask_land_value=0,
    )
    import rasterio

    with rasterio.open(mars_xml) as dataset:
        mars_source_crs = dataset.crs.to_wkt()
    mars_interpretation = {
        **common,
        "body": "Mars",
        "source_crs": mars_source_crs,
        "horizontal_datum": "IAU2000 planetocentric; sphere R=3396000 m",
        "vertical_datum": "GMM3 (mgm1025) areoid, degree/order 50",
        "latitude_type": "planetocentric",
        "longitude_convention": "0_360",
        "nodata": None,
        "raster_data_path": "../../raw/Mars/megt44n000hb.img",
        "label_path": "../../raw/Mars/megt44n000hb.xml",
        "label_sha256": expected[mars_xml],
        "interpretation_evidence": mars_notes,
    }
    earth_interpretation = {
        **common,
        "body": "Earth",
        "source_crs": "EPSG:4326",
        "horizontal_datum": "WGS84",
        "vertical_datum": "EGM96 geoid",
        "latitude_type": "geodetic",
        "nodata": -32768,
        "label_path": "../evidence/NASADEM_HGT_n36w117.umm.json",
        "label_sha256": retrieved["nasadem_granule"]["sha256"],
        "mask_path": "../../raw/Earth/NASADEM_HGT_s01w047/n36w117.swb",
        "mask_sha256": expected[earth / "n36w117.swb"],
        "interpretation_evidence": earth_notes,
    }
    for filename, metadata in [
        ("mars_jezero.yaml", mars_interpretation),
        ("earth_n36w117.yaml", earth_interpretation),
    ]:
        (interpretations / filename).write_text(
            yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8"
        )
    uncertain = (
        "User-supplied extracted files; original download time unknown. accessed_utc is this "
        "metadata verification time. Publisher checksum for original ZIP not available in CMR; "
        "extracted bytes locally checksummed, not independently matched against publisher archive."
    )
    records = [
        SourceRecord(
            source_id="MOLA_MEGT44N000HB",
            provider="NASA PDS Geosciences / MOLA team",
            dataset="MOLA_MEGDR",
            version="2.0 (PDS3); 1.0 (PDS4)",
            product_url=MOLA + "megt44n000hb.xml",
            download_url=MOLA + mars_image.name,
            accessed_utc=now,
            license_or_rights="PDS public-domain data; attribute MOLA team. "
            "https://pds-geosciences.wustl.edu/faq.html",
            checksum_sha256=expected[mars_image],
            planetary_body="Mars",
            horizontal_datum=mars_interpretation["horizontal_datum"],
            vertical_datum=mars_interpretation["vertical_datum"],
            pixel_size_m=463.0576672,
            processing_version="terrain_v1",
            roi_id=mars_roi,
            processing_notes=mars_notes
            + " Original user download time unknown; archive verification "
            f"at {now}; full archive hash verified={remote.get('full_byte_comparison', False)}.",
        )
    ]
    for extension in ("hgt", "swb", "num"):
        records.append(
            SourceRecord(
                source_id=f"NASADEM_N36W117_{extension.upper()}",
                provider="NASA LP DAAC",
                dataset="NASADEM_HGT",
                version="001",
                doi="10.5067/MEaSUREs/NASADEM/NASADEM_HGT.001",
                product_url=CMR,
                download_url=zip_url,
                accessed_utc=now,
                license_or_rights="NASA/USGS open data; credit NASA JPL and LP DAAC. "
                "https://www.usgs.gov/centers/eros/data-citation",
                checksum_sha256=expected[earth / f"n36w117.{extension}"],
                planetary_body="Earth",
                horizontal_datum="WGS84",
                vertical_datum="EGM96 geoid",
                pixel_size_m=30.9,
                processing_version="terrain_v1",
                roi_id=earth_roi,
                processing_notes=f"Member n36w117.{extension} of NASADEM_HGT_n36w117.zip. "
                + uncertain
                + (
                    " 30.9 m is approximate north-south native post spacing; "
                    "actual metre spacing is checked from the georeference."
                ),
            )
        )
    with (metadata_dir / "sources.csv").open("w", encoding="utf-8", newline="") as stream:
        rows = [record.model_dump(mode="json") for record in records]
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    catalog_path = ROOT / "data/catalog/earth_sites.geojson"
    existing = json.loads(catalog_path.read_text())
    if any(feature["properties"]["site_id"] != "earth_n36w117" for feature in existing["features"]):
        raise ValueError("Refusing to replace other Earth catalog regions")
    save_json(
        catalog_path,
        {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [geographic_ring(earth_crs, "Earth", bounds)],
                    },
                    "properties": dict(
                        site_id="earth_n36w117",
                        site_name="Death Valley-area tile-centered ROI",
                        country="United States",
                        roi_id=earth_roi,
                        seed_or_candidate="exploratory",
                        centroid_lon=-116.5,
                        centroid_lat=36.5,
                        reason_selected="Centered on available NASADEM tile before scoring; "
                        "availability-selected exploratory region, no novelty claim.",
                        known_analog_reference="",
                        analysis_crs=earth_crs,
                        analysis_bounds_m=bounds,
                        area_km2=3600,
                        geolocation_source=CMR,
                    ),
                }
            ],
        },
    )
    save_json(
        ROOT / "data/catalog/planetary_rois.json",
        {
            "coordinate_system": "Mars planetocentric positive-East 0-360, NOT Earth GeoJSON",
            "regions": [
                {
                    "profile_id": "mars_jezero_60km_v1",
                    "roi_id": mars_roi,
                    "center_lat": 18.41,
                    "center_lon": 77.69,
                    "geolocation_source": JEZERO,
                    "analysis_crs": mars_crs,
                    "bounds_m": bounds,
                    "area_km2": 3600,
                    "body_geographic_ring": geographic_ring(mars_crs, "Mars", bounds),
                }
            ],
        },
    )
    pipeline = dict(
        processing_version="terrain_v1",
        features_version="features_v1",
        common_grid_m=1000.0,
        roi_size_km=60.0,
        roughness_kernel_cells=3,
        minimum_valid_cell_fraction=0.90,
        jobs=[
            dict(
                raster_path="data/raw/Mars/megt44n000hb.xml",
                interpretation_path="data/metadata/interpretations/mars_jezero.yaml",
                source_id="MOLA_MEGT44N000HB",
                destination_crs=mars_crs,
                bounds_m=bounds,
                identity=dict(
                    profile_id="mars_jezero_60km_v1",
                    region_name="Jezero crater 60 km study ROI",
                    roi_id=mars_roi,
                ),
                warnings=[
                    "MOLA includes interpolated bins; raster validity is not direct-shot coverage."
                ],
            ),
            dict(
                raster_path="data/raw/Earth/NASADEM_HGT_s01w047/n36w117.hgt",
                interpretation_path="data/metadata/interpretations/earth_n36w117.yaml",
                source_id="NASADEM_N36W117_HGT",
                destination_crs=earth_crs,
                bounds_m=bounds,
                supporting_files={
                    f"NASADEM_N36W117_{ext.upper()}": (earth / f"n36w117.{ext}")
                    .relative_to(ROOT)
                    .as_posix()
                    for ext in ("swb", "num")
                },
                identity=dict(
                    profile_id="earth_n36w117_60km_v1",
                    roi_id=earth_roi,
                    region_name="Death Valley-area tile-centered ROI",
                    site_id="earth_n36w117",
                    site_name="Death Valley-area tile-centered ROI",
                    country="United States",
                    centroid_lat=36.5,
                    centroid_lon=-116.5,
                ),
                warnings=[
                    "Single availability-selected candidate; "
                    "rank 1 does not establish superiority.",
                    "Original Earth ZIP publisher checksum not independently verified.",
                ],
            ),
        ],
    )
    pipeline_path.write_text(yaml.safe_dump(pipeline, sort_keys=False), encoding="utf-8")
    targets = read_yaml(ROOT / "config/targets.yaml")
    targets["targets"][0].update(
        profile_id="mars_jezero_60km_v1",
        region_name="Jezero crater 60 km study ROI",
        processing_status="configured_for_preparation",
        center_lat=18.41,
        center_lon=77.69,
        geolocation_source=JEZERO,
    )
    (ROOT / "config/targets.yaml").write_text(
        yaml.safe_dump(targets, sort_keys=False), encoding="utf-8"
    )
    save_json(
        evidence / "registration.json",
        {
            "metadata_accessed_utc": now,
            "original_user_download_utc": None,
            "selection_rule": "Jezero Gazetteer center; Earth tile midpoint; fixed before scoring",
            "evidence": retrieved,
            "mars_integrity": remote,
            "earth_integrity": "Local hashes and provider granule identity/extent; "
            "publisher ZIP hash unverified",
        },
    )
    print("Registered two real study ROIs and four source members. Run scripts/build_profiles.py.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-remote-mars",
        action="store_true",
        help="Skip full remote Mars byte verification (reported as unverified)",
    )
    args = parser.parse_args()
    prepare(not args.skip_remote_mars)
