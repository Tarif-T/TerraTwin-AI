"""Reproducible local planetary context; short sensor records do not become climate scores."""

import csv
import io
import json

from terratwin.config import content_hash
from terratwin.ingest.meda import summarize_meda


def load_meda_context(root, bundle, subject_id):
    path = root / "data/processed/planetary_environment.json"
    if not path.exists():
        return None
    saved = json.loads(path.read_text(encoding="utf-8"))
    if saved["subject_id"] != subject_id:
        return None
    if content_hash(saved["products"]) != saved["processing_hash"]:
        raise ValueError("Planetary environment summary hash changed")
    registry = {s.source_id: s for s in bundle.sources}
    for product in saved["products"]:
        sources = [registry[key] for key in product["source_ids"]]
        csv_source = next(s for s in sources if s.source_id.endswith("_CSV"))
        label = next(s for s in sources if s.source_id.endswith("_LABEL"))
        repeated = summarize_meda(root / csv_source.snapshot_path, root / label.snapshot_path)
        if repeated != {k: v for k, v in product.items() if k != "source_ids"}:
            raise ValueError("Planetary summary does not reproduce the registered sensor data")
    return saved


def export_environment(context, bundle):
    rows = []
    registry = {s.source_id: s for s in bundle.sources}
    for product in context["products"]:
        for item in product["summaries"]:
            rows.append(
                dict(
                    subject_id=context["subject_id"],
                    sol=product["sol"],
                    start_utc=product["start_utc"],
                    stop_utc=product["stop_utc"],
                    logical_identifier=product["logical_identifier"],
                    **item,
                    sources=json.dumps(
                        [registry[key].model_dump(mode="json") for key in product["source_ids"]],
                        sort_keys=True,
                    ),
                    processing_hash=context["processing_hash"],
                    interpretation=product["interpretation"],
                )
            )
    stream = io.StringIO(newline="")
    fields = list(dict.fromkeys(key for row in rows for key in row))
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue()


def render_environment(root, target, bundle):
    import pandas as pd
    import streamlit as st

    with st.expander("Local planetary environmental measurements"):
        st.caption(
            "Short rover-sensor records retain their time range and sampling gaps. "
            "They do not establish the environment of the entire terrain ROI."
        )
        if not st.checkbox("Inspect local measurements", key="local_environment"):
            return
        try:
            context = load_meda_context(root, bundle, target.profile_id)
        except (ValueError, OSError, KeyError, StopIteration) as error:
            st.error(f"Planetary evidence verification failed: {error}")
            return
        if context is None:
            st.info(
                "No local environmental time series is prepared for this target. "
                "Body-mean facts remain separate context."
            )
            return
        st.write(
            "Jezero MEDA: calibrated local temperatures for five detectors and derived pressure, "
            "sols 100–101. Statistics describe observed samples, not full-sol means."
        )
        st.warning(
            "The pressure-uncertainty labels declare kelvin. This unit conflict is preserved; "
            "instrument uncertainty remains unknown. Detector spread is not uncertainty."
        )
        rows = [
            dict(sol=p["sol"], start_utc=p["start_utc"], stop_utc=p["stop_utc"], **s)
            for p in context["products"]
            for s in p["summaries"]
        ]
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        hourly = pd.DataFrame([h for p in context["products"] for h in p["hourly"]])
        for sol in sorted(hourly.sol.unique()):
            st.write(f"Sol {sol}: hourly medians of available samples")
            for title, names in [
                ("Local detector air temperature (K)", [f"ATS_LOCAL_TEMP{i}" for i in range(1, 6)]),
                ("Pressure (Pa)", ["PRESSURE"]),
            ]:
                st.caption(title)
                frame = hourly[(hourly.sol == sol) & hourly.sensor.isin(names)]
                st.line_chart(frame.pivot(index="lmst_hour", columns="sensor", values="median"))
        st.caption(
            "Occupied spacecraft-clock second bins give approximate sol-time coverage. "
            "Having samples in every hour does not mean continuous coverage. "
            "These observations are not scored against Earth's 2015–2024 ERA5 climate means. "
            "A matched sampling/height protocol is needed for a quantitative comparison."
        )
        ids = {key for p in context["products"] for key in p["source_ids"]}
        for source in bundle.sources:
            if source.source_id in ids:
                st.markdown(f"[{source.title}]({source.url})")
        st.download_button(
            "Download local environment CSV",
            export_environment(context, bundle),
            file_name="jezero_meda_sols100_101.csv",
            mime="text/csv",
        )
