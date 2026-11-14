"""Strict local intake: audited interpretation sidecar plus original product metadata.

This deliberately does not guess scientific semantics from file extensions. The
operator must verify each interpretation against the original label/product guide.
GDAL handles supported label formats; unsupported labels fail closed.
"""

from pathlib import Path
from typing import Literal

import numpy as np
import rasterio
from pydantic import Field, model_validator

from terratwin.config import read_yaml
from terratwin.geo.coordinates import validate_body_crs
from terratwin.ingest.manifest import sha256_file
from terratwin.models import Body, Contract, SourceRecord


class RasterInterpretation(Contract):
    body: Body
    product_type: Literal["topographic_elevation"]
    source_crs: str
    horizontal_datum: str = Field(min_length=1)
    vertical_datum: str = Field(min_length=1)
    latitude_type: Literal["planetocentric", "planetographic", "geodetic"]
    longitude_convention: Literal["-180_180", "0_360"]
    sample_unit: Literal["m"]
    scale: float
    offset: float
    value_interpretation: Literal["standard", "lola_height"] = "standard"
    latitude_bounds_deg: tuple[float, float] = (-56, 60)
    nodata: float | None
    raster_data_path: str | None = None
    mask_path: str | None = None
    mask_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    mask_land_value: int = Field(default=0, ge=0, le=255)
    label_path: str = Field(min_length=1)
    label_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    interpretation_evidence: str = Field(min_length=20)

    @model_validator(mode="after")
    def valid_scale(self):
        if self.scale == 0:
            raise ValueError("Elevation scale cannot be zero")
        if not -90 <= self.latitude_bounds_deg[0] < self.latitude_bounds_deg[1] <= 90:
            raise ValueError("Invalid source latitude coverage")
        if (self.mask_path is None) != (self.mask_sha256 is None):
            raise ValueError("A ground mask requires both a path and checksum")
        validate_body_crs(self.source_crs, self.body)
        return self


def validate_local_raster(
    raster_path: Path,
    interpretation_path: Path,
    source: SourceRecord,
    body: str,
) -> RasterInterpretation:
    metadata = RasterInterpretation.model_validate(read_yaml(interpretation_path))
    if metadata.body != body or source.planetary_body != body:
        raise ValueError("Source, interpretation and requested body must agree")
    if source.horizontal_datum != metadata.horizontal_datum:
        raise ValueError("Horizontal datum differs from source manifest")
    if source.vertical_datum != metadata.vertical_datum:
        raise ValueError("Vertical datum differs from source manifest")
    data_path = (
        (interpretation_path.parent / metadata.raster_data_path).resolve()
        if metadata.raster_data_path
        else raster_path
    )
    if sha256_file(data_path) != source.checksum_sha256:
        raise ValueError("Raster checksum does not match source manifest")
    label = (interpretation_path.parent / metadata.label_path).resolve()
    if sha256_file(label) != metadata.label_sha256:
        raise ValueError("Original label/product metadata checksum does not match")
    if label.stat().st_size == 0:
        raise ValueError("Original label/product metadata is empty")
    if metadata.value_interpretation == "lola_height":
        validate_lola_height(label, metadata)
    with rasterio.open(raster_path) as dataset:
        if metadata.value_interpretation == "lola_height" and (
            dataset.driver != "PDS4" or raster_path.resolve() != label.resolve()
        ):
            raise ValueError("LOLA height conversion must read the audited original PDS4 label")
        if dataset.count != 1:
            raise ValueError("Intake requires a verified single-band topographic elevation product")
        if dataset.driver in ("PDS", "PDS4"):
            if metadata.raster_data_path is None:
                raise ValueError(
                    "PDS intake requires the underlying image path for integrity checks"
                )
            if data_path.resolve() not in {Path(name).resolve() for name in dataset.files}:
                raise ValueError("PDS label does not reference the declared image")
            expected_bytes = dataset.width * dataset.height * np.dtype(dataset.dtypes[0]).itemsize
            if data_path.stat().st_size != expected_bytes:
                raise ValueError(
                    "PDS image byte count does not match its declared single-band array"
                )
        if metadata.mask_path:
            mask_path = (interpretation_path.parent / metadata.mask_path).resolve()
            if sha256_file(mask_path) != metadata.mask_sha256:
                raise ValueError("Ground mask checksum mismatch")
            if mask_path.stat().st_size != dataset.width * dataset.height:
                raise ValueError("Ground mask must contain one uint8 value per source sample")
        if dataset.crs is None:
            raise ValueError("GDAL cannot decode source CRS; prepare a verified labeled product")
        expected = validate_body_crs(metadata.source_crs, body)
        actual = validate_body_crs(dataset.crs.to_wkt(), body)
        if not actual.equals(expected, ignore_axis_order=True):
            raise ValueError("Raster CRS differs from audited interpretation")
        if dataset.transform.b != 0 or dataset.transform.d != 0:
            raise ValueError("Rotated source grids require an explicitly validated adapter")
        if dataset.transform.a <= 0 or dataset.transform.e >= 0:
            raise ValueError("Only east-right, north-up source grids are supported")
        if dataset.nodata is not None and dataset.nodata != metadata.nodata:
            raise ValueError("Raster nodata differs from audited interpretation")
        if dataset.scales[0] != 1 and dataset.scales[0] != metadata.scale:
            raise ValueError("Raster scale differs from audited interpretation")
        if (
            dataset.offsets[0] != 0
            and dataset.offsets[0] != metadata.offset
            and not (
                metadata.value_interpretation == "lola_height" and dataset.offsets[0] == 1737400.0
            )
        ):
            raise ValueError("Raster offset differs from audited interpretation")
    return metadata


def validate_lola_height(label, metadata):
    """LOLA labels distinguish HEIGHT=DN*0.5 from RADIUS=DN*0.5+1737400."""
    from xml.etree import ElementTree as ET

    root = ET.parse(label).getroot()
    ns = {"p": "http://pds.nasa.gov/pds4/pds/v1"}
    identifier = root.findtext("p:Identification_Area/p:logical_identifier", namespaces=ns)
    element = root.find(".//p:Array_2D_Image/p:Element_Array", ns)
    if not identifier or not identifier.startswith("urn:nasa:pds:lro_lola_rdr:data_gridded:ldem_"):
        raise ValueError("LOLA height interpretation requires an original LOLA PDS4 label")
    if element is None or (
        element.findtext("p:data_type", namespaces=ns) != "SignedLSB2"
        or float(element.findtext("p:scaling_factor", namespaces=ns)) != 0.5
        or float(element.findtext("p:value_offset", namespaces=ns)) != 1737400
    ):
        raise ValueError("Unexpected LOLA sample representation")
    if (
        metadata.body != "Moon"
        or metadata.scale != 0.5
        or metadata.offset != 0
        or metadata.vertical_datum != "Height above 1737400 m lunar reference sphere"
        or metadata.nodata is not None
    ):
        raise ValueError("LOLA HEIGHT conversion must preserve the documented reference sphere")
