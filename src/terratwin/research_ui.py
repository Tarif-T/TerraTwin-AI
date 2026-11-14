"""Research evidence, scoped comparisons and attributed human review records."""

from datetime import datetime, timezone

import pandas as pd
import streamlit as st
import yaml
from pydantic import ValidationError

from terratwin.config import read_yaml
from terratwin.science import (
    Review,
    export_assessments,
    for_subject,
    import_evidence,
    load_evidence,
    load_reviews,
    rank_assessments,
    save_review,
)
from terratwin.scoring.engine import rank_candidates
from terratwin.search import plan_nasadem


def render_research(root, references, sites, contexts, config):
    st.subheader("Multi-domain analog research")
    st.write(
        "Compare supported terrain, material and subsurface evidence. Domain weights are "
        "engineering choices; the evidence index is not a suitability probability."
    )
    st.caption(
        "Comparison coverage measures configured evidence availability, not scientific confidence. "
        "A reported ice floor does not establish resource abundance or extraction feasibility."
    )
    with st.expander("Plan additional Earth candidate regions"):
        st.caption(
            "Plan deterministic tile centers before scoring. Downloads require Earthdata access; "
            "planned regions enter rankings only after source validation and raster QA."
        )
        with st.form("discovery_plan"):
            west = st.number_input("Search west longitude", -180.0, 179.0, -72.0)
            south = st.number_input("Search south latitude", -56.0, 59.0, -28.0)
            east = st.number_input("Search east longitude", -179.0, 180.0, -66.0)
            north = st.number_input("Search north latitude", -55.0, 60.0, -20.0)
            budget = st.number_input("Maximum acquisition tiles", 1, 40, 12)
            planned = st.form_submit_button("Plan candidate acquisition")
        if planned:
            try:
                plan = plan_nasadem([west, south, east, north], budget)
            except ValueError as error:
                st.error(str(error))
            else:
                st.dataframe(pd.DataFrame(plan["candidates"]), hide_index=True)
                st.download_button(
                    "Download acquisition plan",
                    yaml.safe_dump(plan, sort_keys=False),
                    file_name="candidate_search.yaml",
                    mime="text/yaml",
                )
                st.code(
                    ".venv/Scripts/python.exe scripts/expand_earth_catalog.py "
                    "--candidates candidate_search.yaml --download --register --build"
                )
    if not references or not sites:
        st.info("Prepare real profiles before running evidence assessments.")
        return
    try:
        bundle = load_evidence(root)
        reviews = load_reviews(root)
    except (ValueError, OSError) as error:
        st.error(f"Scientific evidence integrity check failed: {error}")
        return
    target = st.selectbox("Research target", references, format_func=lambda p: p.region_name)
    scenarios = read_yaml(root / "config/research_scenarios.yaml")["scenarios"]
    selected = st.selectbox("Research scenario", scenarios, format_func=lambda p: p["name"])
    scenario = {**selected, "terrain_scoring": config.model_dump(mode="json")}
    st.json(
        {
            "weights": scenario["weights"],
            "minimum_coverage": scenario["minimum_coverage"],
            "required_domains": scenario["required_domains"],
        },
        expanded=False,
    )
    if st.button("Run evidence assessment"):
        st.session_state["research_selection"] = (target.profile_id, scenario["id"])
    if st.session_state.get("research_selection") == (target.profile_id, scenario["id"]):
        rows = rank_assessments(
            target, sites, rank_candidates(target, sites, config), contexts, bundle, scenario
        )
        accepted = [r for r in rows if r["eligible"]]
        st.metric("Eligible evidence candidates", len(accepted))
        if not accepted:
            st.warning(
                "No candidate meets the required evidence domains and coverage. "
                "Missing measurements remain unknown; they are not zero-valued matches."
            )
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        k: r[k]
                        for k in (
                            "evidence_rank",
                            "site_name",
                            "evidence_index",
                            "comparison_coverage",
                            "eligible",
                            "missing_required_domains",
                            "novelty_status",
                            "independent_validation",
                        )
                    }
                    for r in rows
                ]
            ),
            hide_index=True,
            width="stretch",
        )
        item = st.selectbox("Inspect research evidence", rows, format_func=lambda r: r["site_name"])
        st.dataframe(pd.DataFrame(item["domains"]).T, width="stretch")
        site_observations = for_subject(bundle, item["site_id"], "Earth")
        target_observations = for_subject(bundle, target.profile_id, target.body)
        st.caption(
            "Body means, study-region context and named-site observations "
            "keep their original scope. "
            "The 1 km surface grid does not resolve cave entrances or landing hazards."
        )
        st.json(
            {
                "target_observations": [o.model_dump(mode="json") for o in target_observations],
                "earth_observations": [o.model_dump(mode="json") for o in site_observations],
            }
        )
        ids = {s for o in [*site_observations, *target_observations] for s in o.source_ids}
        for source in bundle.sources:
            if source.source_id in ids:
                st.markdown(f"[{source.title}]({source.url})")
                st.caption(f"{source.source_id} · {source.snapshot_type} · {source.attribution}")
        st.download_button(
            "Download evidence assessment CSV",
            export_assessments(rows, target, sites, bundle, scenario, contexts, reviews),
            file_name=f"{target.profile_id}_{scenario['id']}_evidence.csv",
            mime="text/csv",
        )
    with st.expander("Novelty and independent review register"):
        st.write(
            "Record a bounded literature search or an expert/field assessment. "
            "Reviewer identity and submitted conclusions are self-reported and unverified. "
            "A search finding no prior report does not prove novelty. Reviews "
            "do not automatically certify rankings."
        )
        if reviews:
            st.dataframe(
                pd.DataFrame([r.model_dump(mode="json") for r in reviews]), hide_index=True
            )
        with st.form("scientific_review"):
            subject = st.selectbox("Review candidate", sites, format_func=lambda p: p.site_name)
            reviewer = st.text_input("Reviewer name or organization")
            kind = st.selectbox(
                "Review type", ["literature", "expert_assessment", "field_validation"]
            )
            finding = st.selectbox(
                "Review finding",
                [
                    "candidate_requires_review",
                    "known_analog",
                    "no_prior_report_in_search",
                    "supported_for_stated_test",
                    "not_supported_for_stated_test",
                ],
            )
            scope = st.text_area("Search or test scope (queries, dates, databases or protocol)")
            citations = st.text_area("Supporting publication or protocol URLs (one per line)")
            notes = st.text_area("Evidence, limitations and conflicts")
            submitted = st.form_submit_button("Save attributed review")
        if submitted:
            try:
                record = Review(
                    subject_id=subject.site_id,
                    reviewer=reviewer,
                    reviewed_utc=datetime.now(timezone.utc),
                    kind=kind,
                    finding=finding,
                    search_or_test_scope=scope,
                    citations=[u.strip() for u in citations.splitlines() if u.strip()],
                    notes=notes,
                )
                save_review(root, record, {p.site_id for p in sites})
            except (ValidationError, ValueError, OSError) as error:
                st.error(f"Review not saved: {error}")
            else:
                st.success(
                    "Attributed review saved locally. Scientific certification remains pending."
                )
    with st.expander("Import additional measured evidence"):
        st.caption(
            "Import a curated EvidenceBundle JSON with registered subject IDs, units, statistics, "
            "scope, citations and local source snapshots. Snapshot SHA256 must match. "
            "Imported claims remain attributed observations; an import is not expert approval."
        )
        uploaded = st.file_uploader("Curated evidence JSON", type=["json"])
        if st.button("Validate and register evidence", disabled=uploaded is None):
            subjects = (
                {p.profile_id for p in references}
                | {p.site_id for p in sites}
                | {"body:Mars", "body:Moon", "body:Earth"}
            )
            try:
                combined = import_evidence(root, uploaded.getvalue(), subjects)
            except (ValueError, OSError) as error:
                st.error(f"Evidence not registered: {error}")
            else:
                st.success(
                    f"Registered bundle now contains {len(combined.observations)} observations. "
                    "Run the assessment again to use the updated evidence."
                )
                st.session_state.pop("research_selection", None)
