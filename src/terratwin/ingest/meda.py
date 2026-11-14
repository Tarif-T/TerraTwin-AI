"""Audited MEDA ATS/derived-pressure tables; summaries describe observed samples only."""

import hashlib
import re
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pandas as pd

P = {"p": "http://pds.nasa.gov/pds4/pds/v1", "m": "http://pds.nasa.gov/pds4/mission/mars2020/v1"}


def summarize_meda(csv_path: Path, label_path: Path):
    label = ET.parse(label_path).getroot()

    def text(query):
        return label.findtext(query, namespaces=P)

    lid = text("p:Identification_Area/p:logical_identifier") or ""
    if not lid.startswith("urn:nasa:pds:mars2020_meda:"):
        raise ValueError("Not a MEDA product")
    ats = ":data_calibrated_env:" in lid and "cal_ats_" in lid
    pressure = ":data_derived_env:" in lid and "der_ps_" in lid
    if not (ats or pressure):
        raise ValueError("Only calibrated ATS and derived pressure are audited")
    file = label.find("p:File_Area_Observational/p:File", P)
    if file.findtext("p:file_name", namespaces=P) != csv_path.name:
        raise ValueError("MEDA label/data filename mismatch")
    data = csv_path.read_bytes()
    if len(data) != int(file.findtext("p:file_size", namespaces=P)):
        raise ValueError("MEDA byte count differs from publisher label")
    declared_md5 = file.findtext("p:md5_checksum", namespaces=P) or ""
    if not re.fullmatch(r"[0-9a-fA-F]{1,32}", declared_md5):
        raise ValueError("Missing or invalid publisher MD5")
    # Some archived labels omit leading zeroes from the hexadecimal digest.
    if hashlib.md5(data).hexdigest() != declared_md5.lower().zfill(32):
        raise ValueError("MEDA publisher MD5 mismatch")
    table = label.find("p:File_Area_Observational/p:Table_Delimited", P)
    if table.findtext("p:field_delimiter", namespaces=P) != "Comma":
        raise ValueError("MEDA table must be comma-delimited")
    fields = table.findall("p:Record_Delimited/p:Field_Delimited", P)
    names = [f.findtext("p:name", namespaces=P).replace(" ", "_") for f in fields]
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    if df.columns.tolist() != names or len(df) != int(table.findtext("p:records", namespaces=P)):
        raise ValueError("MEDA header or record count mismatch")
    expected = [f"ATS_LOCAL_TEMP{i}" for i in range(1, 6)] if ats else ["PRESSURE"]
    units = {n: f.findtext("p:unit", namespaces=P) for n, f in zip(names, fields, strict=True)}
    if any(units.get(n) != ("kelvin" if ats else "pascal") for n in expected):
        raise ValueError("MEDA physical unit differs from audited interpretation")
    lmst = df.LMST.str.extract(r"^(\d{5})M(\d{2}):(\d{2}):(\d{2}\.\d+)$")
    sol = int(text(".//m:start_sol_number"))
    if (
        lmst.isna().any().any()
        or not (lmst[0].astype(int) == sol).all()
        or not lmst[1].astype(int).between(0, 23).all()
        or not lmst[2].astype(int).between(0, 59).all()
        or not lmst[3].astype(float).between(0, 60, inclusive="left").all()
    ):
        raise ValueError("Invalid or mismatched MEDA local solar times")
    sclk = pd.to_numeric(df.SCLK, errors="raise")
    if not np.isfinite(sclk).all() or sclk.duplicated().any() or not sclk.is_monotonic_increasing:
        raise ValueError("MEDA spacecraft times must be finite, unique and increasing")
    results, hourly = [], []
    hour = lmst[1].astype(int)
    for column in expected:
        raw = df[column]
        numbers = pd.to_numeric(raw.replace("", np.nan), errors="raise")
        sentinel = numbers == 9999999999
        valid = numbers.notna() & ~sentinel
        if not np.isfinite(numbers[valid]).all() or (numbers[valid] <= 0).any():
            raise ValueError("Invalid MEDA physical measurement")
        values = numbers[valid]
        row = dict(
            sensor=column,
            unit=units[column],
            sample_count=int(valid.sum()),
            missing_count=int((~valid).sum()),
            sentinel_count=int(sentinel.sum()),
            observed_median=float(values.median()) if len(values) else None,
            observed_min=float(values.min()) if len(values) else None,
            observed_max=float(values.max()) if len(values) else None,
            occupied_lmst_hours=sorted(int(h) for h in hour[valid].unique()),
            instrument_uncertainty=None,
            uncertainty_note="No instrument uncertainty column is provided for ATS."
            if ats
            else "Pressure-uncertainty label declares kelvin, inconsistent with pressure units; "
            "uncertainty is not interpreted. Blank uncertainty values remain unknown.",
        )
        row["occupied_sclk_second_bins"] = len(np.unique(np.floor(sclk[valid])))
        row["approximate_sol_time_coverage"] = min(
            1.0, row["occupied_sclk_second_bins"] / 88775.244
        )
        if pressure:
            row["uncertainty_label_unit"] = units.get("PRESSURE_UNCERTAINTY")
            row["uncertainty_nonempty_count"] = int((df.PRESSURE_UNCERTAINTY != "").sum())
        results.append(row)
        for h in range(24):
            selected = numbers[valid & (hour == h)]
            hourly.append(
                dict(
                    sol=sol,
                    lmst_hour=h,
                    sensor=column,
                    unit=units[column],
                    sample_count=len(selected),
                    median=float(selected.median()) if len(selected) else None,
                )
            )
    return dict(
        logical_identifier=lid,
        version=text("p:Identification_Area/p:version_id"),
        sol=sol,
        start_utc=text(".//p:Time_Coordinates/p:start_date_time"),
        stop_utc=text(".//p:Time_Coordinates/p:stop_date_time"),
        publisher_md5_verified=True,
        record_count=len(df),
        summaries=results,
        hourly=hourly,
        interpretation="Observed-sample statistics at the rover sensor, "
        "not a full-sol or ROI mean. "
        "Rover heating, detector orientation and sampling gaps may affect temperature; "
        "sensor spread and observed range are not instrument uncertainty.",
    )
