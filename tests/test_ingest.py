"""Temporary SYNTHETIC GeoTIFF fixtures verify mechanics, not real PDS interpretation."""

from datetime import datetime, timezone

import numpy as np
import pytest
import rasterio
import yaml
from rasterio.transform import from_origin

from terratwin.geo.coordinates import validate_body_crs
from terratwin.geo.rasters import metric_roi
from terratwin.ingest.earth_loader import load_nasadem
from terratwin.ingest.manifest import sha256_file
from terratwin.ingest.raster_input import RasterInterpretation
from terratwin.models import SourceRecord

MARS_CRS = "+proj=eqc +R=3396190 +units=m +type=crs"


@pytest.fixture
def local_input(tmp_path):
    path = tmp_path / "SYNTHETIC.tif"
    data = np.full((12, 12), 50, dtype="int16")
    data[0, 0] = -9999
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        width=12,
        height=12,
        count=1,
        dtype="int16",
        crs="EPSG:32631",
        transform=from_origin(500000, 12000, 1000, 1000),
        nodata=-9999,
    ) as dst:
        dst.write(data, 1)
    label = tmp_path / "SYNTHETIC_PRODUCT.txt"
    label.write_text("SYNTHETIC TEST METADATA ONLY", encoding="utf-8")
    metadata = dict(
        body="Earth",
        product_type="topographic_elevation",
        source_crs="EPSG:32631",
        horizontal_datum="WGS84",
        vertical_datum="SYNTHETIC",
        latitude_type="geodetic",
        longitude_convention="-180_180",
        sample_unit="m",
        scale=2,
        offset=100,
        nodata=-9999,
        label_path=label.name,
        label_sha256=sha256_file(label),
        interpretation_evidence="SYNTHETIC TEST ONLY; manually specified scale and offset",
    )
    sidecar = tmp_path / "SYNTHETIC.yaml"
    sidecar.write_text(yaml.safe_dump(metadata), encoding="utf-8")
    source = SourceRecord(
        source_id="SYNTHETIC_SOURCE",
        provider="SYNTHETIC",
        dataset="NASADEM_HGT",
        version="001",
        product_url="https://example.org/synthetic",
        download_url="https://example.org/synthetic.tif",
        accessed_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
        license_or_rights="SYNTHETIC TEST ONLY",
        checksum_sha256=sha256_file(path),
        planetary_body="Earth",
        horizontal_datum="WGS84",
        vertical_datum="SYNTHETIC",
        pixel_size_m=1000,
        processing_version="terrain_v1",
        roi_id="SYNTHETIC_ROI",
        processing_notes="SYNTHETIC TEST ONLY",
    )
    return path, sidecar, source, metadata


def test_local_adapter_scaling_mask_and_metric_grid(local_input):
    path, sidecar, source, _ = local_input
    metadata = load_nasadem(path, sidecar, source)
    array = metric_roi(path, metadata, "EPSG:32631", (500000, 0, 512000, 12000), 1000, 12)
    assert np.isnan(array[0, 0])
    assert np.all(array[np.isfinite(array)] == 200)


def test_coarser_source_cannot_be_upsampled(local_input):
    path, sidecar, source, _ = local_input
    metadata = load_nasadem(path, sidecar, source)
    with pytest.raises(ValueError, match="coarser"):
        metric_roi(path, metadata, "EPSG:32631", (500000, 0, 512000, 12000), 500, 12)


def test_checksum_mismatch_rejected(local_input):
    path, sidecar, source, _ = local_input
    source = source.model_copy(update={"checksum_sha256": "0" * 64})
    with pytest.raises(ValueError, match="checksum"):
        load_nasadem(path, sidecar, source)


def test_original_label_required(local_input):
    path, sidecar, source, metadata = local_input
    (sidecar.parent / metadata["label_path"]).unlink()
    with pytest.raises(FileNotFoundError):
        load_nasadem(path, sidecar, source)


@pytest.mark.parametrize("body", ["Moon", "Mars"])
def test_earth_crs_forbidden_on_other_bodies(body):
    with pytest.raises(ValueError, match="ellipsoid"):
        validate_body_crs("EPSG:4326", body)


def test_planetary_metric_crs():
    assert validate_body_crs(MARS_CRS, "Mars", metric=True).is_projected
    with pytest.raises(ValueError, match="metre"):
        validate_body_crs("EPSG:4326", "Earth", metric=True)


def test_ambiguous_sample_type_rejected(local_input):
    _, _, _, metadata = local_input
    with pytest.raises(ValueError):
        RasterInterpretation.model_validate({**metadata, "product_type": "planet_radius"})


def test_synthetic_local_pipeline_roundtrip_only_in_temporary_directory(local_input, tmp_path):
    import csv
    import json

    from pyproj import Transformer

    from terratwin.datasets import load_prepared
    from terratwin.pipeline import build_profiles

    path, sidecar, source, _ = local_input
    metadata_dir = tmp_path / "data/metadata"
    metadata_dir.mkdir(parents=True)
    source_row = source.model_dump(mode="json")
    with (metadata_dir / "sources.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(source_row))
        writer.writeheader()
        writer.writerow(source_row)
    transform = Transformer.from_crs("EPSG:32631", "EPSG:4326", always_xy=True)
    centroid_lon, centroid_lat = transform.transform(506000, 6000)
    ring = [
        transform.transform(x, y)
        for x, y in (
            (500000, 0),
            (512000, 0),
            (512000, 12000),
            (500000, 12000),
            (500000, 0),
        )
    ]
    identity = dict(
        profile_id="SYNTHETIC_PROFILE",
        region_name="SYNTHETIC TEST ONLY",
        roi_id=source.roi_id,
        site_id="SYNTHETIC_SITE",
        site_name="SYNTHETIC TEST ONLY",
        country="TEST ONLY",
        centroid_lat=centroid_lat,
        centroid_lon=centroid_lon,
    )
    catalog_dir = tmp_path / "data/catalog"
    catalog_dir.mkdir(parents=True)
    (catalog_dir / "earth_sites.geojson").write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Polygon", "coordinates": [ring]},
                        "properties": {
                            **identity,
                            "seed_or_candidate": "test",
                            "reason_selected": "SYNTHETIC TEST ONLY",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    config = dict(
        processing_version="terrain_v1",
        features_version="features_v1",
        common_grid_m=1000,
        roi_size_km=12,
        roughness_kernel_cells=3,
        minimum_valid_cell_fraction=0.9,
        jobs=[
            dict(
                raster_path=str(path),
                interpretation_path=str(sidecar),
                source_id=source.source_id,
                destination_crs="EPSG:32631",
                bounds_m=[500000, 0, 512000, 12000],
                identity=identity,
            )
        ],
    )
    config_path = tmp_path / "pipeline.yaml"
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    profiles = build_profiles(config_path, root=tmp_path)
    assert profiles[0].qa_pass
    assert profiles[0].relief_p90_p10_m == 0
    references, sites, sources = load_prepared(root=tmp_path)
    assert references == []
    assert sites[0].profile_id == "SYNTHETIC_PROFILE"
    assert source.source_id in sources
    report = json.loads((tmp_path / "data/processed/processing_manifest.json").read_text())
    assert report["profiles"][0]["valid_slope_count"] > 0
    # Release protection: explicit synthetic profiles can never enter app data.
    import pandas as pd

    output = tmp_path / "data/processed/earth_profiles.parquet"
    frame = pd.read_parquet(output)
    frame["synthetic"] = True
    frame.to_parquet(output, index=False)
    with pytest.raises(ValueError, match="Synthetic"):
        load_prepared(root=tmp_path)


def test_partial_ground_aggregate_remains_masked(local_input):
    path, sidecar, source, _ = local_input
    metadata = load_nasadem(path, sidecar, source)
    array = metric_roi(path, metadata, "EPSG:32631", (500000, 0, 512000, 12000), 2000, 12)
    assert np.isnan(array[0, 0])
    assert np.isfinite(array[1:, 1:]).all()


def test_external_water_mask_is_applied_and_checksummed(local_input):
    path, sidecar, source, metadata = local_input
    mask = np.zeros((12, 12), dtype="uint8")
    mask[3, 3] = 255
    mask_path = sidecar.parent / "SYNTHETIC.swb"
    mask.tofile(mask_path)
    metadata.update(mask_path=mask_path.name, mask_sha256=sha256_file(mask_path))
    sidecar.write_text(yaml.safe_dump(metadata), encoding="utf-8")
    parsed = load_nasadem(path, sidecar, source)
    z = metric_roi(
        path,
        parsed,
        "EPSG:32631",
        (500000, 0, 512000, 12000),
        1000,
        12,
        interpretation_path=sidecar,
    )
    assert np.isnan(z[3, 3])
    assert z[3, 4] == 200
    mask[3, 3] = 0
    mask.tofile(mask_path)
    with pytest.raises(ValueError, match="mask checksum"):
        load_nasadem(path, sidecar, source)


def test_pds_extra_bytes_rejected_before_measurement(local_input, monkeypatch):
    from types import SimpleNamespace

    path, sidecar, source, metadata = local_input
    image = sidecar.parent / "SYNTHETIC.img"
    image.write_bytes(b"\x00" * 34)  # Declared 4x4 int16 array must have exactly 32 bytes.
    metadata["raster_data_path"] = image.name
    sidecar.write_text(yaml.safe_dump(metadata), encoding="utf-8")
    source = source.model_copy(update={"checksum_sha256": sha256_file(image)})

    class Reader:
        def __enter__(self):
            return SimpleNamespace(
                count=1, driver="PDS4", files=[str(image)], width=4, height=4, dtypes=["int16"]
            )

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(rasterio, "open", lambda *args, **kwargs: Reader())
    with pytest.raises(ValueError, match="byte count"):
        load_nasadem(path, sidecar, source)


def test_catalog_footprint_matches_analysis_bounds():
    from terratwin.geo.regions import geographic_ring, validate_earth_footprint

    bounds = (500000, 0, 512000, 12000)
    geometry = {"type": "Polygon", "coordinates": [geographic_ring("EPSG:32631", "Earth", bounds)]}
    validate_earth_footprint(geometry, "EPSG:32631", bounds)
    with pytest.raises(ValueError, match="footprint"):
        validate_earth_footprint(geometry, "EPSG:32631", (500000, 0, 506000, 12000))
