"""Deterministic, scale-compatible terrain comparison with explicit missingness."""

import math

from terratwin.models import FEATURES, Profile, ScoringConfig


def rank_candidates(reference: Profile, sites: list[Profile], config: ScoringConfig) -> list[dict]:
    if reference.body not in ("Moon", "Mars"):
        raise ValueError("Reference must be a Moon or Mars profile")
    if not reference.qa_pass or reference.valid_cell_fraction < config.minimum_valid_cell_fraction:
        raise ValueError("Reference data failed raster quality checks")
    ids = [site.site_id for site in sites]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate Earth site IDs")
    weights = config.normalized_weights
    missing_reference = [name for name in FEATURES if getattr(reference, name) is None]
    if not any(getattr(reference, name) is not None and weights[name] > 0 for name in FEATURES):
        raise ValueError("Reference has no available positively weighted features")
    results = []
    for site in sites:
        if site.body != "Earth":
            raise ValueError("Candidates must be Earth profiles")
        for field in (
            "common_grid_m",
            "roi_size_km",
            "roughness_kernel_cells",
            "features_version",
        ):
            if getattr(reference, field) != getattr(site, field):
                raise ValueError(f"Incompatible {field} for {site.site_id}")
        components = {}
        for name in FEATURES:
            p, e = getattr(reference, name), getattr(site, name)
            similarity = (
                math.exp(-abs(e - p) / config.tolerances[name])
                if p is not None and e is not None
                else None
            )
            components[name] = {
                "reference_value": p,
                "site_value": e,
                "similarity": similarity,
                "weight": weights[name],
                "contribution": weights[name] * similarity if similarity is not None else None,
                "missing": similarity is None,
            }
        coverage = math.fsum(c["weight"] for c in components.values() if not c["missing"])
        score = (
            100
            * math.fsum(c["contribution"] for c in components.values() if not c["missing"])
            / coverage
            if coverage > 0
            else None
        )
        warnings = [site.data_warning] if site.data_warning else []
        if reference.data_warning:
            warnings.append("Reference: " + reference.data_warning)
        if missing_reference:
            warnings.append("Missing reference features: " + ", ".join(missing_reference))
        if coverage < config.minimum_coverage:
            warnings.append("Insufficient weighted feature coverage")
        qa_ok = site.qa_pass and site.valid_cell_fraction >= config.minimum_valid_cell_fraction
        if not qa_ok:
            warnings.append("Insufficient raster quality")
        results.append(
            {
                "site_id": site.site_id,
                "site_name": site.site_name,
                "similarity_index": score,
                "feature_coverage": coverage,
                "reference_feature_coverage": math.fsum(
                    weights[n] for n in FEATURES if getattr(reference, n) is not None
                ),
                "eligible": coverage >= config.minimum_coverage and qa_ok,
                "components": components,
                "source_ids": sorted(set(reference.source_ids + site.source_ids)),
                "warning": "; ".join(warnings),
            }
        )
    results.sort(
        key=lambda r: (
            not r["eligible"],
            -(r["similarity_index"] if r["similarity_index"] is not None else -1),
            -r["feature_coverage"],
            r["site_id"],
        )
    )
    rank = 0
    for result in results:
        if result["eligible"]:
            rank += 1
            result["rank"] = rank
        else:
            result["rank"] = None
    return results
