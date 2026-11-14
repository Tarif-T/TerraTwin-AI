"""Evidence compatibility, missingness gates and review integrity."""

import json
import shutil
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from terratwin.config import ROOT, read_yaml
from terratwin.science import (
    EvidenceBundle,
    Observation,
    Review,
    assess_candidate,
    compare_observations,
    export_assessments,
    import_evidence,
    load_evidence,
    load_reviews,
    rank_assessments,
    save_review,
)
from terratwin.scoring.engine import rank_candidates


def observation(**changes):
    return Observation.model_validate(
        dict(
            observation_id="test",
            subject_id="test",
            domain="caves",
            quantity="pit_depth_m",
            value=105,
            unit="m",
            statistic="depth_below_funnel",
            scope="named_site",
            status="reported",
            source_ids=["test"],
            interpretation="Synthetic observation for compatibility tests only.",
            **changes,
        )
    )


@pytest.mark.parametrize(
    "difference",
    [
        dict(quantity="cave_length_m"),
        dict(unit="km"),
        dict(statistic="total_depth"),
        dict(scope="study_region"),
        dict(status="candidate"),
    ],
)
def test_incompatible_observations_not_compared(difference):
    one = observation()
    two = Observation.model_validate({**one.model_dump(), **difference})
    assert compare_observations([one], [two], "pit_depth_m", 100)["similarity"] is None


def test_exact_confirmed_observations_match():
    one = observation()
    assert compare_observations([one], [one], "pit_depth_m", 100)["similarity"] == 1
    with pytest.raises(ValueError):
        compare_observations([one], [one], "pit_depth_m", 0)


@pytest.mark.parametrize(
    "change",
    [
        dict(status="unknown"),
        dict(value=-1),
        dict(quantity="water_ice_mass_fraction", value=2, unit="fraction"),
        dict(value=float("nan")),
    ],
)
def test_invalid_observations_rejected(change):
    with pytest.raises(ValidationError):
        Observation.model_validate({**observation().model_dump(), **change})


def test_resource_gate_and_zero_support(reference, earth_sites, scoring_config):
    bundle = EvidenceBundle(version="test", sources=[], observations=[])
    scenario = read_yaml(ROOT / "config/research_scenarios.yaml")["scenarios"][2]
    terrain = rank_candidates(reference, earth_sites, scoring_config)
    rows = rank_assessments(reference, earth_sites, terrain, {}, bundle, scenario)
    assert all(not r["eligible"] and r["evidence_rank"] is None for r in rows)
    assert all("resources" in r["missing_required_domains"] for r in rows)
    zero = {**scenario, "weights": dict(terrain=0, geology=0, environment=0, resources=1, caves=0)}
    result = assess_candidate(reference, earth_sites[0], terrain[0], {}, bundle, zero)
    assert result["evidence_index"] is None and result["comparison_coverage"] == 0
    assert "input_hash" in export_assessments(rows, reference, earth_sites, bundle, scenario, {})


def test_source_tampering_fails(tmp_path):
    bundle = load_evidence(ROOT)
    assert len(bundle.sources) >= 10
    folder = tmp_path / "data/metadata"
    folder.mkdir(parents=True)
    data = json.loads(bundle.model_dump_json())
    data["sources"][0]["snapshot_path"] = "../outside.json"
    (folder / "science_evidence.json").write_text(json.dumps(data))
    with pytest.raises(ValueError, match="workspace"):
        load_evidence(tmp_path)


def test_review_scope_and_append_only_records(tmp_path):
    review = Review(
        subject_id="site",
        reviewer="Test reviewer",
        reviewed_utc=datetime.now(timezone.utc),
        kind="literature",
        finding="no_prior_report_in_search",
        search_or_test_scope="Synthetic bounded search of a specified database and date range.",
        citations=["https://example.org/test"],
        notes="No novelty proof is implied by this synthetic search.",
    )
    with pytest.raises(ValueError):
        save_review(tmp_path, review, {"different_site"})
    first = save_review(tmp_path, review, {"site"})
    second = save_review(tmp_path, review, {"site"})
    assert first != second and len(load_reviews(tmp_path)) == 2
    with pytest.raises(ValidationError):
        Review.model_validate({**review.model_dump(), "kind": "expert_assessment"})


def test_import_requires_snapshots_and_preserves_existing_claims(tmp_path):
    bundle = load_evidence(ROOT)
    shutil.copytree(
        ROOT / "data/metadata/evidence/science", tmp_path / "data/metadata/evidence/science"
    )
    subjects = {o.subject_id for o in bundle.observations}
    imported = import_evidence(tmp_path, bundle.model_dump_json(), subjects)
    assert imported == bundle
    repeated = import_evidence(tmp_path, bundle.model_dump_json(), subjects)
    assert repeated == imported
    altered = json.loads(bundle.model_dump_json())
    altered["observations"][0]["value"] = 20
    with pytest.raises(ValueError, match="Conflicting"):
        import_evidence(tmp_path, json.dumps(altered), subjects)
    assert load_evidence(tmp_path) == imported
    snapshot = tmp_path / bundle.sources[0].snapshot_path
    snapshot.write_text("tampered")
    with pytest.raises(ValueError, match="checksum"):
        import_evidence(tmp_path, bundle.model_dump_json(), subjects)


def test_comparable_abundance_can_satisfy_resource_gate(reference, earth_sites, scoring_config):
    # Synthetic test-only abundance values never enter the real application catalog.
    original = load_evidence(ROOT)
    observations = []
    for identity, subject in [
        ("target_resource", reference.profile_id),
        ("earth_resource", earth_sites[0].site_id),
    ]:
        observations.append(
            Observation.model_validate(
                {
                    **observation().model_dump(),
                    "observation_id": identity,
                    "subject_id": subject,
                    "domain": "resources",
                    "quantity": "water_ice_mass_fraction",
                    "value": 0.1,
                    "unit": "fraction",
                    "statistic": "sample_mean",
                    "scope": "named_site",
                    "status": "measured",
                    "source_ids": [original.sources[0].source_id],
                }
            )
        )
    bundle = EvidenceBundle(
        version="synthetic_test", sources=[original.sources[0]], observations=observations
    )
    scenario = read_yaml(ROOT / "config/research_scenarios.yaml")["scenarios"][2]
    rows = rank_assessments(
        reference,
        earth_sites,
        rank_candidates(reference, earth_sites, scoring_config),
        {},
        bundle,
        scenario,
    )
    assert rows[0]["eligible"] and rows[0]["domains"]["resources"]["similarity"] == 1
    assert sum(r["eligible"] for r in rows) == 1
    assert rows[0]["independent_validation"] == "pending"
