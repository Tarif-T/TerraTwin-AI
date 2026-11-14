"""Published-context regression checks, not an independent scientific evaluation."""

import json
from datetime import datetime, timezone

from streamlit.testing.v1 import AppTest

from terratwin.characterization import load_characterization
from terratwin.config import ROOT, load_scoring, read_yaml
from terratwin.datasets import load_prepared
from terratwin.science import export_assessments, load_evidence, rank_assessments
from terratwin.scoring.engine import rank_candidates


def validate():
    refs, sites, _ = load_prepared()
    config, bundle = load_scoring(), load_evidence(ROOT)
    contexts = load_characterization(ROOT)
    scenarios = read_yaml(ROOT / "config/research_scenarios.yaml")["scenarios"]
    target = next(p for p in refs if "tranquillitatis" in p.profile_id)
    runs = {}
    for reference in refs:
        terrain = rank_candidates(reference, sites, config)
        for preset in scenarios:
            scenario = {**preset, "terrain_scoring": config.model_dump(mode="json")}
            rows = rank_assessments(reference, sites, terrain, contexts, bundle, scenario)
            if rows != rank_assessments(reference, sites, terrain, contexts, bundle, scenario):
                raise ValueError("Research ranking is not deterministic")
            key = f"{reference.profile_id}_{preset['id']}"
            (ROOT / f"data/processed/{key}_evidence.csv").write_text(
                export_assessments(rows, reference, sites, bundle, scenario, contexts),
                encoding="utf-8",
                newline="",
            )
            runs[key] = rows
            if preset["id"] == "resource_research" and any(r["eligible"] for r in rows):
                raise ValueError("Unmeasured resource abundance passed the evidence gate")
    cave_rows = runs[f"{target.profile_id}_cave_robotics"]
    lava = next(r for r in cave_rows if r["site_id"] == "earth_lava_beds")
    if not lava["eligible"] or lava["domains"]["caves"]["similarity"] != 1:
        raise ValueError("Published volcanic subsurface baseline did not match cave setting")
    if lava["novelty_status"] != "known_baseline":
        raise ValueError("Published analog baseline incorrectly presented as novel")
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    next(s for s in app.selectbox if s.label == "Research target").select(target).run()
    next(s for s in app.selectbox if s.label == "Research scenario").select(scenarios[1]).run()
    next(b for b in app.button if b.label == "Run evidence assessment").click().run()
    if app.exception:
        raise ValueError(f"Research UI failed: {app.exception}")
    table = next(f.value for f in app.dataframe if "evidence_rank" in f.value.columns)
    if table["site_name"].tolist() != [r["site_name"] for r in cave_rows]:
        raise ValueError("Research UI candidate ordering disagrees with export")
    if table["evidence_index"].tolist() != [r["evidence_index"] for r in cave_rows]:
        raise ValueError("Research UI scores disagree with export")
    next(s for s in app.selectbox if s.label == "Research scenario").select(scenarios[2]).run()
    if app.get("download_button"):
        raise ValueError("Scenario switch retained stale export")
    next(b for b in app.button if b.label == "Run evidence assessment").click().run()
    if app.exception or not any("No candidate meets" in w.value for w in app.warning):
        raise ValueError("Resource UI did not disclose missing required measurements")
    report = dict(
        checked_utc=datetime.now(timezone.utc).isoformat(),
        status="published_context_regression_passed",
        independent_scientific_validation=False,
        cave_baseline=lava,
        reference_count=len(refs),
        earth_count=len(sites),
        scientific_sources=len(bundle.sources),
        observations=len(bundle.observations),
        research_runs=len(runs),
        ui_table_csv_parity=True,
        missing_resources_rejected=True,
        limitation="Published labels informed these regression checks. This is not held-out "
        "model evaluation, field validation, expert approval or proof of novelty.",
    )
    (ROOT / "data/processed/research_validation.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({k: v for k, v in report.items() if k != "cave_baseline"}, indent=2))


if __name__ == "__main__":
    validate()
