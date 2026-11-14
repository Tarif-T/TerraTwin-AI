"""Scoped, traceable multi-domain comparisons and human review contracts.

An evidence index is an engineering shortlist, never scientific certification.
Missing or uncertain observations cannot satisfy a required comparison domain.
"""

import csv
import io
import json
import math
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, HttpUrl, model_validator

from terratwin.config import content_hash
from terratwin.ingest.manifest import sha256_file
from terratwin.models import Contract

DOMAINS = ("terrain", "geology", "environment", "resources", "caves")


class ScientificSource(Contract):
    source_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    url: HttpUrl
    snapshot_path: str
    snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot_type: Literal["original_response", "structured_transcription"]
    accessed_utc: datetime
    attribution: str = Field(min_length=1)


class Observation(Contract):
    observation_id: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    domain: Literal["geology", "environment", "resources", "caves", "novelty"]
    quantity: str = Field(min_length=1)
    value: float | str | list[str] | None
    unit: str = Field(min_length=1)
    statistic: str = Field(min_length=1)
    scope: Literal["body", "study_region", "named_site", "centroid"]
    status: Literal["reported", "measured", "candidate", "uncertain", "unknown"]
    source_ids: list[str] = Field(min_length=1)
    interpretation: str = Field(min_length=20)

    @model_validator(mode="after")
    def honest_missingness(self):
        if self.status == "unknown" and self.value is not None:
            raise ValueError("Unknown observations must have a null value")
        if self.status in ("reported", "measured") and self.value is None:
            raise ValueError("Reported/measured observations require a value")
        if isinstance(self.value, float) and not math.isfinite(self.value):
            raise ValueError("Observation must be finite")
        if self.quantity.endswith("_m") and isinstance(self.value, float) and self.value < 0:
            raise ValueError("Length/depth observations cannot be negative")
        if (
            self.quantity.endswith("_categories")
            and self.value is not None
            and not isinstance(self.value, list)
        ):
            raise ValueError("Category observations require a list of explicit terms")
        if self.quantity == "water_ice_mass_fraction" and self.value is not None:
            if (
                not isinstance(self.value, float)
                or not 0 <= self.value <= 1
                or self.unit != "fraction"
            ):
                raise ValueError("Water/ice mass fraction must use a 0..1 fraction")
        return self


class EvidenceBundle(Contract):
    version: str
    sources: list[ScientificSource]
    observations: list[Observation]

    @model_validator(mode="after")
    def source_integrity(self):
        ids = {s.source_id for s in self.sources}
        if len(ids) != len(self.sources):
            raise ValueError("Duplicate scientific source ID")
        if len({o.observation_id for o in self.observations}) != len(self.observations):
            raise ValueError("Duplicate observation ID")
        if any(set(o.source_ids) - ids for o in self.observations):
            raise ValueError("Observation refers to an unregistered source")
        return self


class Review(Contract):
    subject_id: str
    reviewer: str = Field(min_length=3)
    reviewed_utc: datetime
    kind: Literal["literature", "expert_assessment", "field_validation"]
    finding: Literal[
        "known_analog",
        "candidate_requires_review",
        "no_prior_report_in_search",
        "supported_for_stated_test",
        "not_supported_for_stated_test",
    ]
    search_or_test_scope: str = Field(min_length=30)
    citations: list[HttpUrl] = Field(min_length=1)
    notes: str = Field(min_length=20)

    @model_validator(mode="after")
    def review_is_scoped(self):
        if self.reviewed_utc.tzinfo is None:
            raise ValueError("Review time must have a timezone")
        if self.kind != "literature" and self.finding in (
            "known_analog",
            "no_prior_report_in_search",
        ):
            raise ValueError("Novelty findings require a literature review")
        return self


def load_evidence(root: Path):
    path = root / "data/metadata/science_evidence.json"
    if not path.exists():
        return EvidenceBundle(version="science_v1", sources=[], observations=[])
    bundle = EvidenceBundle.model_validate_json(path.read_text(encoding="utf-8"))
    verify_snapshots(root, bundle)
    return bundle


def verify_snapshots(root, bundle):
    for source in bundle.sources:
        resolved = (root / source.snapshot_path).resolve()
        if not resolved.is_relative_to(root.resolve()):
            raise ValueError("Scientific snapshot must stay within the study workspace")
        if sha256_file(resolved) != source.snapshot_sha256:
            raise ValueError("Scientific source snapshot checksum changed")


def import_evidence(root, payload, allowed_subjects):
    """Append audited observations without silently replacing existing claims or sources."""
    incoming = EvidenceBundle.model_validate_json(payload)
    if any(o.subject_id not in allowed_subjects for o in incoming.observations):
        raise ValueError(
            "Evidence subject is not a prepared candidate/reference or registered body"
        )
    verify_snapshots(root, incoming)
    existing = load_evidence(root)

    def merge(old, new, key):
        records = {getattr(r, key): r for r in old}
        for record in new:
            identity = getattr(record, key)
            if identity in records and records[identity] != record:
                raise ValueError(f"Conflicting evidence ID: {identity}; use a new versioned ID")
            records[identity] = record
        return list(records.values())

    combined = EvidenceBundle(
        version=existing.version,
        sources=merge(existing.sources, incoming.sources, "source_id"),
        observations=merge(existing.observations, incoming.observations, "observation_id"),
    )
    folder = root / "data/metadata"
    folder.mkdir(parents=True, exist_ok=True)
    temporary = folder / f"science_import_{uuid.uuid4().hex}.tmp"
    temporary.write_text(combined.model_dump_json(indent=2) + "\n", encoding="utf-8")
    temporary.replace(folder / "science_evidence.json")
    return combined


def load_reviews(root: Path):
    folder = root / "data/metadata/reviews"
    return [
        Review.model_validate_json(p.read_text(encoding="utf-8"))
        for p in sorted(folder.glob("*.json"))
    ]


def save_review(root: Path, review: Review, allowed_subjects):
    if review.subject_id not in allowed_subjects:
        raise ValueError("Review subject is not a prepared Earth candidate")
    folder = root / "data/metadata/reviews"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"review_{uuid.uuid4().hex}.json"
    # Exclusive creation keeps earlier review records intact.
    with path.open("x", encoding="utf-8") as stream:
        stream.write(review.model_dump_json(indent=2) + "\n")
    return path


def for_subject(bundle, subject_id, body=None):
    subjects = {subject_id}
    if body:
        subjects.add(f"body:{body}")
    return [o for o in bundle.observations if o.subject_id in subjects]


def material_categories(context, observations):
    classes = set((context.get("geology") or {}).get("lithology_classes", []))
    categories = set()
    if classes & {"volcanic", "plutonic"}:
        categories.add("igneous")
    categories.update(classes & {"sedimentary", "metamorphic", "unconsolidated"})
    for observation in observations:
        if observation.quantity == "geologic_material_categories" and observation.status in (
            "reported",
            "measured",
        ):
            categories.update(observation.value)
    return categories


def compare_observations(left, right, quantity, tolerance):
    """Only equivalent quantities, units, statistics and scopes enter numerical comparison."""
    a = [o for o in left if o.quantity == quantity and o.status in ("reported", "measured")]
    b = [o for o in right if o.quantity == quantity and o.status in ("reported", "measured")]
    for one in a:
        for two in b:
            if (one.unit, one.statistic, one.scope) != (two.unit, two.statistic, two.scope):
                continue
            if isinstance(one.value, float) and isinstance(two.value, float):
                if not math.isfinite(tolerance) or tolerance <= 0:
                    raise ValueError("Comparison tolerance must be positive and finite")
                return dict(
                    similarity=math.exp(-abs(one.value - two.value) / tolerance),
                    left=one.model_dump(mode="json"),
                    right=two.model_dump(mode="json"),
                )
    return dict(
        similarity=None, reason="No equivalent confirmed quantity/unit/statistic/scope pair"
    )


def categorical_overlap(left, right):
    if not left or not right:
        return None
    return len(left & right) / len(left | right)


def assess_candidate(reference, site, terrain, contexts, bundle, scenario):
    target = for_subject(bundle, reference.profile_id, reference.body)
    earth = for_subject(bundle, site.site_id, "Earth")
    context = contexts.get(site.site_id, {})
    a, b = material_categories({}, target), material_categories(context, earth)
    gravity = compare_observations(target, earth, "surface_gravity_m_s2", tolerance=3)
    cave_a = {
        v
        for o in target
        if o.quantity == "subsurface_setting_categories" and o.status in ("reported", "measured")
        for v in o.value
    }
    cave_b = {
        v
        for o in earth
        if o.quantity == "subsurface_setting_categories" and o.status in ("reported", "measured")
        for v in o.value
    }
    # Water/ice presence is reported separately from unknown abundance or extraction feasibility.
    resource = compare_observations(target, earth, "water_ice_mass_fraction", tolerance=0.1)
    domains = dict(
        terrain=dict(
            similarity=terrain["similarity_index"] / 100
            if terrain["similarity_index"] is not None
            else None,
            coverage=terrain["feature_coverage"],
            note="Matched-scale terrain aggregates",
        ),
        geology=dict(
            similarity=categorical_overlap(a, b),
            coverage=1.0 if a and b else 0.0,
            target_categories=sorted(a),
            earth_categories=sorted(b),
            note="Contextual material-category overlap, not ROI proportions or mineral abundance",
        ),
        environment=dict(
            similarity=gravity["similarity"],
            coverage=0.5 if gravity["similarity"] is not None else 0.0,
            note="Body-mean gravity context only; local thermal/radiation/atmospheric "
            "equivalence is unmeasured. Earth air and lunar surface temperatures are not mixed",
        ),
        resources=dict(
            similarity=resource["similarity"],
            coverage=1.0 if resource["similarity"] is not None else 0.0,
            note="Compatible measured resource abundance required; reported ice "
            "alone is insufficient",
        ),
        caves=dict(
            similarity=categorical_overlap(cave_a, cave_b),
            coverage=1.0 if cave_a and cave_b else 0.0,
            note="Published subsurface-setting overlap; no underground "
            "accessibility or stability certification",
        ),
    )
    weights = scenario["weights"]
    if set(weights) != set(DOMAINS) or any(not math.isfinite(v) or v < 0 for v in weights.values()):
        raise ValueError("Scenario requires finite nonnegative weights for all five domains")
    total = math.fsum(weights.values())
    if total <= 0:
        raise ValueError("Scenario weights must sum to a positive value")
    if not 0 < scenario["minimum_coverage"] <= 1 or set(scenario["required_domains"]) - set(
        DOMAINS
    ):
        raise ValueError("Invalid scenario coverage or required domain")
    supported = math.fsum(
        weights[k] * v["coverage"] for k, v in domains.items() if v["similarity"] is not None
    )
    coverage = supported / total
    score = (
        100
        * math.fsum(
            weights[k] * v["coverage"] * v["similarity"]
            for k, v in domains.items()
            if v["similarity"] is not None
        )
        / supported
        if supported
        else None
    )
    missing_required = [k for k in scenario["required_domains"] if domains[k]["similarity"] is None]
    eligible = (
        terrain["eligible"] and coverage >= scenario["minimum_coverage"] and not missing_required
    )
    observation_ids = [o.observation_id for o in [*target, *earth]]
    return dict(
        site_id=site.site_id,
        site_name=site.site_name,
        reference_profile_id=reference.profile_id,
        scenario_id=scenario["id"],
        evidence_index=score,
        comparison_coverage=coverage,
        eligible=eligible,
        missing_required_domains=missing_required,
        domains=domains,
        evidence_ids=observation_ids,
        novelty_status=(
            "known_baseline"
            if any(
                o.quantity == "analog_publication_status"
                and o.value == "known_baseline"
                and o.status == "reported"
                for o in earth
            )
            else "unreviewed"
        ),
        independent_validation="pending",
        cave_resource_observations=[
            o.model_dump(mode="json") for o in earth if o.domain in ("caves", "resources")
        ],
        warning="Contextual evidence index with uncalibrated weights; not a "
        "probability or certification",
    )


def rank_assessments(reference, sites, terrain_results, contexts, bundle, scenario):
    terrain = {r["site_id"]: r for r in terrain_results}
    rows = [
        assess_candidate(reference, site, terrain[site.site_id], contexts, bundle, scenario)
        for site in sites
    ]
    rows.sort(
        key=lambda r: (
            not r["eligible"],
            -(r["evidence_index"] if r["evidence_index"] is not None else -1),
            -r["comparison_coverage"],
            r["site_id"],
        )
    )
    rank = 0
    for row in rows:
        if row["eligible"]:
            rank += 1
            row["evidence_rank"] = rank
        else:
            row["evidence_rank"] = None
    return rows


def export_assessments(rows, reference, sites, bundle, scenario, contexts, reviews=()):
    run_hash = content_hash(
        dict(
            reference=reference.model_dump(mode="json"),
            sites=[p.model_dump(mode="json") for p in sorted(sites, key=lambda p: p.site_id)],
            evidence=bundle.model_dump(mode="json"),
            scenario=scenario,
            contexts=contexts,
            reviews=[r.model_dump(mode="json") for r in reviews],
        )
    )
    stream = io.StringIO(newline="")
    exported = []
    for row in rows:
        site = next(p for p in sites if p.site_id == row["site_id"])
        exported.append(
            dict(
                site_id=site.site_id,
                site_name=site.site_name,
                latitude=site.centroid_lat,
                longitude=site.centroid_lon,
                **{
                    key: row[key]
                    for key in (
                        "evidence_rank",
                        "evidence_index",
                        "comparison_coverage",
                        "eligible",
                        "reference_profile_id",
                        "scenario_id",
                        "novelty_status",
                        "independent_validation",
                    )
                },
                domains=json.dumps(row["domains"], sort_keys=True),
                scientific_evidence=json.dumps(row["evidence_ids"]),
                observations=json.dumps(
                    [
                        o.model_dump(mode="json")
                        for o in bundle.observations
                        if o.observation_id in row["evidence_ids"]
                    ],
                    sort_keys=True,
                ),
                terrain_profiles=json.dumps(
                    {
                        "reference": reference.model_dump(mode="json"),
                        "earth": site.model_dump(mode="json"),
                    },
                    sort_keys=True,
                ),
                earth_context=json.dumps(contexts.get(site.site_id, {}), sort_keys=True),
                input_hash=run_hash,
                source_registry=json.dumps(
                    [s.model_dump(mode="json") for s in bundle.sources], sort_keys=True
                ),
                scenario=json.dumps(scenario, sort_keys=True),
                review_records=json.dumps(
                    [r.model_dump(mode="json") for r in reviews if r.subject_id == site.site_id],
                    sort_keys=True,
                ),
                reviewer_identity_status="self_reported_unverified",
                warning=row["warning"],
            )
        )
    if exported:
        writer = csv.DictWriter(stream, fieldnames=list(exported[0]))
        writer.writeheader()
        writer.writerows(exported)
    return stream.getvalue()
