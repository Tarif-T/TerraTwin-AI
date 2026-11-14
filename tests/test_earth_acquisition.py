"""Synthetic archives and responses test acquisition failure boundaries."""

import copy
import json
import zipfile

import pytest

from terratwin.config import ROOT
from terratwin.ingest import earth_catalog as acquisition


def test_all_planned_metadata_supports_distinct_single_tile_rois():
    from terratwin.config import read_yaml

    candidates = read_yaml(ROOT / "config/earth_candidates.yaml")["candidates"]
    centers = set()
    for candidate in candidates:
        tile = candidate["tile"]
        path = ROOT / f"data/metadata/evidence/NASADEM_HGT_{tile}.umm.json"
        item = json.loads(path.read_text())
        _, lat, lon, _, ring = acquisition.validate_metadata(item, tile)
        centers.add((lat, lon))
        assert len(ring) > 100
    assert len(centers) == 10


def test_mismatched_metadata_rejected():
    path = ROOT / "data/metadata/evidence/NASADEM_HGT_s24w069.umm.json"
    original = json.loads(path.read_text())
    for field, value in [
        ("GranuleUR", "NASADEM_HGT_n00e000"),
        ("CollectionReference", {"ShortName": "OTHER", "Version": "001"}),
    ]:
        item = copy.deepcopy(original)
        item["umm"][field] = value
        with pytest.raises(ValueError, match="mismatch"):
            acquisition.validate_metadata(item, "s24w069")
    item = copy.deepcopy(original)
    item["umm"]["RelatedUrls"] = [{"Type": "GET DATA", "URL": "https://example.org/fake.zip"}]
    with pytest.raises(ValueError, match="official archive"):
        acquisition.validate_metadata(item, "s24w069")


def test_zip_validation_and_existing_raw_preservation(tmp_path, monkeypatch):
    monkeypatch.setattr(acquisition, "SIZES", {"hgt": 4, "swb": 2, "num": 2})
    archive = tmp_path / "synthetic.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        for ext, size in acquisition.SIZES.items():
            stream.writestr(f"n00e000.{ext}", b"\x00" * size)
        stream.writestr("../escape.txt", "SYNTHETIC TEST ONLY")
    destination = tmp_path / "raw"
    hashes = acquisition.extract_archive(archive, destination, "n00e000")
    assert len(hashes) == 3
    assert not (tmp_path / "escape.txt").exists()
    assert acquisition.extract_archive(archive, destination, "n00e000") == hashes
    (destination / "n00e000.hgt").write_bytes(b"EDIT")
    with pytest.raises(ValueError, match="overwrite changed"):
        acquisition.extract_archive(archive, destination, "n00e000")
    assert (destination / "n00e000.hgt").read_bytes() == b"EDIT"


def test_incorrect_member_size_prevents_extraction(tmp_path, monkeypatch):
    monkeypatch.setattr(acquisition, "SIZES", {"hgt": 4})
    archive = tmp_path / "synthetic.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        stream.writestr("n00e000.hgt", b"\x00")
    with pytest.raises(ValueError, match="incorrect-size"):
        acquisition.extract_archive(archive, tmp_path / "raw", "n00e000")
    assert not (tmp_path / "raw").exists()


def test_unauthorized_download_leaves_no_partial_or_archive(tmp_path):
    class Response:
        status_code = 401

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class Session:
        def get(self, *args, **kwargs):
            return Response()

    destination = tmp_path / "synthetic.zip"
    with pytest.raises(PermissionError, match="authentication"):
        acquisition.download_archive(Session(), "https://example.org/synthetic", destination)
    assert not destination.exists()
    assert not destination.with_suffix(".zip.part").exists()


def test_registration_appends_provenance_and_is_idempotent(tmp_path, monkeypatch):
    import shutil

    import scripts.expand_earth_catalog as expansion
    from terratwin.config import read_yaml
    from terratwin.ingest.manifest import load_manifest

    # A temporary study copy: never register synthetic bytes in application data.
    for folder in ("config", "data/metadata/interpretations", "data/metadata/evidence"):
        (tmp_path / folder).mkdir(parents=True, exist_ok=True)
    for relative in (
        "config/earth_candidates.yaml",
        "data/metadata/interpretations/earth_n36w117.yaml",
        "data/metadata/evidence/NASADEM_HGT_s24w069.umm.json",
    ):
        shutil.copyfile(ROOT / relative, tmp_path / relative)
    monkeypatch.setattr(expansion, "ROOT", tmp_path)
    pipeline = read_yaml(ROOT / "config/pipeline.yaml")
    catalog = json.loads((ROOT / "data/catalog/earth_sites.geojson").read_text())
    sources = load_manifest(ROOT / "data/metadata/sources.csv")
    candidate = read_yaml(ROOT / "config/earth_candidates.yaml")["candidates"][0]
    # Begin with this candidate absent even when the real study has expanded.
    pipeline["jobs"] = [
        j for j in pipeline["jobs"] if j["identity"]["profile_id"] != "earth_s24w069_60km_v1"
    ]
    catalog["features"] = [
        f for f in catalog["features"] if f["properties"]["site_id"] != "earth_s24w069"
    ]
    sources = {
        key: value for key, value in sources.items() if not key.startswith("NASADEM_S24W069_")
    }
    item = json.loads(
        (tmp_path / "data/metadata/evidence/NASADEM_HGT_s24w069.umm.json").read_text()
    )
    archive = tmp_path / "synthetic-test-only.zip"
    archive.write_bytes(b"SYNTHETIC TEST ONLY")
    members = {ext: "0" * 64 for ext in acquisition.SIZES}
    original_jobs, original_sites, original_sources = (
        len(pipeline["jobs"]),
        len(catalog["features"]),
        len(sources),
    )
    expansion.register(candidate, item, members, archive, pipeline, catalog, sources)
    assert len(pipeline["jobs"]) == original_jobs + 1
    assert len(catalog["features"]) == original_sites + 1
    assert len(sources) == original_sources + 3
    job = pipeline["jobs"][-1]
    assert job["identity"]["centroid_lat"] == -23.5
    assert len(job["supporting_files"]) == 2
    assert len(catalog["features"][-1]["geometry"]["coordinates"][0]) > 100
    expansion.register(candidate, item, members, archive, pipeline, catalog, sources)
    assert len(pipeline["jobs"]) == original_jobs + 1
    with pytest.raises(ValueError, match="checksum changed"):
        expansion.register(
            candidate, item, {**members, "hgt": "1" * 64}, archive, pipeline, catalog, sources
        )


def test_incomplete_extracted_set_rejected(tmp_path):
    (tmp_path / "n00e000.hgt").write_bytes(b"SYNTHETIC TEST ONLY")
    with pytest.raises(ValueError, match="incorrect-size extracted"):
        acquisition.validate_extracted(tmp_path, "n00e000")


@pytest.mark.parametrize("water,valid", [(b"\x00\xff", True), (b"\x00\x01", False)])
def test_extracted_water_classes_and_checksums(tmp_path, monkeypatch, water, valid):
    import numpy as np
    import rasterio

    monkeypatch.setattr(acquisition, "SIZES", {"hgt": 4, "swb": 2, "num": 2})
    for ext, payload in {"hgt": b"\x00" * 4, "swb": water, "num": b"\x00" * 2}.items():
        (tmp_path / f"n00e000.{ext}").write_bytes(payload)

    class SyntheticDataset:
        width, height, count = 3601, 3601, 1
        crs = rasterio.crs.CRS.from_epsg(4326)
        dtypes = ("int16",)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def xy(self, *args):
            return 0.5, 0.5

        def read(self, *args, **kwargs):
            return np.ma.array([[0, 1]], mask=False)

    monkeypatch.setattr(rasterio, "open", lambda *a, **kw: SyntheticDataset())
    if valid:
        assert len(acquisition.validate_extracted(tmp_path, "n00e000")) == 3
    else:
        with pytest.raises(ValueError, match="SWB classes"):
            acquisition.validate_extracted(tmp_path, "n00e000")
