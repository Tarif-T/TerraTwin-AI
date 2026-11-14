"""Independently recompute real-grid measurements and verify app/export parity.

Validates numerical behavior for the prepared slice, not external scientific
suitability. Never manufactures or fills missing scientific profiles.
"""

import argparse
import csv
import io
import json
import math
from datetime import datetime, timezone

import numpy as np
import rasterio
from streamlit.testing.v1 import AppTest

from terratwin.config import ROOT, content_hash, load_scoring, read_yaml
from terratwin.datasets import load_prepared
from terratwin.export.csv_export import export_analysis
from terratwin.geo.rasters import metric_roi
from terratwin.ingest.manifest import sha256_file
from terratwin.ingest.raster_input import RasterInterpretation
from terratwin.models import FEATURES, ScoringConfig
from terratwin.scoring.engine import rank_candidates


def quantile(values, fraction):
    ordered = sorted(float(value) for value in values)
    index = (len(ordered) - 1) * fraction
    lower, upper = math.floor(index), math.ceil(index)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def independent_features(z, spacing, kernel):
    """Scalar loops and explicit statistics, separate from production vectorized code."""
    heights, slopes, roughness = [], [], []
    rows, cols = z.shape
    radius = kernel // 2
    for r in range(rows):
        for c in range(cols):
            if math.isfinite(z[r, c]):
                heights.append(z[r, c])
            if 0 < r < rows - 1 and 0 < c < cols - 1:
                stencil = [z[r, c], z[r - 1, c], z[r + 1, c], z[r, c - 1], z[r, c + 1]]
                if all(math.isfinite(value) for value in stencil):
                    dx = (z[r, c + 1] - z[r, c - 1]) / (2 * spacing)
                    dy = (z[r + 1, c] - z[r - 1, c]) / (2 * spacing)
                    slopes.append(math.degrees(math.atan(math.sqrt(dx * dx + dy * dy))))
            if radius <= r < rows - radius and radius <= c < cols - radius:
                window = [
                    z[a, b]
                    for a in range(r - radius, r + radius + 1)
                    for b in range(c - radius, c + radius + 1)
                ]
                if all(math.isfinite(value) for value in window):
                    mean = math.fsum(window) / len(window)
                    roughness.append(
                        math.sqrt(math.fsum((v - mean) ** 2 for v in window) / len(window))
                    )
    if not heights or not slopes or not roughness:
        raise ValueError("Independent validator found insufficient measured samples")
    return {
        "slope_median_deg": quantile(slopes, 0.5),
        "relief_p90_p10_m": quantile(heights, 0.9) - quantile(heights, 0.1),
        "roughness_local_std_m": quantile(roughness, 0.5),
        "steep_fraction_15deg": sum(value > 15 for value in slopes) / len(slopes),
    }


def validate(check_ui=True):
    references, sites, _ = load_prepared()
    if not references or not sites:
        raise ValueError("Real references and sites are required")
    pipeline = read_yaml(ROOT / "config/pipeline.yaml")
    processing = json.loads((ROOT / "data/processed/processing_manifest.json").read_text())
    if processing["pipeline_config_sha256"] != content_hash(pipeline):
        raise ValueError("Processing manifest config hash is stale")
    code_hash = content_hash(
        {
            str(path.relative_to(ROOT)).replace("\\", "/"): sha256_file(path)
            for folder in (ROOT / "src", ROOT / "scripts")
            for path in sorted(folder.rglob("*.py"))
        }
    )
    if processing["code_sha256"] != code_hash:
        raise ValueError("Rebuild profiles after numerical/preparation code changes")
    configs = {job["identity"]["profile_id"]: job for job in pipeline["jobs"]}
    evidence, grids = [], []
    for profile in [*references, *sites]:
        report = next(
            row for row in processing["profiles"] if row["profile_id"] == profile.profile_id
        )
        path = ROOT / "data/processed" / report["analysis_raster"]
        if sha256_file(path) != report["analysis_raster_sha256"]:
            raise ValueError("Saved analysis raster changed")
        with rasterio.open(path) as dataset:
            z = dataset.read(1)
            if not np.allclose([dataset.res[0], dataset.res[1]], profile.common_grid_m):
                raise ValueError("Saved grid spacing differs from profile")
        result = independent_features(z, profile.common_grid_m, profile.roughness_kernel_cells)
        differences = {name: abs(result[name] - getattr(profile, name)) for name in FEATURES}
        if any(value > 1e-8 for value in differences.values()):
            raise ValueError(f"Independent feature disagreement: {differences}")
        fraction = float(np.isfinite(z).mean())
        if abs(fraction - profile.valid_cell_fraction) > 1e-12:
            raise ValueError("Saved grid/profile coverage disagreement")
        job = configs[profile.profile_id]
        interpretation_path = ROOT / job["interpretation_path"]
        metadata = RasterInterpretation.model_validate(read_yaml(interpretation_path))
        repeated = metric_roi(
            ROOT / job["raster_path"],
            metadata,
            job["destination_crs"],
            job["bounds_m"],
            profile.common_grid_m,
            profile.roi_size_km,
            interpretation_path=interpretation_path,
        )
        if not np.array_equal(z, repeated, equal_nan=True):
            raise ValueError("Repeated raw-to-grid processing is not deterministic")
        if profile.body == "Earth" and metadata.mask_path:
            unmasked_metadata = metadata.model_copy(update={"mask_path": None, "mask_sha256": None})
            unmasked = metric_roi(
                ROOT / job["raster_path"],
                unmasked_metadata,
                job["destination_crs"],
                job["bounds_m"],
                profile.common_grid_m,
                profile.roi_size_km,
                interpretation_path=interpretation_path,
            )
            removed = int((np.isfinite(unmasked) & ~np.isfinite(z)).sum())
        else:
            removed = None
        grids.append((profile, z))
        evidence.append(
            {
                "profile_id": profile.profile_id,
                "independent_features": result,
                "absolute_errors": differences,
                "valid_cell_fraction": fraction,
                "water_mask_removed_analysis_cells": removed,
                "raw_to_grid_repeat_exact": True,
            }
        )
    config = load_scoring()
    reference = next(p for p in references if p.body == "Mars")
    results = rank_candidates(reference, sites, config)
    weights = config.normalized_weights
    for row in results:
        site = next(p for p in sites if p.site_id == row["site_id"])
        values = {
            name: math.exp(
                -abs(getattr(site, name) - getattr(reference, name)) / config.tolerances[name]
            )
            for name in FEATURES
        }
        independent_score = 100 * math.fsum(weights[name] * values[name] for name in FEATURES)
        if abs(independent_score - row["similarity_index"]) > 1e-10:
            raise ValueError("Independent scoring disagreement")
    csv_payload = export_analysis(reference, sites, results, config)
    rows = list(csv.DictReader(io.StringIO(csv_payload)))
    if any(
        float(row["similarity_index"]) != result["similarity_index"]
        for row, result in zip(rows, results)
    ):
        raise ValueError("CSV score mismatch")
    sensitivity = []
    for feature in FEATURES:
        for multiplier in (0.9, 1.1):
            raw_weights = {**config.weights, feature: config.weights[feature] * multiplier}
            altered = ScoringConfig.model_validate({**config.model_dump(), "weights": raw_weights})
            result = rank_candidates(reference, sites, altered)[0]
            sensitivity.append(
                {
                    "feature": feature,
                    "weight_multiplier": multiplier,
                    "score": result["similarity_index"],
                }
            )
    ablations = []
    for feature in ("slope_median_deg", "roughness_local_std_m"):
        altered = ScoringConfig.model_validate(
            {**config.model_dump(), "weights": {**config.weights, feature: 0}}
        )
        ablations.append(
            {
                "removed": feature,
                "score": rank_candidates(reference, sites, altered)[0]["similarity_index"],
            }
        )
    ui = {"checked": False}
    if check_ui:
        app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
        if app.exception or app.button[0].disabled:
            raise ValueError(f"Real app failed or disabled ranking: {app.exception}")
        app.button[0].click().run()
        if app.exception:
            raise ValueError(f"Real ranking UI failed: {app.exception}")
        table = next(frame.value for frame in app.dataframe if "rank" in frame.value.columns)
        if table["similarity_index"].tolist() != [
            r["similarity_index"] for r in results if r["eligible"]
        ]:
            raise ValueError("Real UI table scores differ from export")
        if len(app.get("download_button")) != 1:
            raise ValueError("Real CSV download button missing")
        next(s for s in app.selectbox if s.label == "Planetary body").select("Moon").run()
        if app.exception or not app.button[0].disabled or app.get("download_button"):
            raise ValueError("Unavailable Moon allows stale result/export")
        ui = {"checked": True, "real_rank_table_csv_parity": True, "unavailable_moon_blocked": True}
    output = ROOT / "data/processed"
    (output / "real_analysis.csv").write_text(csv_payload, encoding="utf-8", newline="")
    summary = {
        "validated_utc": datetime.now(timezone.utc).isoformat(),
        "status": "numerically_verified_limited_real_slice",
        "scientific_suitability_validated": False,
        "input_data_hash": rows[0]["input_data_hash"],
        "run_id": rows[0]["run_id"],
        "profiles": evidence,
        "rankings": results,
        "ui": ui,
        "weight_sensitivity": sensitivity,
        "ablations": ablations,
        "limitations": [
            "One candidate cannot establish ranking utility or novelty.",
            "Engineering weights/tolerances are uncalibrated.",
            "Independent arithmetic checks use the same measured grids.",
            "Earth publisher ZIP checksum remains unverified.",
            "Lunar profile and >=10-site acceptance remain incomplete.",
        ],
    }
    (output / "real_validation.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    plot(grids, output / "real_terrain_review.png")
    print(
        json.dumps(
            {
                "status": summary["status"],
                "score": results[0]["similarity_index"],
                "coverage": results[0]["feature_coverage"],
                "ui": ui,
            },
            indent=2,
        )
    )


def plot(grids, path):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.colors import LightSource

    fig, axes = plt.subplots(2, len(grids), figsize=(12, 9), layout="constrained")
    for col, (profile, z) in enumerate(grids):
        height = np.ma.masked_invalid(z)
        image = axes[0, col].imshow(height, extent=(-30, 30, -30, 30), cmap="terrain")
        datum = "MOLA GMM3 areoid" if profile.body == "Mars" else "NASADEM EGM96 geoid"
        fig.colorbar(image, ax=axes[0, col], label=f"Elevation (m), {datum}", shrink=0.8)
        axes[0, col].set_title(f"{profile.body}: {profile.region_name}", fontsize=10)
        shade = LightSource(azdeg=315, altdeg=45).hillshade(z, dx=1000, dy=1000)
        axes[1, col].imshow(np.ma.masked_invalid(shade), extent=(-30, 30, -30, 30), cmap="gray")
        axes[1, col].set_title("Hillshade of measured 1 km grid; gaps are masked", fontsize=10)
        for ax in axes[:, col]:
            ax.set_xlabel("Local easting (km)")
            ax.set_ylabel("Local northing (km)")
    fig.suptitle(
        "Real terrain review: matched 60 x 60 km footprints\n"
        "Separate vertical datums and color scales; no absolute-height scoring",
        fontsize=13,
    )
    fig.savefig(path, dpi=140)
    plt.close(fig)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-ui", action="store_true")
    args = parser.parse_args()
    validate(not args.skip_ui)
