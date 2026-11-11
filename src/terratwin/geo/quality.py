from terratwin.geo.features import FeatureResult
from terratwin.models import FEATURES


def quality_reasons(result: FeatureResult, minimum_fraction: float = 0.90) -> list[str]:
    if not 0 < minimum_fraction <= 1:
        raise ValueError("Minimum valid fraction must be in (0, 1]")
    reasons = []
    if result.valid_cell_fraction < minimum_fraction:
        reasons.append(f"Valid raster coverage below {minimum_fraction:.0%}")
    for name in FEATURES:
        if getattr(result.measurements, name) is None:
            reasons.append(f"No valid samples for {name}")
    return reasons
