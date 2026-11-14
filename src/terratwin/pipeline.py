"""Offline, local-file profile preparation. No acquisition runs in the web app."""

import importlib.metadata
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import rasterio
from pydantic import Field
from rasterio.transform import from_origin

from terratwin.config import ROOT, content_hash, read_yaml
from terratwin.datasets import load_catalog
from terratwin.geo.features import extract_features
from terratwin.geo.quality import quality_reasons
from terratwin.geo.rasters import metric_roi
from terratwin.geo.regions import validate_earth_footprint
from terratwin.ingest.earth_loader import load_earth
from terratwin.ingest.manifest import load_manifest, sha256_file
from terratwin.ingest.pds_loader import load_pds
from terratwin.models import Contract, Profile


class PipelineConfig(Contract):
    processing_version: str = "terrain_v1"
    features_version: str = "features_v1"
    common_grid_m: float = Field(gt=0)
    roi_size_km: float = Field(gt=0)
    roughness_kernel_cells: int = Field(ge=3)
    minimum_valid_cell_fraction: float = Field(gt=0, le=1)
    jobs: list[dict]


class Job(Contract):
    raster_path: str
    interpretation_path: str
    source_id: str
    destination_crs: str
    bounds_m: tuple[float, float, float, float]
    # Identity only: measurements, scale, QA and hashes are computed by the pipeline.
    identity: dict
    supporting_files: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


def build_profiles(config_path: Path, root: Path = ROOT) -> list[Profile]:
    config = PipelineConfig.model_validate(read_yaml(config_path))
    if not config.jobs:
        raise ValueError(
            "No verified raster jobs configured. Supply MOLA topography + label, "
            "LOLA GDR + label, NASADEM_HGT.001 clips + metadata, and verified ROI definitions. "
            "See docs/data-acquisition.md."
        )
    if config.roughness_kernel_cells % 2 != 1:
        raise ValueError("Roughness kernel must be odd")
    manifest = load_manifest(root / "data/metadata/sources.csv")
    catalog = load_catalog(root / "data/catalog/earth_sites.geojson")
    profiles, reports, arrays = [], [], []
    for raw_job in config.jobs:
        job = Job.model_validate(raw_job)
        if job.source_id not in manifest:
            raise ValueError(f"Missing source manifest record: {job.source_id}")
        source = manifest[job.source_id]
        support_records = {}
        for source_id, relative_path in job.supporting_files.items():
            if source_id not in manifest:
                raise ValueError(f"Missing supporting source: {source_id}")
            supporting = manifest[source_id]
            if supporting.planetary_body != source.planetary_body:
                raise ValueError("Supporting source body mismatch")
            if supporting.roi_id != source.roi_id:
                raise ValueError("Supporting source ROI mismatch")
            if sha256_file(root / relative_path) != supporting.checksum_sha256:
                raise ValueError(f"Supporting file checksum mismatch: {source_id}")
            support_records[source_id] = supporting.model_dump(mode="json")
        raster_path, interpretation_path = (
            root / job.raster_path,
            root / job.interpretation_path,
        )
        adapter = load_earth if source.planetary_body == "Earth" else load_pds
        metadata = adapter(raster_path, interpretation_path, source)
        if source.roi_id != job.identity.get("roi_id"):
            raise ValueError("Job ROI differs from source manifest")
        if source.processing_version != config.processing_version:
            raise ValueError("Source manifest processing version differs from pipeline")
        array = metric_roi(
            raster_path,
            metadata,
            job.destination_crs,
            job.bounds_m,
            config.common_grid_m,
            config.roi_size_km,
            interpretation_path=interpretation_path,
        )
        features = extract_features(
            array,
            config.common_grid_m,
            roughness_kernel_cells=config.roughness_kernel_cells,
        )
        reasons = quality_reasons(features, config.minimum_valid_cell_fraction)
        computed = dict(
            body=source.planetary_body,
            roi_size_km=config.roi_size_km,
            common_grid_m=config.common_grid_m,
            roughness_kernel_cells=config.roughness_kernel_cells,
            valid_cell_fraction=features.valid_cell_fraction,
            qa_pass=not reasons,
            source_ids=[source.source_id, *sorted(support_records)],
            processing_version=config.processing_version,
            features_version=config.features_version,
            config_sha256=content_hash(
                {
                    "pipeline": config.model_dump(),
                    "source": source.model_dump(mode="json"),
                    "interpretation": metadata.model_dump(),
                    "supporting_sources": support_records,
                }
            ),
            created_utc=datetime.now(timezone.utc),
            coordinate_convention=f"{metadata.latitude_type}; {metadata.longitude_convention}",
            processing_notes=metadata.interpretation_evidence,
            data_warning="; ".join([*job.warnings, *reasons]),
            synthetic=False,
            **features.measurements.model_dump(),
        )
        if set(job.identity) & set(computed):
            raise ValueError("Job identity cannot override computed measurements or provenance")
        profile = Profile.model_validate({**job.identity, **computed})
        if profile.body == "Earth":
            if profile.site_id not in catalog:
                raise ValueError(f"No verified Earth polygon for {profile.site_id}")
            properties = catalog[profile.site_id]["properties"]
            validate_earth_footprint(
                catalog[profile.site_id]["geometry"], job.destination_crs, job.bounds_m
            )
            if any(
                getattr(profile, key) != properties[key]
                for key in (
                    "roi_id",
                    "centroid_lat",
                    "centroid_lon",
                )
            ):
                raise ValueError("Earth profile/catalog identity mismatch")
        profiles.append(profile)
        arrays.append((profile, array, job))
        reports.append(
            {
                "profile_id": profile.profile_id,
                "raster_sha256": source.checksum_sha256,
                "reader_entrypoint_sha256": sha256_file(raster_path),
                "supporting_source_ids": sorted(support_records),
                "interpretation_sha256": sha256_file(interpretation_path),
                "label_sha256": metadata.label_sha256,
                "config_sha256": profile.config_sha256,
                "destination_crs": job.destination_crs,
                "bounds_m": job.bounds_m,
                "valid_elevation_count": features.valid_elevation_count,
                "valid_slope_count": features.valid_slope_count,
                "valid_roughness_count": features.valid_roughness_count,
                "quality_reasons": reasons,
            }
        )
    if len({p.profile_id for p in profiles}) != len(profiles):
        raise ValueError("Duplicate profile IDs in pipeline jobs")
    earth_ids = [p.site_id for p in profiles if p.body == "Earth"]
    if len(set(earth_ids)) != len(earth_ids):
        raise ValueError("Duplicate Earth site IDs in pipeline jobs")
    output = root / "data/processed"
    output.mkdir(parents=True, exist_ok=True)
    terrain = output / "terrain"
    terrain.mkdir(exist_ok=True)
    for profile, array, job in arrays:
        # Use a digest filename: identifiers never become filesystem paths.
        name = content_hash(profile.profile_id)[:16] + ".tif"
        path = terrain / name
        with rasterio.open(
            path,
            "w",
            driver="GTiff",
            height=array.shape[0],
            width=array.shape[1],
            count=1,
            dtype="float64",
            nodata=np.nan,
            crs=job.destination_crs,
            transform=from_origin(
                job.bounds_m[0], job.bounds_m[3], config.common_grid_m, config.common_grid_m
            ),
            compress="deflate",
        ) as dataset:
            dataset.write(array, 1)
        report = next(r for r in reports if r["profile_id"] == profile.profile_id)
        report["analysis_raster"] = f"terrain/{name}"
        report["analysis_raster_sha256"] = sha256_file(path)
    for name, group in (
        ("planetary_profiles", [p for p in profiles if p.body != "Earth"]),
        ("earth_profiles", [p for p in profiles if p.body == "Earth"]),
    ):
        # Always replace both tables, including empty tables: no stale profiles from prior runs.
        rows = [p.model_dump(mode="json") for p in group]
        path = output / f"{name}.parquet"
        temp = path.with_suffix(".parquet.tmp")
        pd.DataFrame(rows).to_parquet(temp, index=False)
        temp.replace(path)
    git = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    report = {
        "git_commit": git.stdout.strip() or "unavailable",
        "code_sha256": content_hash(
            {
                str(path.relative_to(root)).replace("\\", "/"): sha256_file(path)
                for folder in (root / "src", root / "scripts")
                for path in sorted(folder.rglob("*.py"))
            }
        ),
        "pipeline_config_sha256": content_hash(config.model_dump()),
        "packages": {
            package: importlib.metadata.version(package)
            for package in (
                "terratwin-ai",
                "numpy",
                "rasterio",
                "pyproj",
                "pydantic",
                "pandas",
            )
        },
        "profiles": reports,
    }
    (output / "processing_manifest.json").write_text(
        json.dumps(report, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    return profiles
