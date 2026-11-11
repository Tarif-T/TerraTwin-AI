import hashlib
import json
from pathlib import Path

import yaml

from terratwin.models import ScoringConfig

ROOT = Path(__file__).resolve().parents[2]


def read_yaml(path: str | Path) -> dict:
    with Path(path).open(encoding="utf-8") as stream:
        value = yaml.safe_load(stream)
    if not isinstance(value, dict):
        raise ValueError(f"Expected a YAML mapping in {path}")
    return value


def load_scoring(path: str | Path = ROOT / "config/scoring_v1.yaml") -> ScoringConfig:
    return ScoringConfig.model_validate(read_yaml(path))


def content_hash(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
