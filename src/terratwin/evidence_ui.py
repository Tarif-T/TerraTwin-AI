"""Render scientific context without converting missing evidence into scores."""

import json

import numpy as np
import pandas as pd
import rasterio
import streamlit as st

from terratwin.ingest.manifest import sha256_file
from terratwin.models import FEATURES


def render_characterization(site, context):
    st.subheader("Candidate characterization")
    st.write(
        f"{site.site_name} · {site.country} · {site.centroid_lat:.4f}°, {site.centroid_lon:.4f}°"
    )
    climate = context.get("climate") or {}
    geology = context.get("geology") or {}
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "domain": "Terrain",
                    "evidence": "Measured 60 km ROI; scored against selected reference",
                },
                {"domain": "Geology", "evidence": geology.get("status", "No local evidence")},
                {
                    "domain": "Environment",
                    "evidence": "Earth reanalysis grid cell" if climate else "Missing",
                },
                {
                    "domain": "Resources / caves",
                    "evidence": "Not assessed; no extraction/subsurface survey",
                },
                {
                    "domain": "Novelty",
                    "evidence": "Unreviewed; ranking does not establish a new analog",
                },
            ]
        ),
        hide_index=True,
        width="stretch",
    )
    if climate:
        columns = st.columns(2)
        t, p = climate["mean_temperature_c"], climate["mean_annual_precipitation_mm"]
        columns[0].metric(
            "Earth mean air temperature", f"{t:.1f} °C" if t is not None else "Missing"
        )
        columns[1].metric(
            "Earth mean annual precipitation", f"{p:.1f} mm" if p is not None else "Missing"
        )
        st.caption(
            "2015–2024 ERA5 near the centroid (0.25 degree grid); reanalysis, "
            "not a field observation "
            "or whole-ROI average. Earth air temperature is not lunar/Martian surface "
            "temperature, and precipitation does not measure extractable water."
        )
        monthly = climate["monthly_mean_temperature_c"]
        st.line_chart(
            pd.DataFrame(
                {
                    "Month": [int(m) for m in monthly],
                    "Earth air temperature (°C)": list(monthly.values()),
                }
            ),
            x="Month",
        )
    if geology.get("units"):
        st.write("Mapped geology at the candidate centroid")
        st.dataframe(
            pd.DataFrame(geology["units"])[["name", "lith", "scale", "source_id"]],
            hide_index=True,
            width="stretch",
        )
        st.caption(
            "Finest available map scale; multiple source interpretations are retained. "
            "A centroid unit is not the geology of the entire ROI. Lithology screening "
            "does not establish mineral abundance, grain size or excavation properties."
        )
        for reference in geology.get("references", {}).values():
            if reference:
                st.write(reference)
    for evidence in context.get("evidence", []):
        st.markdown(f"[{evidence['kind'].title()} source]({evidence['url']})")
        st.caption(evidence["license"] + f" · SHA256 {evidence['sha256']}")
    if not context:
        st.info("Supplementary characterization is not prepared for this candidate.")
    st.write(
        "Potential use: shortlist terrain for field testing under the chosen mission "
        "preset. Access, permits, hazards and scientific suitability require site review."
    )


def render_comparison(reference, site, other, root):
    st.dataframe(
        pd.DataFrame(
            {
                "Selected reference": {k: getattr(reference, k) for k in FEATURES},
                site.site_name: {k: getattr(site, k) for k in FEATURES},
                other.site_name: {k: getattr(other, k) for k in FEATURES},
            }
        ),
        width="stretch",
    )
    with st.expander("Measured terrain cross-sections"):
        manifest_path = root / "data/processed/processing_manifest.json"
        if not manifest_path.exists():
            st.info("Saved grids are unavailable.")
            return
        manifest = json.loads(manifest_path.read_text())
        curves = {}
        for profile in (reference, site, other):
            row = next(
                (r for r in manifest["profiles"] if r["profile_id"] == profile.profile_id), None
            )
            if row is None:
                st.info("No measurement grid is registered for this selection.")
                return
            path = root / "data/processed" / row["analysis_raster"]
            if sha256_file(path) != row["analysis_raster_sha256"]:
                st.error("Saved terrain grid checksum changed")
                return
            with rasterio.open(path) as dataset:
                heights = dataset.read(1)[dataset.height // 2]
            # Center relative to this transect only: no cross-body absolute datum comparison.
            curves[profile.region_name] = heights - np.nanmedian(heights)
        count = len(next(iter(curves.values())))
        curves["Local east distance (km)"] = (
            np.arange(count) + 0.5
        ) * reference.common_grid_m / 1000 - reference.roi_size_km / 2
        st.line_chart(pd.DataFrame(curves), x="Local east distance (km)")
        st.caption(
            "Central east–west row; heights relative to each transect median (metres). "
            "Local orientations differ. This is a visual review, not shape registration."
        )
