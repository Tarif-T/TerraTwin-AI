"""Acquire cached geology and historical climate context for measured Earth sites.

These sources characterize Earth field conditions, not planetary environmental
equivalence or extractable resources. Missing requests stay explicitly missing.
"""

import json
import shutil
from datetime import datetime, timezone

import requests

from terratwin.characterization import (
    CLIMATE_END,
    CLIMATE_START,
    summarize_climate,
    summarize_geology,
)
from terratwin.config import ROOT, content_hash
from terratwin.datasets import load_prepared
from terratwin.ingest.manifest import sha256_file


def prepare():
    _, sites, _ = load_prepared()
    raw = ROOT / "data/metadata/evidence/context"
    raw.mkdir(parents=True, exist_ok=True)
    output = {}
    session = requests.Session()
    for site in sites:
        record = dict(
            latitude=site.centroid_lat,
            longitude=site.centroid_lon,
            climate=None,
            geology=None,
            evidence=[],
            acquisition_errors={},
            resources=dict(
                status="not_assessed",
                water_ice=None,
                minerals=None,
                cave_access=None,
                note="No extraction feasibility or subsurface survey supplied",
            ),
            novelty=dict(
                status="unreviewed",
                note="A ranking does not establish a new analog; "
                "literature and field validation required",
            ),
        )
        for kind, url, params, parser, license_text in [
            (
                "geology",
                "https://macrostrat.org/api/v2/geologic_units/map",
                {"lat": site.centroid_lat, "lng": site.centroid_lon},
                summarize_geology,
                "Macrostrat CC-BY 4.0; original map references retained",
            ),
            (
                "climate",
                "https://archive-api.open-meteo.com/v1/archive",
                {
                    "latitude": site.centroid_lat,
                    "longitude": site.centroid_lon,
                    "start_date": CLIMATE_START,
                    "end_date": CLIMATE_END,
                    "daily": "temperature_2m_mean,precipitation_sum",
                    "models": "era5",
                    "timezone": "UTC",
                    "elevation": "nan",
                },
                summarize_climate,
                "Credit Open-Meteo and Copernicus Climate Change Service ERA5; CC-BY 4.0",
            ),
        ]:
            cache_key = content_hash(dict(url=url, params=params))[:16]
            path = raw / f"{site.site_id}_{kind}_{cache_key}.json"
            metadata_path = path.with_suffix(".request.json")
            try:
                previous = ROOT / "data/raw/context" / path.name
                if (
                    not path.exists()
                    and previous.exists()
                    and previous.with_suffix(".request.json").exists()
                ):
                    shutil.copyfile(previous, path)
                    shutil.copyfile(previous.with_suffix(".request.json"), metadata_path)
                if not path.exists():
                    response = session.get(url, params=params, timeout=(15, 60))
                    response.raise_for_status()
                    # Parse before caching so an error page never becomes a scientific source.
                    parser(response.json())
                    path.write_bytes(response.content)
                    metadata_path.write_text(
                        json.dumps(
                            dict(
                                url=response.url,
                                requested_parameters=params,
                                retrieved_utc=datetime.now(timezone.utc).isoformat(),
                                license=license_text,
                            ),
                            indent=2,
                        ),
                        encoding="utf-8",
                    )
                record[kind] = parser(json.loads(path.read_text(encoding="utf-8")))
                request = json.loads(metadata_path.read_text(encoding="utf-8"))
                record["evidence"].append(
                    dict(
                        kind=kind,
                        raw_path=path.relative_to(ROOT).as_posix(),
                        sha256=sha256_file(path),
                        metadata_path=metadata_path.relative_to(ROOT).as_posix(),
                        metadata_sha256=sha256_file(metadata_path),
                        **request,
                    )
                )
            except (requests.RequestException, ValueError, KeyError, OSError) as error:
                record["acquisition_errors"][kind] = type(error).__name__
        output[site.site_id] = record
        print(
            f"{site.site_id}: climate={record['climate'] is not None}, "
            f"geology={record['geology'] is not None}",
            flush=True,
        )
    bundle = dict(
        version="characterization_v1",
        prepared_utc=datetime.now(timezone.utc).isoformat(),
        sites=output,
        note="Earth context is not a cross-body suitability score",
    )
    (ROOT / "data/processed/characterization.json").write_text(
        json.dumps(bundle, indent=2, allow_nan=False) + "\n", encoding="utf-8"
    )


if __name__ == "__main__":
    prepare()
