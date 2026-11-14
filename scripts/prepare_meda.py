"""Acquire and register a bounded two-sol Jezero MEDA environmental evidence slice."""

import json
import re
from datetime import datetime, timezone

from scripts.prepare_challenge_data import obtain
from terratwin.config import ROOT, content_hash
from terratwin.datasets import load_prepared
from terratwin.environment import export_environment
from terratwin.ingest.manifest import sha256_file
from terratwin.ingest.meda import summarize_meda
from terratwin.science import (
    EvidenceBundle,
    Observation,
    ScientificSource,
    import_evidence,
    load_evidence,
)

BASE = "https://atmos.nmsu.edu/PDS/data/PDS4/Mars2020/mars2020_meda/"


def prepare():
    folder = ROOT / "data/raw/Mars/MEDA"
    folder.mkdir(parents=True, exist_ok=True)
    old = load_evidence(ROOT)
    known = {s.source_id: s for s in old.sources}
    sources, observations, products = [], [], []
    now = datetime.now(timezone.utc)

    def register(key, path, url, title):
        digest = sha256_file(path)
        if key in known:
            record = known[key]
            if record.snapshot_sha256 != digest or str(record.url) != url:
                raise ValueError(
                    "Registered MEDA source changed; preserve and version it explicitly"
                )
        else:
            record = ScientificSource(
                source_id=key,
                title=title,
                url=url,
                snapshot_path=path.relative_to(ROOT).as_posix(),
                snapshot_sha256=digest,
                snapshot_type="original_response",
                accessed_utc=now,
                attribution="Rodriguez-Manfredi et al. (2021), MEDA, NASA PDS, "
                "DOI 10.17189/1522849",
            )
        sources.append(record)
        return key

    readme = folder / "readme.txt"
    obtain(BASE + "readme.txt", readme, limit=100000)
    docs = register("MEDA_README", readme, BASE + "readme.txt", "PDS MEDA interpretation README")
    for sol in (100, 101):
        for collection, code in (
            ("data_calibrated_env", "CAL_ATS"),
            ("data_derived_env", "DER_PS"),
        ):
            directory = BASE + collection + f"/sol_0090_0179/sol_{sol:04d}/"
            index = folder / f"sol_{sol:04d}_{collection}_index.html"
            obtain(directory, index, limit=100000)
            names = re.findall(r'href="(WE__\d{4}_+' + code + r'_+P\d+\.CSV)"', index.read_text())
            if not names:
                raise ValueError("No audited MEDA product in publisher listing")
            name = max(names, key=lambda n: int(re.search(r"P(\d+)\.CSV", n).group(1)))
            csv_path, label = folder / name, folder / name.replace(".CSV", ".xml")
            for path in (csv_path, label):
                obtain(directory + path.name, path, limit=12000000)
            product = summarize_meda(csv_path, label)
            ids = [docs]
            for suffix, path in (("CSV", csv_path), ("LABEL", label), ("INDEX", index)):
                ids.append(
                    register(
                        f"MEDA_SOL{sol}_{code}_{suffix}",
                        path,
                        directory if suffix == "INDEX" else directory + path.name,
                        f"MEDA sol {sol} {code} {suffix}",
                    )
                )
            product["source_ids"] = ids
            products.append(product)
            for item in product["summaries"]:
                if item["observed_median"] is None:
                    continue
                temperature = code == "CAL_ATS"
                observations.append(
                    Observation(
                        observation_id=f"meda_sol{sol}_{item['sensor']}_median_v1",
                        subject_id="mars_jezero_60km_v1",
                        domain="environment",
                        quantity="sensor_local_air_temperature_k"
                        if temperature
                        else "surface_pressure_pa",
                        value=item["observed_median"],
                        unit="K" if temperature else "Pa",
                        statistic="observed_sample_median",
                        scope="named_site",
                        status="measured",
                        source_ids=ids,
                        interpretation=product["interpretation"] + f" Sol {sol}, {item['sensor']}.",
                        measurement_start_utc=product["start_utc"],
                        measurement_stop_utc=product["stop_utc"],
                        sample_count=item["sample_count"],
                        sampling_basis="partial_sol_rover_sensor_samples",
                        measurement_method=f"MEDA {code} {item['sensor']}",
                        uncertainty_note=item["uncertainty_note"],
                    )
                )
    incoming = EvidenceBundle(version="science_v1", sources=sources, observations=observations)
    refs, sites, _ = load_prepared()
    import_evidence(
        ROOT,
        incoming.model_dump_json(),
        {p.profile_id for p in refs}
        | {p.site_id for p in sites}
        | {"body:Mars", "body:Moon", "body:Earth"},
    )
    result = dict(
        version="meda_context_v1",
        subject_id="mars_jezero_60km_v1",
        products=products,
        processing_hash=content_hash(products),
        independent_validation=False,
    )
    (ROOT / "data/processed/planetary_environment.json").write_text(
        json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )
    (ROOT / "data/processed/jezero_meda_sols100_101.csv").write_text(
        export_environment(result, load_evidence(ROOT)), encoding="utf-8", newline=""
    )
    print(
        f"Verified {len(products)} MEDA tables against publisher MD5; "
        f"added {len(observations)} observations"
    )


if __name__ == "__main__":
    prepare()
