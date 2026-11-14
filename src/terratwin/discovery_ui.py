"""Search controls and nonblocking progress for new measured Earth candidates."""

import json
import re
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

from terratwin.discovery import DiscoveryRequest, load_completed_run, start_job, write_json


def render_job(root, run_id, reference_id, polling=False):
    folder = root / "data/processed/discovery" / run_id
    try:
        status = json.loads((folder / "status.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        st.error(f"Search status unavailable: {error}")
        return
    st.caption(f"Search {run_id[:8]} · {status['state']}")
    if polling and status["state"] not in ("queued", "running"):
        st.rerun()
    if status["state"] in ("queued", "running"):
        st.progress(min(1.0, status["completed"] / max(1, status["total"])), text=status["message"])
        st.caption(
            "Processing continues in a background worker. This view refreshes automatically."
        )
        if st.button("Cancel discovery search", key="cancel_" + run_id):
            (folder / "cancel.request").touch()
            write_json(
                folder / "status.json",
                {
                    **status,
                    "state": "cancelled",
                    "message": "Cancellation requested; any current download may finish first",
                },
            )
            st.info("Cancellation requested; the current bounded download may finish first.")
            st.rerun()
        stamp = status.get("updated_utc")
        if (
            stamp
            and (datetime.now(timezone.utc) - datetime.fromisoformat(stamp)).total_seconds() > 180
        ):
            st.warning(
                "The worker has not updated recently. Check the saved run log if this persists."
            )
        return
    if status["state"] != "completed":
        st.warning(status["message"])
        return
    try:
        result = load_completed_run(folder)
    except (ValueError, OSError, KeyError, StopIteration) as error:
        st.error(f"Saved search integrity check failed: {error}")
        return
    if result["request"]["reference"]["profile_id"] != reference_id:
        st.info(
            "This saved search uses a different planetary target. Select its target to inspect it."
        )
        return
    st.success(
        f"Measured {status['measured']} new regions; {status['eligible']} passed ranking QA."
    )
    st.caption(
        f"Saved search box: {result['search']['bbox']}. "
        "Centers were chosen before scoring. Existing catalog centers within 60 km were excluded."
    )
    ranks = pd.DataFrame(result["rankings"])
    if not ranks.empty:
        st.dataframe(
            ranks[
                ["rank", "site_name", "similarity_index", "feature_coverage", "eligible", "warning"]
            ],
            hide_index=True,
            width="stretch",
        )
        profiles = {p["site_id"]: p for p in result["profiles"]}
        eligible = [r for r in result["rankings"] if r["eligible"]]
        if eligible:
            points = pd.DataFrame(
                [
                    dict(
                        latitude=profiles[r["site_id"]]["centroid_lat"],
                        longitude=profiles[r["site_id"]]["centroid_lon"],
                        score=r["similarity_index"],
                    )
                    for r in eligible
                ]
            )
            st.map(points, latitude="latitude", longitude="longitude")
        item = st.selectbox(
            "Inspect discovered location",
            result["rankings"],
            format_func=lambda r: r["site_name"],
            key="inspect_" + run_id,
        )
        profile = profiles[item["site_id"]]
        st.write(f"Coordinates: {profile['centroid_lat']:.5f}, {profile['centroid_lon']:.5f}")
        st.caption(
            f"Valid source/land coverage: {profile['valid_cell_fraction']:.1%}. "
            "Novelty, geology and mission suitability: unreviewed."
        )
        st.dataframe(pd.DataFrame(item["components"]).T, width="stretch")
        for source in result["sources"]:
            if source["source_id"] in profile["source_ids"]:
                st.markdown(f"[{source['dataset']}]({source['download_url']})")
        st.download_button(
            "Download discovered rankings CSV",
            (folder / "rankings.csv").read_bytes(),
            file_name=f"earth_discovery_{run_id[:8]}.csv",
            mime="text/csv",
        )
        st.download_button(
            "Download discovery footprints GeoJSON",
            json.dumps(result["footprints"]),
            file_name=f"earth_discovery_{run_id[:8]}.geojson",
            mime="application/geo+json",
        )
    else:
        st.info("No measurable new locations were found. Try a larger inland search box.")
    st.download_button(
        "Download discovery evidence JSON",
        (folder / "results.json").read_bytes(),
        file_name=f"earth_discovery_{run_id[:8]}_evidence.json",
        mime="application/json",
    )
    if result["failures"]:
        with st.expander("Unavailable or failed source tiles"):
            st.dataframe(pd.DataFrame(result["failures"]), hide_index=True)
    st.caption(result["attribution"])


def render_discovery(root, references, sites, config):
    st.subheader("Discover Earth locations")
    st.write(
        "Search beyond the existing catalog: acquire public elevation and water-mask tiles, "
        "measure new regions, then rank their terrain against your Mars or Moon target."
    )
    st.caption(
        "This search currently supports non-dateline boxes between 40° S and 40° N. "
        "Each candidate covers 60 × 60 km on a 1 km grid. It is a bounded terrain search, "
        "not proof of a previously unpublished analog. Geology, environment and access need review."
    )
    st.caption(
        "The search box selects candidate centers; their full footprints may extend beyond it."
    )
    valid = [p for p in references if p.qa_pass and not p.synthetic]
    if not valid:
        st.info("Prepare a real planetary reference before running geographic discovery.")
        return
    target = st.selectbox("Discovery planetary target", valid, format_func=lambda p: p.region_name)
    with st.form("earth_discovery"):
        a, b, c, d = st.columns(4)
        west = a.number_input("Discovery west longitude", -180.0, 179.0, -119.0)
        south = b.number_input("Discovery south latitude", -40.0, 39.0, 33.0)
        east = c.number_input("Discovery east longitude", -179.0, 180.0, -112.0)
        north = d.number_input("Discovery north latitude", -39.0, 40.0, 38.0)
        budget = st.number_input("Maximum regions to measure", 1, 30, 12)
        st.caption(
            "Starting a search downloads public Copernicus GLO-90 files (up to roughly "
            "10 MB per region, plus the coverage index). No Earthdata login is required. "
            "Results are saved separately from the existing catalog."
        )
        submitted = st.form_submit_button("Discover and rank new Earth locations", type="primary")
    if submitted:
        active = st.session_state.get("discovery_run")
        previous = root / "data/processed/discovery" / str(active) / "status.json"
        if (
            active
            and previous.exists()
            and json.loads(previous.read_text())["state"] in ("queued", "running")
        ):
            st.warning(
                "A search is already running. Let it finish or cancel it before starting another."
            )
        else:
            try:
                request = DiscoveryRequest(
                    bbox=(west, south, east, north),
                    budget=budget,
                    reference=target,
                    scoring=config,
                    known_centers=[(p.centroid_lon, p.centroid_lat) for p in sites],
                )
                run_id = start_job(root, request)
                st.session_state["discovery_run"] = run_id
                st.session_state["discovery_view"] = run_id
                st.session_state["saved_discovery_selection"] = run_id
            except (ValueError, OSError) as error:
                st.error(f"Search could not start: {error}")
    saved = root / "data/processed/discovery"
    runs = sorted(
        (p.name for p in saved.glob("*") if p.is_dir() and re.fullmatch(r"[a-f0-9]{32}", p.name)),
        key=lambda name: (saved / name).stat().st_mtime,
        reverse=True,
    )
    if runs:
        current = st.session_state.get("discovery_run", runs[0])
        chosen = st.selectbox(
            "Saved discovery search",
            runs,
            index=runs.index(current) if current in runs else 0,
            format_func=lambda name: name[:8],
            key="saved_discovery_selection",
        )
        if st.button("Open saved discovery search"):
            st.session_state["discovery_view"] = chosen
        if st.session_state.get("discovery_view") == chosen:
            status = json.loads((saved / chosen / "status.json").read_text(encoding="utf-8"))
            polling = status["state"] in ("queued", "running")
            st.fragment(run_every="3s" if polling else None)(render_job)(
                root, chosen, target.profile_id, polling
            )
