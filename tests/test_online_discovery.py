"""Bounded online-discovery contracts with synthetic rasters confined to tmp_path."""

import csv
import hashlib
import io
import json
from datetime import datetime, timezone

import numpy as np
import pytest
import rasterio
from pydantic import ValidationError
from rasterio.transform import from_origin

import terratwin.discovery as discovery
from terratwin.discovery import (
    DiscoveryRequest,
    acquire,
    execute,
    load_completed_run,
    measure_tile,
    propose_tiles,
    write_json,
)

TILE = "Copernicus_DSM_COG_30_N35_00_W118_00_DEM"


@pytest.fixture
def discovery_request(reference, scoring_config):
    # Contract testing only: no synthetic fixture enters application data.
    return DiscoveryRequest(
        bbox=(-118, 34, -115, 36),
        budget=4,
        reference=reference.model_copy(update={"synthetic": False}),
        scoring=scoring_config,
        known_centers=[],
    )


@pytest.mark.parametrize(
    "updates",
    [
        dict(bbox=(-118, 40, -115, 60)),
        dict(bbox=(170, 0, -170, 5)),
        dict(bbox=(-118, float("nan"), -115, 36)),
        dict(budget=31),
        dict(budget=0),
    ],
)
def test_unsupported_search_rejected(discovery_request, updates):
    with pytest.raises(ValidationError):
        DiscoveryRequest.model_validate({**discovery_request.model_dump(), **updates})


def test_plan_excludes_existing_regions_before_scoring(discovery_request):
    index = "\n".join(
        [TILE, TILE, "malformed", TILE.replace("N35", "N34"), TILE.replace("W118", "W116")]
    )
    discovery_request.known_centers = [(-117.5, 35.5)]
    rows, available, excluded = propose_tiles(index, discovery_request)
    assert len(rows) == available == 2 and excluded == 1
    assert all(r["tile"] != TILE for r in rows)
    assert rows == propose_tiles(index, discovery_request)[0]


def test_cache_validates_receipt_and_source_md5(tmp_path, monkeypatch):
    payload = b"public test data"

    class Response:
        headers = {"ETag": hashlib.md5(payload).hexdigest()}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def raise_for_status(self):
            pass

        def iter_content(self, size):
            yield payload

    monkeypatch.setattr(discovery.requests, "get", lambda *a, **kw: Response())
    path = tmp_path / "test.bin"
    record = acquire("https://example.org/test", path)
    assert record["etag_md5_verified"] and acquire("https://example.org/test", path) == record
    path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="changed"):
        acquire("https://example.org/test", path)
    with pytest.raises(ValueError, match="limit"):
        acquire("https://example.org/large", tmp_path / "large", limit=1)


@pytest.fixture
def fake_assets(monkeypatch):
    water = {"value": 0}

    def fake_acquire(url, path, limit=12000000):
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix == ".txt":
            path.write_text(TILE + "\n")
        elif path.suffix == ".xml":
            path.write_text("<synthetic>WGS84-G1150; WGS 84 Geoid EGM08</synthetic>")
        elif path.suffix == ".tif":
            mask = "_WBM" in path.name
            values = (
                np.full((1200, 1200), water["value"], dtype="uint8")
                if mask
                else (
                    100
                    + np.arange(1200, dtype="float32")[:, None]
                    + np.zeros((1200, 1200), dtype="float32")
                )
            )
            with rasterio.open(
                path,
                "w",
                driver="GTiff",
                width=1200,
                height=1200,
                count=1,
                dtype=values.dtype,
                crs="EPSG:4326",
                transform=from_origin(-118 - 1 / 2400, 36 + 1 / 2400, 1 / 1200, 1 / 1200),
                compress="deflate",
            ) as ds:
                ds.write(values, 1)
        return dict(
            url=url,
            sha256=discovery.sha256_file(path),
            bytes=path.stat().st_size,
            etag_md5_verified=False,
            accessed_utc=datetime.now(timezone.utc).isoformat(),
        )

    monkeypatch.setattr(discovery, "acquire", fake_acquire)
    return water


def test_actual_metric_pipeline_and_water_qa(tmp_path, discovery_request, fake_assets):
    folder = tmp_path / "job"
    folder.mkdir()
    proposal = dict(tile=TILE, longitude=-117.5, latitude=35.5)
    profile, sources, footprint, audit = measure_tile(tmp_path, proposal, discovery_request, folder)
    assert profile.qa_pass and profile.valid_cell_fraction == 1
    assert len(sources) == 3 and footprint["properties"]["novelty"] == "unreviewed"
    assert audit["valid_elevation_count"] == 3600
    fake_assets["value"] = 2
    drowned, *_ = measure_tile(tmp_path, proposal, discovery_request, folder)
    assert not drowned.qa_pass and drowned.valid_cell_fraction == 0
    assert drowned.relief_p90_p10_m is None


def test_execute_saves_rankings_sources_and_empty_or_cancelled_runs(
    tmp_path, discovery_request, fake_assets
):
    folder = tmp_path / "job"
    folder.mkdir()
    write_json(folder / "request.json", discovery_request.model_dump(mode="json"))
    execute(tmp_path, folder)
    status = json.loads((folder / "status.json").read_text())
    result = json.loads((folder / "results.json").read_text())
    assert status["state"] == "completed" and status["eligible"] == 1
    rows = list(csv.DictReader(io.StringIO((folder / "rankings.csv").read_text())))
    assert float(rows[0]["similarity_index"]) == result["rankings"][0]["similarity_index"]
    assert result["search"]["novelty"] == "unreviewed"
    assert load_completed_run(folder) == result
    (folder / "rankings.csv").write_text("tampered")
    with pytest.raises(ValueError, match="changed"):
        load_completed_run(folder)
    (folder / "cancel.request").touch()
    execute(tmp_path, folder)
    assert json.loads((folder / "status.json").read_text())["state"] == "cancelled"
