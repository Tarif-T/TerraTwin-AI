"""Versioned engineering presets; no claims of calibrated mission suitability."""

from terratwin.models import ScoringConfig


def mission_scoring(base, preset):
    version = (
        base.version if preset["id"] == "terrain_baseline" else f"{base.version}_{preset['id']}"
    )
    return ScoringConfig.model_validate(
        {**base.model_dump(), "weights": preset["weights"], "version": version}
    )
