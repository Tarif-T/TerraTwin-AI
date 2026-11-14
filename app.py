"""Offline-first application: never download or preprocess rasters during a request."""

import json

import pandas as pd
import streamlit as st

from terratwin.characterization import characterize_filter, load_characterization
from terratwin.config import ROOT, load_scoring, read_yaml
from terratwin.datasets import load_prepared
from terratwin.evidence_ui import render_characterization, render_comparison
from terratwin.export.csv_export import export_analysis
from terratwin.mission import mission_scoring
from terratwin.models import FEATURES
from terratwin.scoring.engine import rank_candidates

st.set_page_config(page_title="TerraTwin AI | Analognauts", page_icon="🌍", layout="wide")
st.caption("ANALOGNAUTS  /  TERRAIN ANALOG RESEARCH")
st.title("TerraTwin AI")
st.write(
    "Find Earth environments with terrain characteristics similar to measured "
    "Mars and Moon regions."
)
st.caption(
    "A terrain similarity index supports research shortlisting. "
    "It is not a probability of mission suitability."
)

base_config = load_scoring()
config = base_config
try:
    characterization = load_characterization(ROOT)
except (ValueError, OSError, KeyError) as error:
    characterization = {}
    st.warning(f"Supplementary evidence unavailable: {error}")
explore, methods, sources_tab = st.tabs(["Explore", "Methodology", "Sources & readiness"])
try:
    references, sites, sources = load_prepared()
    data_error = None
except (ValueError, OSError, KeyError, TypeError) as error:
    references, sites, sources = [], [], {}
    data_error = str(error)

if references and sites and (len(sites) < 10 or {p.body for p in references} != {"Mars", "Moon"}):
    st.info(
        f"Limited real-data prototype: {len(references)} reference "
        f"and {len(sites)} Earth candidate(s). "
        + (
            "A single candidate's rank 1 does not establish superiority. "
            if len(sites) == 1
            else ""
        )
        + "Full MVP coverage and independent scientific validation remain incomplete."
    )

acquisition_path = ROOT / "data/metadata/earth_acquisition_status.json"
if acquisition_path.exists():
    acquisition = json.loads(acquisition_path.read_text(encoding="utf-8"))
    prepared_ids = {p.site_id for p in sites}
    pending = [c for c in acquisition["candidates"] if f"earth_{c['tile']}" not in prepared_ids]
    if pending:
        with st.expander(f"Expand Earth coverage: {len(pending)} additional regions pending"):
            st.write(
                "These are planned regions, not measured ranking results. Sign in to NASA "
                "Earthdata to download each ZIP, then place it in "
                "data/raw/Earth/NASADEM_archives/."
            )
            for candidate in pending:
                st.link_button(
                    f"Download {candidate['region']} ({candidate['tile']})",
                    candidate["download_url"],
                )
            st.write("After downloading, run this command from the project folder:")
            st.code(
                ".venv/Scripts/python.exe scripts/expand_earth_catalog.py --register --build",
                language="powershell",
            )

with explore:
    presets = read_yaml(ROOT / "config/missions.yaml")["missions"]
    preset = st.selectbox("Mission focus", presets, format_func=lambda p: p["name"])
    config = mission_scoring(base_config, preset)
    st.caption(preset["purpose"] + " Weights are uncalibrated engineering presets.")
    comparison_sites = sites
    filters = dict(max_precipitation=None, max_temperature=None, geology_class=None)
    if st.checkbox("Apply Earth field-condition filters"):
        st.caption(
            "Filters select Earth testing conditions; they do not score planetary "
            "environmental similarity. Candidates lacking required evidence are excluded."
        )
        dry, cold, lith = st.columns(3)
        with dry:
            if st.checkbox("Limit annual precipitation"):
                filters["max_precipitation"] = st.number_input(
                    "Maximum annual precipitation (mm)", min_value=0.0, value=250.0
                )
        with cold:
            if st.checkbox("Limit mean air temperature"):
                filters["max_temperature"] = st.number_input(
                    "Maximum mean air temperature (°C)", min_value=-100.0, value=0.0
                )
        with lith:
            lithology = st.selectbox(
                "Mapped lithology at centroid",
                ["Any", "volcanic", "sedimentary", "unconsolidated", "metamorphic", "plutonic"],
            )
            filters["geology_class"] = None if lithology == "Any" else lithology
        comparison_sites = [
            p for p in sites if characterize_filter(p, characterization.get(p.site_id), **filters)
        ]
        st.info(
            f"{len(comparison_sites)} of {len(sites)} candidates "
            "match the selected evidence filters."
        )
    left, right = st.columns([1, 2])
    with left:
        st.subheader("Choose a reference")
        body = st.selectbox("Planetary body", ["Mars", "Moon"])
        available = [
            p
            for p in references
            if p.body == body
            and p.qa_pass
            and p.valid_cell_fraction >= config.minimum_valid_cell_fraction
        ]
        reference = None
        if available:
            reference = st.selectbox(
                "Measured reference region", available, format_func=lambda p: p.region_name
            )
            st.caption(
                f"{reference.roi_size_km:g} km ROI · {reference.common_grid_m:g} m analysis grid"
            )
            st.dataframe(
                pd.DataFrame([reference.model_dump(include=set(FEATURES))]).T, width="stretch"
            )
            st.caption(f"Valid ground coverage: {reference.valid_cell_fraction:.1%}")
            if reference.body == "Moon":
                st.info(
                    "This Shackleton study includes south-pole terrain; it is not a selected "
                    "base or landing pad. Illumination, ice distribution and communications "
                    "are not measured by LOLA elevation."
                )
                st.markdown(
                    "[NASA lunar south-pole environment]"
                    "(https://www.nasa.gov/reference/moonbase-environment/)"
                )
            elif reference.body == "Mars":
                st.caption(
                    "Jezero contains both igneous crater-floor rocks and sedimentary delta "
                    "deposits. A single terrain profile does not describe that lithological "
                    "distribution; inspect the Earth geology evidence separately."
                )
                st.markdown(
                    "[NASA Jezero geology context]"
                    "(https://www.nasa.gov/missions/mars-2020-perseverance/perseverance-rover/"
                    "nasas-perseverance-makes-new-discoveries-in-mars-jezero-crater/)"
                )
        else:
            target = next(
                t for t in read_yaml(ROOT / "config/targets.yaml")["targets"] if t["body"] == body
            )
            st.info("Reference data are not prepared.")
            st.caption(target["required_source"])
        run = st.button(
            "Find Earth Analogs",
            disabled=reference is None or not comparison_sites,
            type="primary",
            width="stretch",
        )
    with right:
        st.subheader("Earth candidate map")
        if data_error:
            st.warning("No validated scientific profiles loaded")
            st.write(
                "Prepare verified source rasters and ROI polygons with the offline pipeline "
                "to enable analysis."
            )
            st.caption(data_error)
        elif comparison_sites:
            points = pd.DataFrame(
                [
                    {"latitude": p.centroid_lat, "longitude": p.centroid_lon, "site": p.site_name}
                    for p in comparison_sites
                ]
            )
            # Basemap tiles may require network; rankings and all evidence remain local.
            st.map(points, latitude="latitude", longitude="longitude")
            st.caption(
                "Only verified catalog locations are shown. Basemap tiles require a connection."
            )
            with st.expander("Offline location overview"):
                st.scatter_chart(points, x="longitude", y="latitude")
                st.caption(
                    "Longitude/latitude overview without basemap tiles; not an equal-area map."
                )
        else:
            st.info("No verified Earth candidates are available.")
    # Recompute from the current selection on each rerun; never reuse stale rankings.
    if run and reference:
        st.session_state["analysis_reference"] = reference.profile_id
    if (
        reference
        and st.session_state.get("analysis_reference") == reference.profile_id
        and comparison_sites
    ):
        try:
            results = rank_candidates(reference, comparison_sites, config)
        except ValueError as error:
            st.error(str(error))
        else:
            eligible = [r for r in results if r["eligible"]]
            rejected = [r for r in results if not r["eligible"]]
            st.subheader("Ranked Earth candidates")
            if eligible:
                st.dataframe(
                    pd.DataFrame(
                        [
                            {
                                k: r[k]
                                for k in (
                                    "rank",
                                    "site_name",
                                    "similarity_index",
                                    "feature_coverage",
                                    "warning",
                                )
                            }
                            for r in eligible
                        ]
                    ),
                    hide_index=True,
                    width="stretch",
                )
                selected = st.selectbox(
                    "Inspect candidate evidence", eligible, format_func=lambda r: r["site_name"]
                )
                site = next(p for p in sites if p.site_id == selected["site_id"])
                st.metric("Terrain similarity index", f"{selected['similarity_index']:.2f} / 100")
                st.caption(f"Weighted feature coverage: {selected['feature_coverage']:.1%}")
                if selected["warning"]:
                    st.warning(selected["warning"])
                st.caption(
                    "This index compares four aggregate measurements. "
                    "It does not compare crater shape or the spatial arrangement of landforms."
                )
                breakdown = pd.DataFrame(selected["components"]).T
                st.dataframe(breakdown, width="stretch")
                st.write(
                    "Why it matches / how it differs: component similarity decreases exponentially "
                    "with absolute feature distance at the tolerances shown in Methodology."
                )
                st.caption(
                    f"Raster coverage {site.valid_cell_fraction:.1%}; {site.processing_notes}"
                )
                for source_id in selected["source_ids"]:
                    source = sources[source_id]
                    st.markdown(
                        f"[{source.dataset} {source.version}]({source.product_url}) · {source_id}"
                    )
                render_characterization(site, characterization.get(site.site_id, {}))
                others = [p for p in comparison_sites if p.site_id != site.site_id]
                if others:
                    with st.expander("Compare two Earth candidates"):
                        other = st.selectbox(
                            "Compare with", others, format_func=lambda p: p.site_name
                        )
                        render_comparison(reference, site, other, ROOT)
            else:
                st.info(
                    f"No eligible candidates. {len(rejected)} rejected by coverage "
                    "or raster QA thresholds."
                )
            if rejected:
                with st.expander(f"Insufficient coverage or quality ({len(rejected)})"):
                    st.dataframe(
                        pd.DataFrame(
                            [
                                {
                                    k: r[k]
                                    for k in (
                                        "site_name",
                                        "feature_coverage",
                                        "warning",
                                    )
                                }
                                for r in rejected
                            ]
                        ),
                        hide_index=True,
                    )
            st.download_button(
                "Download analysis CSV",
                export_analysis(
                    reference,
                    comparison_sites,
                    results,
                    config,
                    characterization=characterization,
                    selection_metadata={"mission_id": preset["id"], **filters},
                ),
                file_name="terratwin_analysis.csv",
                mime="text/csv",
            )

with methods:
    st.subheader("Transparent measurements, reproducible comparisons")
    st.latex(
        r"s_i=\exp(-|e_i-p_i|/\tau_i),\quad S=100\frac{\sum_{i\in V}w_i s_i}{\sum_{i\in V}w_i}"
    )
    st.write(
        "Coverage is the fraction of all configured weight supported by both profiles. "
        "Missing reference features are reported and reduce coverage; "
        "null is never treated as zero."
    )
    st.dataframe(
        pd.DataFrame({"weight": config.normalized_weights, "tolerance": config.tolerances}),
        width="stretch",
    )
    st.caption(
        f"{config.version} · minimum feature coverage {config.minimum_coverage:.0%} · "
        f"minimum valid raster coverage {config.minimum_valid_cell_fraction:.0%}"
    )
    st.markdown("""
    - **Median slope (degrees):** central elevation differences divided by metre spacing.
    - **Relief (metres):** P90 minus P10 elevation within the ROI.
    - **Local roughness (metres):** median population standard deviation in fully valid windows.
    - **Steep fraction (0–1):** share of valid slope samples above 15 degrees.
    """)
    st.write(
        "Comparisons require the same grid, ROI size, feature version and roughness neighborhood. "
        "At the provisional 1 km grid, the roughness window is 3 × 3 km. "
        "Thresholds and tolerances are engineering defaults requiring sensitivity review."
    )
    st.warning(
        "Terrain similarity does not establish matching geology, climate, resources, "
        "access, safety, "
        "gravity, atmosphere or radiation. These results imply no NASA endorsement."
    )

with sources_tab:
    st.subheader("Scientific data readiness")
    cols = st.columns(3)
    cols[0].metric("Measured references", len(references))
    cols[1].metric("Earth profiles", len(sites))
    cols[2].metric("Traceable sources", len(sources))
    st.write(
        "Full MVP acceptance requires one verified Mars reference, one Moon reference, "
        "and at least ten geographically distinct, QA-approved Earth profiles."
    )
    st.subheader("Challenge readiness")
    mapped_count = sum(
        bool(c.get("geology", {}).get("units"))
        for c in characterization.values()
        if c.get("geology")
    )
    climate_count = sum(c.get("climate") is not None for c in characterization.values())
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Capability": "Terrain comparison",
                    "Evidence": f"{len(references)} references; {len(sites)} Earth profiles",
                },
                {
                    "Capability": "Geology",
                    "Evidence": f"{mapped_count} centroid map interpretations; "
                    "no whole-ROI mineral maps",
                },
                {
                    "Capability": "Environment",
                    "Evidence": f"{climate_count} Earth climate summaries; "
                    "no cross-body climate equivalence",
                },
                {
                    "Capability": "Resources / caves",
                    "Evidence": "Not assessed; subsurface and resource observations still needed",
                },
                {
                    "Capability": "Candidate discovery",
                    "Evidence": "Bounded ArcticDEM tile search; no claim of worldwide completeness",
                },
                {
                    "Capability": "Novelty / suitability",
                    "Evidence": "Unreviewed; independent research and field validation required",
                },
            ]
        ),
        hide_index=True,
        width="stretch",
    )
    if sources:
        for source in sources.values():
            with st.expander(f"{source.source_id} · {source.dataset} {source.version}"):
                st.json(source.model_dump(mode="json"))
    else:
        st.info("No verified product IDs, checksums or retrieval records have been registered yet.")
    st.caption(
        "Acquisition instructions: docs/data-acquisition.md. "
        "No external data API is required to score prepared profiles."
    )
