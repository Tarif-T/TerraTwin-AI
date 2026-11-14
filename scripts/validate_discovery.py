"""Independently verify saved real geographic discovery and its app presentation."""

import argparse
import json
import re
from datetime import datetime, timezone

import rasterio
from streamlit.testing.v1 import AppTest

from scripts.validate_real_slice import independent_features, independent_ranking
from terratwin.config import ROOT
from terratwin.datasets import load_prepared
from terratwin.discovery import DiscoveryRequest, load_completed_run
from terratwin.models import FEATURES, Profile


def validate(run_id):
    folder = ROOT / "data/processed/discovery" / run_id
    result = load_completed_run(folder)
    request = DiscoveryRequest.model_validate(result["request"])
    profiles = [Profile.model_validate(p) for p in result["profiles"]]
    for p in profiles:
        audit = next(a for a in result["audits"] if a["site_id"] == p.site_id)
        with rasterio.open(folder / audit["analysis_grid"]) as ds:
            z = ds.read(1)
        expected = independent_features(z, 1000, 3)
        if any(
            abs(expected[k] - getattr(p, k)) > 1e-8 for k in FEATURES if expected[k] is not None
        ):
            raise ValueError("Independent discovery measurement disagreement")
    independent = independent_ranking(request.reference, profiles, request.scoring)
    if [r["site_id"] for r in independent] != [r["site_id"] for r in result["rankings"]]:
        raise ValueError("Independent discovery ranking order disagrees")
    for a, b in zip(independent, result["rankings"], strict=True):
        if a["eligible"] != b["eligible"] or a["rank"] != b["rank"]:
            raise ValueError("Independent discovery eligibility disagrees")
        if (
            a["similarity_index"] is not None
            and abs(a["similarity_index"] - b["similarity_index"]) > 1e-10
        ):
            raise ValueError("Independent discovery score disagrees")
    refs, _, _ = load_prepared()
    target = next(p for p in refs if p.profile_id == request.reference.profile_id)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=40).run()
    next(s for s in app.selectbox if s.label == "Discovery planetary target").select(target).run()
    next(s for s in app.selectbox if s.label == "Saved discovery search").select(run_id).run()
    next(b for b in app.button if b.label == "Open saved discovery search").click().run()
    if app.exception:
        raise ValueError(f"Discovery UI failed: {app.exception}")
    table = next(f.value for f in app.dataframe if "rank" in f.value.columns)
    if table["similarity_index"].tolist() != [r["similarity_index"] for r in result["rankings"]]:
        raise ValueError("Discovery table/CSV disagreement")
    if len(app.get("download_button")) != 3:
        raise ValueError("Discovery CSV/GeoJSON/evidence downloads are unavailable")
    other = next(p for p in refs if p.body != target.body)
    next(s for s in app.selectbox if s.label == "Discovery planetary target").select(other).run()
    if app.exception or app.get("download_button"):
        raise ValueError("Discovery retained results for wrong planetary target")
    report = dict(
        checked_utc=datetime.now(timezone.utc).isoformat(),
        run_id=run_id,
        measured=len(profiles),
        eligible=sum(r["eligible"] for r in result["rankings"]),
        independent_features=True,
        independent_ranking=True,
        ui_table_export_parity=True,
        target_switch_clears_results=True,
        novelty="unreviewed",
        scientific_suitability_validated=False,
    )
    (folder / "validation.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-f0-9]{32}", args.run):
        parser.error("Invalid run ID")
    validate(args.run)
