"""Bounded, reproducible acquisition proposals chosen before any similarity scores."""

import math


def plan_nasadem(bbox, budget=12):
    west, south, east, north = bbox
    if not all(math.isfinite(v) for v in bbox) or not (
        -180 <= west < east <= 180 and -56 <= south < north <= 60
    ):
        raise ValueError("Use a non-dateline box within NASADEM's 56 S to 60 N coverage")
    if not isinstance(budget, int) or not 1 <= budget <= 40:
        raise ValueError("Acquisition budget must be 1..40 tiles")
    # Lower-latitude single-tile ROIs keep 60 km footprints inside source coverage.
    # Higher latitudes require multi-tile intake or the existing PGC discovery workflow.
    centers = [
        (lat, lon)
        for lat in range(math.floor(south), math.ceil(north))
        for lon in range(math.floor(west), math.ceil(east))
        if south <= lat + 0.5 <= north and west <= lon + 0.5 <= east and abs(lat + 0.5) <= 40
    ]
    if not centers:
        raise ValueError("No supported single-tile centers; use ArcticDEM/REMA for polar regions")
    count = min(budget, len(centers))
    indices = [round(i * (len(centers) - 1) / max(1, count - 1)) for i in range(count)]
    candidates = []
    for i in indices:
        lat, lon = centers[i]
        tile = f"{'n' if lat >= 0 else 's'}{abs(lat):02}{'e' if lon >= 0 else 'w'}{abs(lon):03}"
        candidates.append(
            dict(
                tile=tile,
                region=f"Systematic NASADEM {tile} study",
                country="Not independently identified",
            )
        )
    return dict(
        selection_rationale="Evenly sampled latitude/longitude tile-center sequence within "
        "a bounded box, chosen before scoring. Ocean, missing source coverage and terrain "
        "QA may reject candidates. This is not a worldwide uniform-area sample or novelty proof.",
        search_bbox=list(bbox),
        candidates=candidates,
    )
