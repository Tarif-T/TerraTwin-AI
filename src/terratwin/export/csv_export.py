import csv
import io
import json

from terratwin.config import content_hash
from terratwin.models import FEATURES, Profile, ScoringConfig

ALIASES = dict(zip(FEATURES, ("slope", "relief", "roughness", "steep_fraction")))


def export_analysis(
    reference: Profile, sites: list[Profile], results: list[dict], config: ScoringConfig
) -> str:
    input_hash = content_hash(
        {
            "reference": reference.model_dump(mode="json"),
            "sites": [s.model_dump(mode="json") for s in sorted(sites, key=lambda s: s.site_id)],
        }
    )
    run_id = content_hash({"input": input_hash, "config": config.model_dump()})[:16]
    rows = []
    for result in results:
        row = {
            k: result[k]
            for k in (
                "site_id",
                "rank",
                "similarity_index",
                "feature_coverage",
                "eligible",
                "warning",
            )
        }
        row.update(
            run_id=run_id,
            reference_profile_id=reference.profile_id,
            scoring_version=config.version,
            input_data_hash=input_hash,
            source_ids=";".join(result["source_ids"]),
            processing_version=reference.processing_version,
            common_grid_m=reference.common_grid_m,
            roi_size_km=reference.roi_size_km,
            roughness_kernel_cells=reference.roughness_kernel_cells,
            minimum_coverage=config.minimum_coverage,
            minimum_valid_cell_fraction=config.minimum_valid_cell_fraction,
            reference_feature_coverage=result["reference_feature_coverage"],
            weights=json.dumps(config.normalized_weights, sort_keys=True),
            tolerances=json.dumps(config.tolerances, sort_keys=True),
        )
        for name in FEATURES:
            row[f"{ALIASES[name]}_similarity"] = result["components"][name]["similarity"]
        rows.append(row)
    if not rows:
        return ""
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()
