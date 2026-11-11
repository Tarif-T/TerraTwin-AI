"""Offline-first application: never download or preprocess rasters during a request."""

import pandas as pd
import streamlit as st

from terratwin.config import ROOT, load_scoring, read_yaml
from terratwin.datasets import load_prepared
from terratwin.export.csv_export import export_analysis
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

config = load_scoring()
explore, methods, sources_tab = st.tabs(["Explore", "Methodology", "Sources & readiness"])
try:
    references, sites, sources = load_prepared()
    data_error = None
except (ValueError, OSError, KeyError, TypeError) as error:
    references, sites, sources = [], [], {}
    data_error = str(error)

with explore:
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
        else:
            target = next(
                t for t in read_yaml(ROOT / "config/targets.yaml")["targets"] if t["body"] == body
            )
            st.info("Reference data are not prepared.")
            st.caption(target["required_source"])
        run = st.button(
            "Find Earth Analogs",
            disabled=reference is None or not sites,
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
        elif sites:
            points = pd.DataFrame(
                [
                    {"latitude": p.centroid_lat, "longitude": p.centroid_lon, "site": p.site_name}
                    for p in sites
                ]
            )
            # Basemap tiles may require network; rankings and all evidence remain local.
            st.map(points, latitude="latitude", longitude="longitude")
            st.caption(
                "Only verified catalog locations are shown. Basemap tiles require a connection."
            )
        else:
            st.info("No verified Earth candidates are available.")
    # Recompute from the current selection on each rerun; never reuse stale rankings.
    if run and reference:
        st.session_state["analysis_reference"] = reference.profile_id
    if reference and st.session_state.get("analysis_reference") == reference.profile_id and sites:
        try:
            results = rank_candidates(reference, sites, config)
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
                export_analysis(reference, sites, results, config),
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
