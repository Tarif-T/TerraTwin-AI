"""Plan, acquire and register distinct Earth regions without inventing profiles.

Default: verify/cache public CMR metadata and write a download checklist.
--download: retrieve missing ZIPs using existing Earthdata .netrc credentials.
Alternatively place browser-downloaded ZIPs in data/raw/Earth/NASADEM_archives/.
--register: validate ZIPs or extracted HGT/SWB/NUM files and append sources/ROIs/jobs.
--build: rebuild and independently validate rankings after registration.
"""

import argparse
import copy
import csv
import json
import subprocess
import sys
from datetime import datetime, timezone

import requests
import yaml

from terratwin.config import ROOT, read_yaml
from terratwin.ingest.earth_catalog import (
    CMR_CONCEPT,
    download_archive,
    extract_archive,
    retrieve_metadata,
    validate_extracted,
    validate_metadata,
)
from terratwin.ingest.manifest import load_manifest, sha256_file
from terratwin.models import SourceRecord


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def register(candidate, item, members, archive, pipeline, catalog, sources, directory=None):
    tile = candidate["tile"]
    url, lat, lon, crs, ring = validate_metadata(item, tile)
    site_id, roi_id = f"earth_{tile}", f"earth_{tile}_roi_60km_v1"
    profile_id = f"earth_{tile}_60km_v1"
    existing = [j for j in pipeline["jobs"] if j["identity"]["profile_id"] == profile_id]
    if existing:
        # Never silently replace an existing study definition or its provenance.
        for ext, digest in members.items():
            if sources[f"NASADEM_{tile.upper()}_{ext.upper()}"].checksum_sha256 != digest:
                raise ValueError(f"Registered member checksum changed for {tile}")
        return
    if any(f["properties"]["site_id"] == site_id for f in catalog["features"]):
        raise ValueError(f"Catalog/job conflict for {site_id}")
    now = datetime.now(timezone.utc).isoformat()
    evidence = ROOT / f"data/metadata/evidence/NASADEM_HGT_{tile}.umm.json"
    product_url = CMR_CONCEPT + item["meta"]["concept-id"] + ".umm_json"
    integrity = (
        f"Archive SHA256 {sha256_file(archive)}; ZIP member CRC verified. "
        if archive is not None
        else "User-supplied extracted members; original ZIP unavailable, ZIP CRC unverified. "
    )
    notes = (
        "Exploratory tile-centered ROI selected before scoring; geology unassessed. "
        + integrity
        + "Local checksums are not independently published NASA checksums. "
        "Original retrieval time may be unknown for manually supplied files; "
        "accessed_utc records verification time."
    )
    directory = directory or ROOT / f"data/raw/Earth/NASADEM_HGT_{tile}"
    for ext, digest in members.items():
        source_id = f"NASADEM_{tile.upper()}_{ext.upper()}"
        if source_id in sources:
            raise ValueError(f"Source ID already registered without matching job: {source_id}")
        sources[source_id] = SourceRecord(
            source_id=source_id,
            provider="NASA LP DAAC",
            dataset="NASADEM_HGT",
            version="001",
            doi="10.5067/MEaSUREs/NASADEM/NASADEM_HGT.001",
            product_url=product_url,
            download_url=url,
            accessed_utc=now,
            license_or_rights="NASA/USGS open data; credit NASA JPL and LP DAAC. "
            "https://www.usgs.gov/centers/eros/data-citation",
            checksum_sha256=digest,
            planetary_body="Earth",
            horizontal_datum="WGS84",
            vertical_datum="EGM96 geoid",
            pixel_size_m=30.9,
            processing_version="terrain_v1",
            roi_id=roi_id,
            processing_notes=notes + " Native post spacing varies with latitude.",
        )
    interpretation = copy.deepcopy(
        read_yaml(ROOT / "data/metadata/interpretations/earth_n36w117.yaml")
    )
    interpretation.update(
        label_path=f"../evidence/{evidence.name}",
        label_sha256=sha256_file(evidence),
        mask_path="../../" + (directory / f"{tile}.swb").relative_to(ROOT / "data").as_posix(),
        mask_sha256=members["swb"],
        interpretation_evidence=(
            "NASADEM user guide Table 1: HGT big-endian int16 EGM96 metres, "
            "WGS84 1 arcsecond posts; SWB uint8 0=land, 255=water. " + notes
        ),
    )
    sidecar = ROOT / f"data/metadata/interpretations/earth_{tile}.yaml"
    sidecar.write_text(yaml.safe_dump(interpretation, sort_keys=False), encoding="utf-8")
    identity = dict(
        profile_id=profile_id,
        roi_id=roi_id,
        region_name=candidate["region"],
        site_id=site_id,
        site_name=candidate["region"],
        country=candidate["country"],
        centroid_lat=lat,
        centroid_lon=lon,
    )
    pipeline["jobs"].append(
        dict(
            raster_path=(directory / f"{tile}.hgt").relative_to(ROOT).as_posix(),
            interpretation_path=sidecar.relative_to(ROOT).as_posix(),
            source_id=f"NASADEM_{tile.upper()}_HGT",
            destination_crs=crs,
            bounds_m=[-30000, -30000, 30000, 30000],
            identity=identity,
            supporting_files={
                f"NASADEM_{tile.upper()}_{ext.upper()}": (directory / f"{tile}.{ext}")
                .relative_to(ROOT)
                .as_posix()
                for ext in ("swb", "num")
            },
            warnings=[
                "Exploratory regional candidate; scientific analog suitability unvalidated.",
                "Publisher checksum not independently verified.",
            ],
        )
    )
    catalog["features"].append(
        dict(
            type="Feature",
            geometry=dict(type="Polygon", coordinates=[ring]),
            properties=dict(
                site_id=site_id,
                site_name=candidate["region"],
                country=candidate["country"],
                roi_id=roi_id,
                seed_or_candidate="exploratory",
                centroid_lat=lat,
                centroid_lon=lon,
                reason_selected=read_yaml(ROOT / "config/earth_candidates.yaml")[
                    "selection_rationale"
                ],
                known_analog_reference="",
                analysis_crs=crs,
                analysis_bounds_m=[-30000, -30000, 30000, 30000],
                area_km2=3600,
                geolocation_source=product_url,
            ),
        )
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args()
    if args.build and not args.register:
        parser.error("--build requires --register")
    candidates = read_yaml(ROOT / "config/earth_candidates.yaml")["candidates"]
    if len({c["tile"] for c in candidates}) != len(candidates):
        raise ValueError("Duplicate candidate tile")
    pipeline_path = ROOT / "config/pipeline.yaml"
    catalog_path = ROOT / "data/catalog/earth_sites.geojson"
    pipeline = read_yaml(pipeline_path)
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    sources = load_manifest(ROOT / "data/metadata/sources.csv")
    archive_dir = ROOT / "data/raw/Earth/NASADEM_archives"
    archive_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    rows, auth_blocked = [], False
    for candidate in candidates:
        tile = candidate["tile"]
        path = ROOT / f"data/metadata/evidence/NASADEM_HGT_{tile}.umm.json"
        if path.exists():
            item = json.loads(path.read_text(encoding="utf-8"))
        else:
            item = retrieve_metadata(session, tile)
            write_json(path, item)
        url, lat, lon, _, _ = validate_metadata(item, tile)
        archive = archive_dir / f"NASADEM_HGT_{tile}.zip"
        extracted = next(
            (
                directory
                for directory in (archive_dir, ROOT / f"data/raw/Earth/NASADEM_HGT_{tile}")
                if any((directory / f"{tile}.{ext}").exists() for ext in ("hgt", "swb", "num"))
            ),
            None,
        )
        row = {
            **candidate,
            "latitude": lat,
            "longitude": lon,
            "download_url": url,
            "metadata_url": CMR_CONCEPT + item["meta"]["concept-id"] + ".umm_json",
            "status": "awaiting_download",
        }
        if args.download and not archive.exists() and extracted is None and not auth_blocked:
            try:
                download_archive(session, url, archive)
            except PermissionError:
                auth_blocked = True
                print("Earthdata sign-in required; no credentials printed or stored.", flush=True)
        if archive.exists():
            extracted = ROOT / f"data/raw/Earth/NASADEM_HGT_{tile}"
            extract_archive(archive, extracted, tile)
            members = validate_extracted(extracted, tile)
            row.update(status="archive_verified", archive_sha256=sha256_file(archive))
        elif extracted is not None:
            members = validate_extracted(extracted, tile)
            row.update(status="extracted_members_verified", zip_crc_verified=False)
        if extracted is not None:
            row["member_sha256"] = members
            if args.register:
                register(
                    candidate,
                    item,
                    members,
                    archive if archive.exists() else None,
                    pipeline,
                    catalog,
                    sources,
                    directory=extracted,
                )
                row["status"] = "registered_pending_build"
        rows.append(row)
        print(f"{tile}: {row['status']}", flush=True)
    if args.register:
        if len([j for j in pipeline["jobs"] if "site_id" in j["identity"]]) > 1:
            for job in pipeline["jobs"]:
                job["warnings"] = [
                    w
                    for w in job.get("warnings", [])
                    if not w.startswith("Single availability-selected candidate")
                ]
        pipeline_path.write_text(yaml.safe_dump(pipeline, sort_keys=False), encoding="utf-8")
        write_json(catalog_path, catalog)
        with (ROOT / "data/metadata/sources.csv").open("w", encoding="utf-8", newline="") as stream:
            records = [s.model_dump(mode="json") for s in sources.values()]
            writer = csv.DictWriter(stream, fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
    write_json(
        ROOT / "data/metadata/earth_acquisition_status.json",
        dict(
            checked_utc=datetime.now(timezone.utc).isoformat(),
            selection_config="config/earth_candidates.yaml",
            candidates=rows,
            authentication_blocked=auth_blocked,
            note="Metadata or registration alone does not mean a profile passed terrain QA.",
        ),
    )
    if args.build:
        for script in ("build_profiles.py", "validate_real_slice.py"):
            subprocess.run([sys.executable, str(ROOT / "scripts" / script)], check=True, cwd=ROOT)
        from terratwin.datasets import load_prepared

        _, prepared, _ = load_prepared()
        by_id = {profile.site_id: profile for profile in prepared}
        for row in rows:
            profile = by_id.get(f"earth_{row['tile']}")
            if profile is not None:
                row.update(
                    status="profile_prepared",
                    qa_pass=profile.qa_pass,
                    valid_cell_fraction=profile.valid_cell_fraction,
                )
        write_json(
            ROOT / "data/metadata/earth_acquisition_status.json",
            dict(
                checked_utc=datetime.now(timezone.utc).isoformat(),
                selection_config="config/earth_candidates.yaml",
                candidates=rows,
                authentication_blocked=auth_blocked,
                note="Prepared from real source members; QA status and coverage recorded per site.",
            ),
        )


if __name__ == "__main__":
    main()
