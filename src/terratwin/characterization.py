"""Evidence-backed Earth context, separate from cross-body terrain similarity."""

import json
import math
import re
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

from terratwin.ingest.manifest import sha256_file

CLIMATE_START, CLIMATE_END = "2015-01-01", "2024-12-31"


def summarize_climate(payload, start=CLIMATE_START, end=CLIMATE_END):
    daily, units = payload["daily"], payload["daily_units"]
    if units["temperature_2m_mean"] != "°C" or units["precipitation_sum"] != "mm":
        raise ValueError("Climate source units differ from the documented interpretation")
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    dates = [first + timedelta(days=n) for n in range((last - first).days + 1)]
    if daily["time"] != [d.isoformat() for d in dates]:
        raise ValueError("Climate dates must be complete, contiguous and ordered")
    temperatures, precipitation = daily["temperature_2m_mean"], daily["precipitation_sum"]
    if len(temperatures) != len(dates) or len(precipitation) != len(dates):
        raise ValueError("Climate sample arrays differ in length")
    for value in [*temperatures, *precipitation]:
        if value is not None and not math.isfinite(value):
            raise ValueError("Nonfinite climate measurement")
    if any(v < 0 for v in precipitation if v is not None):
        raise ValueError("Precipitation cannot be negative")
    if any(not -100 <= v <= 70 for v in temperatures if v is not None):
        raise ValueError("Invalid Earth air temperature or unmasked source fill value")
    valid = [v for v in temperatures if v is not None]
    by_month, by_year = defaultdict(list), defaultdict(list)
    for day, t, p in zip(dates, temperatures, precipitation, strict=True):
        if t is not None:
            by_month[day.month].append(t)
        by_year[day.year].append(p)
    # A complete annual total is never inferred from an incomplete year.
    totals = [
        math.fsum(values)
        for year, values in by_year.items()
        if None not in values and len(values) == (date(year + 1, 1, 1) - date(year, 1, 1)).days
    ]
    fraction = len(valid) / len(dates)
    return dict(
        period_start=start,
        period_end=end,
        sample_days=len(dates),
        valid_temperature_fraction=fraction,
        mean_temperature_c=math.fsum(valid) / len(valid) if fraction >= 0.95 else None,
        freezing_mean_day_fraction=sum(t < 0 for t in valid) / len(valid)
        if fraction >= 0.95
        else None,
        mean_annual_precipitation_mm=math.fsum(totals) / len(totals)
        if len(totals) == len(by_year)
        else None,
        complete_precipitation_years=len(totals),
        monthly_mean_temperature_c={
            str(month): math.fsum(values) / len(values)
            for month, values in sorted(by_month.items())
        },
        spatial_scope="Model grid cell selected near Earth ROI centroid, not an ROI average",
        model="Copernicus ERA5 via Open-Meteo; 0.25 degree reanalysis",
        resource_inference="Precipitation and temperature do not measure extractable water or ice",
    )


def summarize_geology(payload):
    success = payload["success"]
    rows = success["data"]
    if not rows:
        return dict(status="no_mapped_unit", units=[], lithology_classes=[], references={})
    order = {"large": 0, "medium": 1, "small": 2, "tiny": 3}
    best = min(order.get(row.get("scale"), 4) for row in rows)
    selected = [row for row in rows if order.get(row.get("scale"), 4) == best]
    units = [
        {
            k: row.get(k)
            for k in ("map_id", "source_id", "name", "lith", "descrip", "scale", "best_int_name")
        }
        for row in selected
    ]
    text = " ".join(str(row.get(k, "")) for row in selected for k in ("name", "lith")).lower()
    classes = []
    for name, pattern in {
        "volcanic": r"volcan|basalt|andesit|rhyolit|lava|tuff",
        "sedimentary": r"sediment|siliciclastic|sandstone|limestone|mudstone|shale",
        "unconsolidated": r"alluv|unconsolidat|surficial|sand\b|gravel|playa",
        "metamorphic": r"metamorph|gneiss|schist|quartzite",
        "plutonic": r"pluton|granit|diorit|gabbro",
    }.items():
        if re.search(pattern, text):
            classes.append(name)
    references = success.get("refs", {})
    return dict(
        status="mapped_context",
        units=units,
        lithology_classes=classes,
        references={
            str(row["source_id"]): references.get(str(row["source_id"]), "") for row in selected
        },
        license=success.get("license", "See source"),
        spatial_scope="Mapped units intersecting the ROI centroid; not whole-ROI geology",
        classification_method="Explicit lithology-name keyword screening, not mineral inference",
    )


def load_characterization(root: Path):
    path = root / "data/processed/characterization.json"
    if not path.exists():
        return {}
    bundle = json.loads(path.read_text(encoding="utf-8"))
    for row in bundle["sites"].values():
        for evidence in row["evidence"]:
            if sha256_file(root / evidence["raw_path"]) != evidence["sha256"]:
                raise ValueError("Characterization evidence checksum changed")
            if sha256_file(root / evidence["metadata_path"]) != evidence["metadata_sha256"]:
                raise ValueError("Characterization request metadata checksum changed")
            request = json.loads((root / evidence["metadata_path"]).read_text(encoding="utf-8"))
            params = request["requested_parameters"]
            lat_key, lon_key = (
                ("latitude", "longitude") if evidence["kind"] == "climate" else ("lat", "lng")
            )
            if params[lat_key] != row["latitude"] or params[lon_key] != row["longitude"]:
                raise ValueError("Characterization query location differs from site")
            payload = json.loads((root / evidence["raw_path"]).read_text(encoding="utf-8"))
            if evidence["kind"] == "climate":
                if params["models"] != "era5":
                    raise ValueError("Unsupported climate model for this interpretation")
                recalculated = summarize_climate(payload)
            else:
                recalculated = summarize_geology(payload)
            if recalculated != row[evidence["kind"]]:
                raise ValueError("Characterization summary differs from source evidence")
    return bundle["sites"]


def characterize_filter(
    profile, context, *, max_precipitation=None, max_temperature=None, geology_class=None
):
    """Missing evidence never passes a requested filter; terrain eligibility is separate."""
    context = context or {}
    if context and (
        context["latitude"] != profile.centroid_lat or context["longitude"] != profile.centroid_lon
    ):
        raise ValueError("Characterization location differs from prepared terrain profile")
    climate = context.get("climate") or {}
    for field, threshold in (
        ("mean_annual_precipitation_mm", max_precipitation),
        ("mean_temperature_c", max_temperature),
    ):
        value = climate.get(field)
        if threshold is not None and (value is None or value > threshold):
            return False
    if geology_class and geology_class not in (context.get("geology") or {}).get(
        "lithology_classes", []
    ):
        return False
    return True
