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

from terratwin.characterization import load_characterization
from terratwin.config import ROOT, content_hash, load_scoring, read_yaml
from terratwin.datasets import load_prepared
from terratwin.export.csv_export import export_analysis
from terratwin.geo.rasters import metric_roi
from terratwin.ingest.manifest import sha256_file
from terratwin.ingest.raster_input import RasterInterpretation
from terratwin.mission import mission_scoring
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
    return {
        "slope_median_deg": quantile(slopes, 0.5) if slopes else None,
        "relief_p90_p10_m": quantile(heights, 0.9) - quantile(heights, 0.1) if heights else None,
        "roughness_local_std_m": quantile(roughness, 0.5) if roughness else None,
        "steep_fraction_15deg": sum(value > 15 for value in slopes) / len(slopes)
        if slopes
        else None,
    }


def independent_ranking(reference, sites, config):
    """Recompute score, rejection and ordering without using engine result fields."""
    rows = []
    for site in sites:
        valid = [
            name
            for name in FEATURES
            if getattr(site, name) is not None and getattr(reference, name) is not None
        ]
        total_weight = math.fsum(config.weights.values())
        supported = math.fsum(config.weights[name] for name in valid)
        coverage = supported / total_weight
        score = (
            100
            * math.fsum(
                config.weights[name]
                * math.exp(
                    -abs(getattr(site, name) - getattr(reference, name)) / config.tolerances[name]
                )
                for name in valid
            )
            / supported
            if supported
            else None
        )
        eligible = (
            coverage >= config.minimum_coverage
            and site.qa_pass
            and site.valid_cell_fraction >= config.minimum_valid_cell_fraction
        )
        rows.append(
            dict(
                site_id=site.site_id,
                similarity_index=score,
                feature_coverage=coverage,
                eligible=eligible,
            )
        )
    rows.sort(
        key=lambda r: (
            not r["eligible"],
            -(r["similarity_index"] if r["similarity_index"] is not None else -1),
            -r["feature_coverage"],
            r["site_id"],
        )
    )
    rank = 0
    for row in rows:
        if row["eligible"]:
            rank += 1
            row["rank"] = rank
        else:
            row["rank"] = None
    return rows


def rank_summary(results):
    return [
        {
            key: row[key]
            for key in ("site_id", "rank", "similarity_index", "feature_coverage", "eligible")
        }
        for row in results
    ]


def verified_ranking(reference, sites, config):
    results = rank_candidates(reference, sites, config)
    for row, expected in zip(results, independent_ranking(reference, sites, config), strict=True):
        for key in ("site_id", "eligible", "rank"):
            if row[key] != expected[key]:
                raise ValueError(f"Independent ranking disagreement: {key}")
        for key in ("similarity_index", "feature_coverage"):
            if (row[key] is None) != (expected[key] is None):
                raise ValueError(f"Independent missingness disagreement: {key}")
            if row[key] is not None and abs(row[key] - expected[key]) > 1e-10:
                raise ValueError(f"Independent scoring disagreement: {key}")
    return results


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
        differences = {}
        for name in FEATURES:
            measured, saved = result[name], getattr(profile, name)
            if (measured is None) != (saved is None):
                raise ValueError(f"Independent feature missingness disagreement: {name}")
            differences[name] = abs(measured - saved) if measured is not None else 0.0
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
                "source_mask_removed_analysis_cells": removed,
                "raw_to_grid_repeat_exact": True,
            }
        )
    config = load_scoring()
    reference = next(p for p in references if p.body == "Mars")
    results = rank_candidates(reference, sites, config)
    independent = independent_ranking(reference, sites, config)
    for row, expected in zip(results, independent, strict=True):
        for key in ("site_id", "eligible", "rank"):
            if row[key] != expected[key]:
                raise ValueError(f"Independent ranking disagreement: {key}")
        for key in ("similarity_index", "feature_coverage"):
            if (row[key] is None) != (expected[key] is None):
                raise ValueError(f"Independent missingness disagreement: {key}")
            if row[key] is not None and abs(row[key] - expected[key]) > 1e-10:
                raise ValueError(f"Independent scoring disagreement: {key}")
    contexts = load_characterization(ROOT)
    selection = {
        "mission_id": "terrain_baseline",
        "max_precipitation": None,
        "max_temperature": None,
        "geology_class": None,
    }
    csv_payload = export_analysis(
        reference, sites, results, config, characterization=contexts, selection_metadata=selection
    )
    rows = list(csv.DictReader(io.StringIO(csv_payload)))
    if any(
        (float(row["similarity_index"]) if row["similarity_index"] else None)
        != result["similarity_index"]
        or row["site_id"] != result["site_id"]
        for row, result in zip(rows, results, strict=True)
    ):
        raise ValueError("CSV score mismatch")
    sensitivity = []
    for feature in FEATURES:
        for multiplier in (0.9, 1.1):
            raw_weights = {**config.weights, feature: config.weights[feature] * multiplier}
            altered = ScoringConfig.model_validate({**config.model_dump(), "weights": raw_weights})
            altered_results = rank_candidates(reference, sites, altered)
            sensitivity.append(
                {
                    "feature": feature,
                    "weight_multiplier": multiplier,
                    "score": altered_results[0]["similarity_index"],
                    "rankings": rank_summary(altered_results),
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
                "rankings": rank_summary(rank_candidates(reference, sites, altered)),
            }
        )
    all_references = {}
    written_bodies = set()
    for target in references:
        missions = {}
        for preset in read_yaml(ROOT / "config/missions.yaml")["missions"]:
            altered = mission_scoring(config, preset)
            missions[preset["id"]] = rank_summary(verified_ranking(target, sites, altered))
        target_results = verified_ranking(target, sites, config)
        target_csv = export_analysis(
            target,
            sites,
            target_results,
            config,
            characterization=contexts,
            selection_metadata=selection,
        )
        target_rows = list(csv.DictReader(io.StringIO(target_csv)))
        if [r["site_id"] for r in target_rows] != [r["site_id"] for r in target_results]:
            raise ValueError("Reference CSV candidate ordering mismatch")
        (ROOT / f"data/processed/{target.profile_id}_analysis.csv").write_text(
            target_csv, encoding="utf-8", newline=""
        )
        if target.body not in written_bodies:
            (ROOT / f"data/processed/{target.body.lower()}_analysis.csv").write_text(
                target_csv, encoding="utf-8", newline=""
            )
            written_bodies.add(target.body)
        all_references[target.profile_id] = dict(
            body=target.body,
            rankings=target_results,
            missions=missions,
            csv_input_hash=target_rows[0]["input_data_hash"],
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
        if app.exception or app.get("download_button"):
            raise ValueError("Body switch retained stale result/export")
        lunar = next((p for p in references if p.body == "Moon"), None)
        if lunar:
            if app.button[0].disabled:
                raise ValueError("Prepared Moon reference cannot be ranked")
            app.button[0].click().run()
            lunar_table = next(f.value for f in app.dataframe if "rank" in f.value.columns)
            lunar_results = verified_ranking(lunar, sites, config)
            lunar_eligible = [r for r in lunar_results if r["eligible"]]
            if lunar_table["site_name"].tolist() != [r["site_name"] for r in lunar_eligible]:
                raise ValueError("Lunar UI candidate ordering mismatch")
            if lunar_table["similarity_index"].tolist() != [
                r["similarity_index"] for r in lunar_eligible
            ]:
                raise ValueError("Lunar UI scores differ from independently verified export")
            if app.exception or len(app.get("download_button")) != 1:
                raise ValueError("Lunar UI export unavailable")
        elif not app.button[0].disabled:
            raise ValueError("Unavailable Moon allows ranking")
        for target in references:
            next(s for s in app.selectbox if s.label == "Planetary body").select(target.body).run()
            next(s for s in app.selectbox if s.label == "Measured reference region").select(
                target
            ).run()
            app.button[0].click().run()
            table = next(f.value for f in app.dataframe if "rank" in f.value.columns)
            expected = [r for r in verified_ranking(target, sites, config) if r["eligible"]]
            if (
                app.exception
                or table["site_name"].tolist() != [r["site_name"] for r in expected]
                or table["similarity_index"].tolist() != [r["similarity_index"] for r in expected]
            ):
                raise ValueError("Reference-specific UI parity failed")
        ui = {
            "checked": True,
            "real_rank_table_csv_parity": True,
            "body_switch_clears_stale_output": True,
            "moon_rankings_verified": lunar is not None,
            "all_reference_selectors_verified": len(references),
        }
    output = ROOT / "data/processed"
    (output / "real_analysis.csv").write_text(csv_payload, encoding="utf-8", newline="")
    summary = {
        "validated_utc": datetime.now(timezone.utc).isoformat(),
        "status": "numerically_verified_terrain_catalog"
        if len(sites) >= 10
        else "numerically_verified_limited_real_slice",
        "scientific_suitability_validated": False,
        "input_data_hash": rows[0]["input_data_hash"],
        "run_id": rows[0]["run_id"],
        "profiles": evidence,
        "rankings": results,
        "reference_analyses": all_references,
        "independent_ranking_order_verified": True,
        "candidate_count": len(sites),
        "eligible_candidate_count": sum(r["eligible"] for r in results),
        "ui": ui,
        "weight_sensitivity": sensitivity,
        "ablations": ablations,
        "limitations": [
            "Catalog-based shortlisting is not a worldwide terrain search or novelty assessment.",
            "Engineering weights/tolerances are uncalibrated.",
            "Independent arithmetic checks use the same measured grids.",
            "Earth publisher ZIP checksum remains unverified.",
            "Lunar profile and >=10-site acceptance require the release smoke check.",
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

    columns = min(3, len(grids))
    pairs = math.ceil(len(grids) / columns)
    fig, axes = plt.subplots(
        2 * pairs, columns, figsize=(6 * columns, 8 * pairs), squeeze=False, layout="constrained"
    )
    for index, (profile, z) in enumerate(grids):
        col, top = index % columns, 2 * (index // columns)
        height = np.ma.masked_invalid(z)
        image = axes[top, col].imshow(height, extent=(-30, 30, -30, 30), cmap="terrain")
        if profile.body == "Mars":
            datum = "MOLA GMM3 areoid"
        elif profile.body == "Moon":
            datum = "LOLA lunar reference sphere"
        elif any(source.startswith(("REMA_", "ARCTICDEM_")) for source in profile.source_ids):
            datum = "WGS84 ellipsoid"
        elif any(source.startswith("USGS_LAVA_BEDS") for source in profile.source_ids):
            datum = "USGS NAVD88"
        else:
            datum = "NASADEM EGM96 geoid"
        fig.colorbar(image, ax=axes[top, col], label=f"Elevation (m), {datum}", shrink=0.8)
        axes[top, col].set_title(f"{profile.body}: {profile.region_name}", fontsize=10)
        shade = LightSource(azdeg=315, altdeg=45).hillshade(z, dx=1000, dy=1000)
        axes[top + 1, col].imshow(
            np.ma.masked_invalid(shade), extent=(-30, 30, -30, 30), cmap="gray"
        )
        axes[top + 1, col].set_title(
            "Hillshade of measured 1 km grid; gaps are masked", fontsize=10
        )
        for ax in axes[top : top + 2, col]:
            ax.set_xlabel("Local easting (km)")
            ax.set_ylabel("Local northing (km)")
    for index in range(len(grids), pairs * columns):
        for ax in axes[2 * (index // columns) : 2 * (index // columns) + 2, index % columns]:
            ax.set_visible(False)
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
