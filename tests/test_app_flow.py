"""SYNTHETIC test-only app sessions; never write demo data to production folders."""

import csv
import io
import socket

import pytest
from conftest import changed
from streamlit.testing.v1 import AppTest

import terratwin.datasets
import terratwin.export.csv_export
from terratwin.config import ROOT
from terratwin.models import SourceRecord


def selector(app, label):
    return next(widget for widget in app.selectbox if widget.label == label)


@pytest.fixture
def app_flow(monkeypatch, reference, earth_sites):
    mars = changed(reference, source_ids=["SYNTHETIC_MARS_SOURCE"])
    moon = changed(
        reference,
        profile_id="SYNTHETIC_MOON",
        body="Moon",
        region_name="Synthetic Moon test",
        source_ids=["SYNTHETIC_MOON_SOURCE"],
    )
    sites = [changed(site, source_ids=["SYNTHETIC_EARTH_SOURCE"]) for site in earth_sites]
    # Exercise a rejected site alongside eligible sites.
    sites[-1] = changed(sites[-1], slope_median_deg=None, relief_p90_p10_m=None)
    sources = {}
    for body in ("Mars", "Moon", "Earth"):
        source_id = f"SYNTHETIC_{body.upper()}_SOURCE"
        sources[source_id] = SourceRecord(
            source_id=source_id,
            provider="SYNTHETIC TEST ONLY",
            dataset="SYNTHETIC TEST ONLY",
            version="test",
            product_url="https://example.org/synthetic-test-only",
            download_url="https://example.org/synthetic-test-only",
            accessed_utc=reference.created_utc,
            license_or_rights="SYNTHETIC TEST ONLY",
            checksum_sha256="0" * 64,
            planetary_body=body,
            horizontal_datum="SYNTHETIC",
            vertical_datum="SYNTHETIC",
            pixel_size_m=1000,
            processing_version="terrain_v1",
            roi_id="SYNTHETIC_ROI",
            processing_notes="SYNTHETIC TEST ONLY",
        )
    assert all(profile.synthetic for profile in [mars, moon, *sites])
    monkeypatch.setattr(terratwin.datasets, "load_prepared", lambda: ([mars, moon], sites, sources))

    # The Python app must not contact a service to rank or export prepared profiles.
    def no_network(*args, **kwargs):
        raise AssertionError("Application attempted a network connection")

    monkeypatch.setattr(socket, "create_connection", no_network)
    captured_exports = []
    original_export = terratwin.export.csv_export.export_analysis

    def capture_export(*args, **kwargs):
        result = original_export(*args, **kwargs)
        captured_exports.append(result)
        return result

    monkeypatch.setattr(terratwin.export.csv_export, "export_analysis", capture_export)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    assert not app.exception
    return app, captured_exports


def test_rank_evidence_rejected_sites_and_csv_parity(app_flow):
    app, exports = app_flow
    assert not app.button[0].disabled
    app.button[0].click().run()
    assert not app.exception
    ranked = next(frame.value for frame in app.dataframe if "rank" in frame.value.columns)
    assert len(ranked) == 11
    assert ranked.iloc[0]["similarity_index"] == pytest.approx(100)
    assert "Synthetic site 11" not in ranked["site_name"].tolist()
    assert any("Insufficient coverage or quality (1)" == e.label for e in app.expander)
    assert len(app.get("download_button")) == 1
    rows = list(csv.DictReader(io.StringIO(exports[-1])))
    assert len(rows) == 12
    for displayed, exported in zip(ranked.to_dict("records"), rows):
        assert displayed["similarity_index"] == float(exported["similarity_index"])
        assert displayed["feature_coverage"] == float(exported["feature_coverage"])
        assert exported["reference_profile_id"] == "SYNTHETIC_MARS"
    assert rows[-1]["eligible"] == "False"
    assert rows[-1]["rank"] == ""
    assert any("SYNTHETIC_MARS_SOURCE" in md.value for md in app.markdown)


def test_select_candidate_updates_evidence(app_flow):
    app, _ = app_flow
    app.button[0].click().run()
    selector(app, "Inspect candidate evidence").select_index(1).run()
    assert not app.exception
    evidence = next(frame.value for frame in app.dataframe if "site_value" in frame.value.columns)
    assert evidence.loc["slope_median_deg", "site_value"] == 11
    score = next(
        metric.value for metric in app.metric if metric.label == "Terrain similarity index"
    )
    assert score != "100.00 / 100"


def test_switch_body_clears_stale_results_and_exports_moon(app_flow):
    app, exports = app_flow
    app.button[0].click().run()
    selector(app, "Planetary body").select("Moon").run()
    assert not app.exception
    assert not any(metric.label == "Terrain similarity index" for metric in app.metric)
    assert len(app.get("download_button")) == 0
    app.button[0].click().run()
    assert not app.exception
    rows = list(csv.DictReader(io.StringIO(exports[-1])))
    assert all(row["reference_profile_id"] == "SYNTHETIC_MOON" for row in rows)


def test_no_eligible_candidates_explained_and_exportable(monkeypatch, reference, earth_sites):
    # No source detail pane is opened when all candidates fail coverage.
    sites = [changed(site, qa_pass=False) for site in earth_sites]
    monkeypatch.setattr(terratwin.datasets, "load_prepared", lambda: ([reference], sites, {}))
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    app.button[0].click().run()
    assert not app.exception
    assert any("No eligible candidates. 12 rejected" in info.value for info in app.info)
    assert len(app.get("download_button")) == 1
