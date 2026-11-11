"""Validate all scientific products before making them available to the UI."""

import json
from pathlib import Path

import pandas as pd
from shapely.geometry import Point, shape

from terratwin.config import ROOT
from terratwin.ingest.manifest import load_manifest
from terratwin.models import Profile


def load_catalog(path: Path) -> dict:
    collection = json.loads(path.read_text(encoding="utf-8"))
    if collection.get("type") != "FeatureCollection":
        raise ValueError("Earth catalog must be a GeoJSON FeatureCollection")
    sites = {}
    for feature in collection["features"]:
        properties = feature["properties"]
        site_id = properties["site_id"]
        if site_id in sites:
            raise ValueError("Duplicate catalog site ID")
        polygon = shape(feature["geometry"])
        if polygon.geom_type not in ("Polygon", "MultiPolygon") or not polygon.is_valid:
            raise ValueError(f"Invalid polygon for {site_id}")
        lon, lat = properties["centroid_lon"], properties["centroid_lat"]
        if not (-180 <= lon <= 180 and -56 <= lat <= 60):
            raise ValueError(f"Invalid NASADEM catalog coordinates for {site_id}")
        if not polygon.covers(Point(lon, lat)):
            raise ValueError(f"Catalog centroid outside polygon for {site_id}")
        for key in ("site_name", "country", "roi_id", "seed_or_candidate", "reason_selected"):
            if not properties.get(key):
                raise ValueError(f"Missing catalog {key} for {site_id}")
        sites[site_id] = feature
    return sites


def load_prepared(root: Path = ROOT) -> tuple[list[Profile], list[Profile], dict]:
    paths = [
        root / "data/processed" / name
        for name in (
            "planetary_profiles.parquet",
            "earth_profiles.parquet",
        )
    ]
    if not all(path.is_file() for path in paths):
        raise ValueError(
            "No validated scientific profiles loaded. Required: "
            + ", ".join(path.name for path in paths if not path.is_file())
        )
    sources = load_manifest(root / "data/metadata/sources.csv")
    groups = []
    for path in paths:
        profiles = []
        for row in pd.read_parquet(path).to_dict("records"):
            # Only optional feature/candidate columns may be null. Pydantic rejects
            # nonfinite measurements and missing required provenance.
            row = {
                key: (None if isinstance(value, float) and pd.isna(value) else value)
                for key, value in row.items()
            }
            if hasattr(row.get("source_ids"), "tolist"):
                row["source_ids"] = row["source_ids"].tolist()
            profile = Profile.model_validate(row)
            if profile.synthetic:
                raise ValueError("Synthetic profiles are forbidden in application data")
            for source_id in profile.source_ids:
                if source_id not in sources:
                    raise ValueError(f"Missing source manifest record: {source_id}")
                if sources[source_id].planetary_body != profile.body:
                    raise ValueError("Profile/source planetary body mismatch")
            profiles.append(profile)
        if len({p.profile_id for p in profiles}) != len(profiles):
            raise ValueError("Duplicate profile IDs")
        groups.append(profiles)
    references, earth = groups
    if any(p.body not in ("Mars", "Moon") for p in references):
        raise ValueError("Planetary table contains a non-planetary profile")
    if any(p.body != "Earth" for p in earth):
        raise ValueError("Earth table contains a non-Earth profile")
    catalog = load_catalog(root / "data/catalog/earth_sites.geojson")
    for site in earth:
        if site.site_id not in catalog:
            raise ValueError(f"No verified catalog polygon for {site.site_id}")
        properties = catalog[site.site_id]["properties"]
        if (
            site.roi_id != properties["roi_id"]
            or site.centroid_lon != properties["centroid_lon"]
            or site.centroid_lat != properties["centroid_lat"]
        ):
            raise ValueError(f"Profile/catalog ROI or centroid mismatch for {site.site_id}")
    return references, earth, sources
