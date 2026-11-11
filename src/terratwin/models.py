"""Canonical scientific contracts; null means missing, never zero."""

import math
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

FEATURES = (
    "slope_median_deg",
    "relief_p90_p10_m",
    "roughness_local_std_m",
    "steep_fraction_15deg",
)
Body = Literal["Earth", "Mars", "Moon"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Measurements(Contract):
    slope_median_deg: float | None = Field(default=None, ge=0, lt=90)
    relief_p90_p10_m: float | None = Field(default=None, ge=0)
    roughness_local_std_m: float | None = Field(default=None, ge=0)
    steep_fraction_15deg: float | None = Field(default=None, ge=0, le=1)


class Profile(Measurements):
    profile_id: str = Field(min_length=1)
    body: Body
    region_name: str = Field(min_length=1)
    roi_id: str = Field(min_length=1)
    roi_size_km: float = Field(gt=0)
    common_grid_m: float = Field(gt=0)
    roughness_kernel_cells: int = Field(default=3, ge=3)
    valid_cell_fraction: float = Field(ge=0, le=1)
    qa_pass: bool
    source_ids: list[str] = Field(min_length=1)
    processing_version: str = Field(min_length=1)
    features_version: str = "features_v1"
    config_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    created_utc: datetime
    coordinate_convention: str = Field(min_length=1)
    processing_notes: str = Field(min_length=1)
    synthetic: bool = False
    site_id: str | None = None
    site_name: str | None = None
    country: str | None = None
    centroid_lat: float | None = Field(default=None, ge=-90, le=90)
    centroid_lon: float | None = Field(default=None, ge=-180, le=180)
    data_warning: str = ""

    @model_validator(mode="after")
    def validate_identity(self):
        if self.roughness_kernel_cells % 2 != 1:
            raise ValueError("Roughness kernel must be odd")
        if self.created_utc.tzinfo is None:
            raise ValueError("created_utc must include a timezone")
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("Duplicate source IDs")
        if self.body == "Earth" and any(
            getattr(self, key) is None
            for key in ("site_id", "site_name", "country", "centroid_lat", "centroid_lon")
        ):
            raise ValueError(
                "Earth profiles require site identity and verified centroid coordinates"
            )
        if self.qa_pass and not any(getattr(self, key) is not None for key in FEATURES):
            raise ValueError("QA cannot pass without measured features")
        return self


class SourceRecord(Contract):
    source_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    dataset: str = Field(min_length=1)
    version: str = Field(min_length=1)
    doi: str = ""
    product_url: HttpUrl
    download_url: HttpUrl
    accessed_utc: datetime
    license_or_rights: str = Field(min_length=1)
    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    planetary_body: Body
    horizontal_datum: str = Field(min_length=1)
    vertical_datum: str = Field(min_length=1)
    pixel_size_m: float = Field(gt=0)
    processing_version: str = Field(min_length=1)
    roi_id: str = Field(min_length=1)
    processing_notes: str = Field(min_length=1)

    @model_validator(mode="after")
    def timezone_required(self):
        if self.accessed_utc.tzinfo is None:
            raise ValueError("accessed_utc must include a timezone")
        return self


class ScoringConfig(Contract):
    version: str = "scoring_v1"
    weights: dict[str, float]
    tolerances: dict[str, float]
    minimum_coverage: float = Field(default=0.75, gt=0, le=1)
    minimum_valid_cell_fraction: float = Field(default=0.90, gt=0, le=1)

    @model_validator(mode="after")
    def validate_parameters(self):
        if set(self.weights) != set(FEATURES) or set(self.tolerances) != set(FEATURES):
            raise ValueError(
                "Weights and tolerances must contain exactly the four terrain features"
            )
        if any(not math.isfinite(w) or w < 0 for w in self.weights.values()):
            raise ValueError("Weights must be finite and nonnegative")
        total = math.fsum(self.weights.values())
        if not math.isfinite(total) or total <= 0:
            raise ValueError("Total weight must be finite and positive")
        if any(not math.isfinite(t) or t <= 0 for t in self.tolerances.values()):
            raise ValueError("Tolerances must be finite and positive")
        return self

    @property
    def normalized_weights(self):
        total = math.fsum(self.weights.values())
        return {name: self.weights[name] / total for name in FEATURES}
