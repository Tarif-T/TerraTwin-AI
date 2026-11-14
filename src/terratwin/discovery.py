"""Explicit online, bounded discovery jobs; existing catalog files are never replaced."""

import hashlib
import json
import math
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone

import numpy as np
import rasterio
import requests
import yaml
from pydantic import Field, model_validator
from pyproj import Geod
from rasterio.transform import from_origin

from terratwin.config import content_hash
from terratwin.export.csv_export import export_analysis
from terratwin.geo.features import extract_features
from terratwin.geo.quality import quality_reasons
from terratwin.geo.rasters import metric_roi
from terratwin.geo.regions import geographic_ring
from terratwin.ingest.manifest import sha256_file
from terratwin.ingest.raster_input import RasterInterpretation, validate_local_raster
from terratwin.models import Contract, Profile, ScoringConfig, SourceRecord
from terratwin.scoring.engine import rank_candidates

BASE = "https://copernicus-dem-90m.s3.amazonaws.com/"
ATTRIBUTION = (
    "Produced using Copernicus WorldDEM-90 © DLR e.V. 2010-2014 and © Airbus Defence "
    "and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA; "
    "all rights reserved. https://registry.opendata.aws/copernicus-dem/"
)
GEOD = Geod(ellps="WGS84")


class DiscoveryRequest(Contract):
    bbox: tuple[float, float, float, float]
    budget: int = Field(default=12, ge=1, le=30)
    reference: Profile
    scoring: ScoringConfig
    known_centers: list[tuple[float, float]]

    @model_validator(mode="after")
    def valid_search(self):
        w, s, e, n = self.bbox
        if not all(math.isfinite(v) for v in self.bbox) or not (
            -180 <= w < e <= 180 and -40 <= s < n <= 40
        ):
            raise ValueError("Use a non-dateline search box between 40 S and 40 N")
        p = self.reference
        if (
            p.body not in ("Mars", "Moon")
            or not p.qa_pass
            or p.synthetic
            or p.valid_cell_fraction < self.scoring.minimum_valid_cell_fraction
        ):
            raise ValueError("Discovery requires a QA-approved real planetary reference")
        if (p.roi_size_km, p.common_grid_m, p.roughness_kernel_cells) != (60, 1000, 3):
            raise ValueError("Discovery currently supports matched 60 km / 1 km / 3-cell profiles")
        if any(not (-180 <= lon <= 180 and -90 <= lat <= 90) for lon, lat in self.known_centers):
            raise ValueError("Invalid known catalog coordinates")
        return self


def write_json(path, value):
    temporary = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    temporary.replace(path)


def acquire(url, path, limit=12_000_000):
    """Bounded cache with receipts; changed cached bytes fail rather than being trusted."""
    receipt = path.with_suffix(path.suffix + ".receipt.json")
    if path.exists():
        record = json.loads(receipt.read_text(encoding="utf-8"))
        if record["url"] != url or record["sha256"] != sha256_file(path):
            raise ValueError("Cached discovery source changed")
        return record
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{uuid.uuid4().hex}.part")
    try:
        with requests.get(url, stream=True, timeout=(15, 30)) as response:
            response.raise_for_status()
            size, md5 = 0, hashlib.md5()
            with temporary.open("xb") as stream:
                for block in response.iter_content(256 * 1024):
                    size += len(block)
                    if size > limit:
                        raise ValueError("Discovery asset exceeded download limit")
                    md5.update(block)
                    stream.write(block)
            etag = response.headers.get("ETag", "").strip('"')
            verified = bool(re.fullmatch(r"[a-fA-F0-9]{32}", etag))
            if verified and md5.hexdigest() != etag.lower():
                raise ValueError("Discovery source ETag/MD5 disagreement")
            record = dict(
                url=url,
                sha256=sha256_file(temporary),
                bytes=size,
                etag=etag,
                etag_md5_verified=verified,
                accessed_utc=datetime.now(timezone.utc).isoformat(),
            )
        temporary.replace(path)
        write_json(receipt, record)
        return record
    finally:
        temporary.unlink(missing_ok=True)


def propose_tiles(index_text, request):
    west, south, east, north = request.bbox
    available, excluded = [], 0
    for name in sorted(set(index_text.splitlines())):
        match = re.fullmatch(
            r"Copernicus_DSM_COG_30_([NS])(\d{2})_00_([EW])(\d{3})_00_DEM", name.strip()
        )
        if not match:
            continue
        ns, a, ew, b = match.groups()
        lat = int(a) * (1 if ns == "N" else -1) + 0.5
        lon = int(b) * (1 if ew == "E" else -1) + 0.5
        if not (west <= lon <= east and south <= lat <= north):
            continue
        if any(GEOD.inv(lon, lat, x, y)[2] < 60000 for x, y in request.known_centers):
            excluded += 1
            continue
        available.append(dict(tile=name.strip(), latitude=lat, longitude=lon))
    available.sort(key=lambda r: (r["latitude"], r["longitude"]))
    count = min(request.budget, len(available))
    indices = [round(i * (len(available) - 1) / max(1, count - 1)) for i in range(count)]
    return [available[i] for i in indices], len(available), excluded


def measure_tile(root, proposal, request, folder):
    tile = proposal["tile"]
    raw = root / "data/raw/Earth/Copernicus90" / tile
    assets = {
        "DEM": (raw / f"{tile}.tif", BASE + f"{tile}/{tile}.tif"),
        "WBM": (
            raw / f"{tile.replace('_DEM', '_WBM')}.tif",
            BASE + f"{tile}/AUXFILES/{tile.replace('_DEM', '_WBM')}.tif",
        ),
        "XML": (
            raw / f"{tile.replace('_COG', '').replace('_DEM', '')}.xml",
            BASE + f"{tile}/{tile.replace('_COG', '').replace('_DEM', '')}.xml",
        ),
    }
    receipts = {
        key: acquire(url, path, limit=8_000_000 if key == "DEM" else 1_000_000)
        for key, (path, url) in assets.items()
    }
    dem, water, label = [assets[k][0] for k in ("DEM", "WBM", "XML")]
    label_text = label.read_text(encoding="utf-8")
    if "WGS84-G1150" not in label_text or "WGS 84 Geoid EGM08" not in label_text:
        raise ValueError("Copernicus metadata lacks the audited WGS84/EGM2008 datum")
    with rasterio.open(dem) as ds, rasterio.open(water) as mask:
        if (
            ds.count != 1
            or ds.crs != rasterio.crs.CRS.from_epsg(4326)
            or ds.shape != (1200, 1200)
            or mask.shape != ds.shape
            or mask.crs != ds.crs
            or mask.transform != ds.transform
            or not np.allclose(ds.res, (1 / 1200, 1 / 1200), atol=1e-12)
        ):
            raise ValueError("Copernicus DEM and water mask differ from the audited source grid")
        classes = mask.read(1)
        if not np.isin(classes, [0, 1, 2, 3]).all():
            raise ValueError("Unexpected Copernicus water-mask classes")
        source_crs, nodata = ds.crs.to_wkt(), ds.nodata
        lon, lat = proposal["longitude"], proposal["latitude"]
        if not (ds.bounds.left < lon < ds.bounds.right and ds.bounds.bottom < lat < ds.bounds.top):
            raise ValueError("Planned candidate center is outside its source tile")
    mask_path = folder / f"{content_hash(tile)[:12]}_water.bin"
    classes.astype("uint8").tofile(mask_path)
    site_id = (
        "discovery_" + tile.removeprefix("Copernicus_DSM_COG_30_").removesuffix("_DEM").lower()
    )
    roi_id = site_id + "_roi60km_v1"
    note = (
        "Systematically sampled available source-tile center chosen before scoring. "
        "WBM 0=no water retained; ocean(1), lake(2), river(3) excluded before averaging. "
        "DSM may include vegetation, buildings, snow, ice and infilled terrain. "
        "Geology/environment/resources/caves and literature novelty are unreviewed."
    )
    records = []
    for key, (path, url) in assets.items():
        records.append(
            SourceRecord(
                source_id=site_id + "_" + key,
                provider="Copernicus / Sinergise AWS",
                dataset="COP_DEM_GLO90" if key == "DEM" else f"COP_DEM_GLO90_{key}",
                version="AWS 2021 release",
                doi="10.5270/ESA-c5d3d65",
                product_url=assets["XML"][1],
                download_url=url,
                accessed_utc=receipts[key]["accessed_utc"],
                license_or_rights=ATTRIBUTION,
                checksum_sha256=receipts[key]["sha256"],
                planetary_body="Earth",
                horizontal_datum="WGS84-G1150",
                vertical_datum="EGM2008 geoid"
                if key == "DEM"
                else "Not applicable: supporting metadata/mask",
                pixel_size_m=90,
                processing_version="terrain_v1",
                roi_id=roi_id,
                processing_notes=note,
            )
        )
    sidecar = folder / f"{site_id}.yaml"
    interpretation = RasterInterpretation(
        body="Earth",
        product_type="topographic_elevation",
        source_crs=source_crs,
        horizontal_datum="WGS84-G1150",
        vertical_datum="EGM2008 geoid",
        latitude_type="geodetic",
        longitude_convention="-180_180",
        sample_unit="m",
        scale=1,
        offset=0,
        nodata=nodata,
        latitude_bounds_deg=(-90, 90),
        label_path=str(label.resolve()),
        label_sha256=receipts["XML"]["sha256"],
        mask_path=str(mask_path.resolve()),
        mask_sha256=sha256_file(mask_path),
        mask_land_value=0,
        interpretation_evidence=note,
    )
    sidecar.write_text(yaml.safe_dump(interpretation.model_dump(mode="json")), encoding="utf-8")
    validate_local_raster(dem, sidecar, records[0], "Earth")
    crs = f"+proj=aeqd +lat_0={lat} +lon_0={lon} +datum=WGS84 +units=m +type=crs"
    bounds = (-30000, -30000, 30000, 30000)
    z = metric_roi(dem, interpretation, crs, bounds, 1000, 60, interpretation_path=sidecar)
    measured = extract_features(z, 1000)
    reasons = quality_reasons(measured, request.scoring.minimum_valid_cell_fraction)
    profile = Profile(
        **measured.measurements.model_dump(),
        profile_id=site_id + "_60km_v1",
        body="Earth",
        region_name=f"Search candidate {lat:.2f}, {lon:.2f}",
        roi_id=roi_id,
        roi_size_km=60,
        common_grid_m=1000,
        valid_cell_fraction=measured.valid_cell_fraction,
        qa_pass=not reasons,
        source_ids=[r.source_id for r in records],
        processing_version="terrain_v1",
        config_sha256=content_hash(
            dict(request=request.model_dump(mode="json"), receipts=receipts)
        ),
        created_utc=datetime.now(timezone.utc),
        coordinate_convention="WGS84 geodetic; longitude -180..180",
        processing_notes=note,
        site_id=site_id,
        site_name=f"Search candidate {lat:.2f}, {lon:.2f}",
        country="Jurisdiction not independently identified",
        centroid_lat=lat,
        centroid_lon=lon,
        data_warning="; ".join(
            reasons + ["Unreviewed terrain candidate; Copernicus surface model"]
        ),
    )
    grid = folder / f"{site_id}.tif"
    with rasterio.open(
        grid,
        "w",
        driver="GTiff",
        height=60,
        width=60,
        count=1,
        dtype="float64",
        nodata=np.nan,
        crs=crs,
        transform=from_origin(-30000, 30000, 1000, 1000),
    ) as ds:
        ds.write(z, 1)
    footprint = dict(
        type="Feature",
        geometry=dict(type="Polygon", coordinates=[geographic_ring(crs, "Earth", bounds)]),
        properties=dict(site_id=site_id, latitude=lat, longitude=lon, novelty="unreviewed"),
    )
    audit = dict(
        site_id=site_id,
        source_receipts=receipts,
        analysis_grid=grid.name,
        analysis_sha256=sha256_file(grid),
        mask_sha256=sha256_file(mask_path),
        valid_elevation_count=int(measured.valid_elevation_count),
        valid_slope_count=int(measured.valid_slope_count),
        valid_roughness_count=int(measured.valid_roughness_count),
    )
    return profile, records, footprint, audit


def execute(root, folder):
    request = DiscoveryRequest.model_validate_json(
        (folder / "request.json").read_text(encoding="utf-8")
    )

    def status(state, **extra):
        write_json(
            folder / "status.json",
            dict(state=state, updated_utc=datetime.now(timezone.utc).isoformat(), **extra),
        )

    try:
        status(
            "running", message="Reading public coverage index", completed=0, total=request.budget
        )
        index = root / "data/raw/Earth/Copernicus90/tileList.txt"
        receipt = acquire(BASE + "tileList.txt", index, limit=5_000_000)
        proposals, available, excluded = propose_tiles(index.read_text(), request)
        profiles, records, footprints, audits, failures = [], [], [], [], []
        for i, proposal in enumerate(proposals):
            if (folder / "cancel.request").exists():
                status(
                    "cancelled",
                    message="Search cancelled; existing catalog preserved",
                    completed=i,
                    total=len(proposals),
                )
                return
            status(
                "running",
                message=f"Measuring {proposal['latitude']:.2f}, {proposal['longitude']:.2f}",
                completed=i,
                total=len(proposals),
            )
            try:
                p, s, f, a = measure_tile(root, proposal, request, folder)
                profiles.append(p)
                records.extend(s)
                footprints.append(f)
                audits.append(a)
            except (OSError, ValueError, requests.RequestException) as error:
                failures.append(dict(tile=proposal["tile"], reason=str(error)))
        if (folder / "cancel.request").exists():
            status(
                "cancelled",
                message="Search cancelled",
                completed=len(proposals),
                total=len(proposals),
            )
            return
        rows = rank_candidates(request.reference, profiles, request.scoring)
        metadata = dict(
            bbox=request.bbox,
            budget=request.budget,
            selection="evenly sampled tile-center sequence before scoring",
            novelty="unreviewed",
            provider="Copernicus GLO-90 AWS 2021",
            coverage_index=receipt,
            excluded_known_centers_within_km=60,
            available_new_tiles=available,
            excluded_count=excluded,
        )
        csv = export_analysis(
            request.reference, profiles, rows, request.scoring, selection_metadata=metadata
        )
        (folder / "rankings.csv").write_text(csv, encoding="utf-8", newline="")
        result = dict(
            request=request.model_dump(mode="json"),
            search=metadata,
            rankings=rows,
            profiles=[p.model_dump(mode="json") for p in profiles],
            sources=[s.model_dump(mode="json") for s in records],
            footprints=dict(type="FeatureCollection", features=footprints),
            audits=audits,
            failures=failures,
            attribution=ATTRIBUTION,
        )
        write_json(folder / "results.json", result)
        write_json(
            folder / "checksums.json",
            {
                name: sha256_file(folder / name)
                for name in ("request.json", "results.json", "rankings.csv")
            },
        )
        status(
            "completed",
            completed=len(proposals),
            total=len(proposals),
            measured=len(profiles),
            eligible=sum(r["eligible"] for r in rows),
            failed=len(failures),
            message="Search complete" if rows else "No measurable new candidates in this search",
        )
    except Exception as error:
        status("failed", message=f"{type(error).__name__}: {error}")
        raise


def load_completed_run(folder):
    checksums = json.loads((folder / "checksums.json").read_text(encoding="utf-8"))
    for name in ("request.json", "results.json", "rankings.csv"):
        if sha256_file(folder / name) != checksums[name]:
            raise ValueError("Saved discovery evidence changed")
    result = json.loads((folder / "results.json").read_text(encoding="utf-8"))
    request = DiscoveryRequest.model_validate(result["request"])
    profiles = [Profile.model_validate(p) for p in result["profiles"]]
    for profile in profiles:
        audit = next(a for a in result["audits"] if a["site_id"] == profile.site_id)
        path = (folder / audit["analysis_grid"]).resolve()
        if (
            not path.is_relative_to(folder.resolve())
            or sha256_file(path) != audit["analysis_sha256"]
        ):
            raise ValueError("Discovery analysis grid checksum changed")
        with rasterio.open(path) as ds:
            z = ds.read(1)
            if ds.res != (profile.common_grid_m, profile.common_grid_m) or z.shape != (60, 60):
                raise ValueError("Discovery grid scale changed")
        measured = extract_features(z, 1000)
        for key, value in measured.measurements.model_dump().items():
            if getattr(profile, key) != value:
                raise ValueError("Discovery profile does not reproduce measured terrain")
        if measured.valid_cell_fraction != profile.valid_cell_fraction or profile.qa_pass != (
            not quality_reasons(measured, request.scoring.minimum_valid_cell_fraction)
        ):
            raise ValueError("Discovery coverage/QA does not reproduce")
    if rank_candidates(request.reference, profiles, request.scoring) != result["rankings"]:
        raise ValueError("Saved discovery ranking does not reproduce")
    return result


def start_job(root, request):
    run_id = uuid.uuid4().hex
    folder = root / "data/processed/discovery" / run_id
    folder.mkdir(parents=True)
    write_json(folder / "request.json", request.model_dump(mode="json"))
    write_json(
        folder / "status.json",
        dict(state="queued", message="Starting search worker", completed=0, total=request.budget),
    )
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    with (folder / "worker.log").open("wb") as log:
        child = subprocess.Popen(
            [sys.executable, str(root / "scripts/discover_candidates.py"), "--run", run_id],
            cwd=root,
            stdout=log,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            **options,
        )
    write_json(folder / "worker.json", dict(pid=child.pid))
    return run_id
