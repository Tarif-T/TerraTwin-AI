# Initial implementation verification

Verified November 10, 2026, in the repository's Python 3.11.14 Windows environment.

Story: opening the offline-first Streamlit shell loads local configuration and
checks prepared profiles, explains unavailable data, and prevents unsupported
scientific rankings while exposing methodology and readiness.

| Boundary | Result | Evidence |
| --- | --- | --- |
| Server launch | Pass | Streamlit listening on 127.0.0.1:8501 |
| Browser rendering | Pass | TerraTwin title, Explore, Methodology and Sources/readiness visible |
| Local data absence -> UI | Pass | Missing-profile message and disabled Find Earth Analogs button |
| Mars/Moon state | Pass in AppTest | Both selections remain disabled; Moon displays LOLA source requirement |
| Offline empty state | Pass | Socket connection creation disabled during AppTest |
| Numeric features/scoring/schema | Pass | Analytical/synthetic tests; no test features placed in production data |
| Local raster -> feature -> Parquet -> reload | Pass | Synthetic temporary GeoTIFF round trip with mask/scaling/provenance checks |
| Lint | Pass | Ruff reports all checks passed |
| Dependencies | Pass | uv pip check: 57 packages compatible |
| Scientific release | Blocked as designed | Missing planetary_profiles.parquet and earth_profiles.parquet |

Commands executed:

```text
python -m pytest -q                        # 56 passed
python -m ruff check .                     # all checks passed
python scripts/run_smoke_test.py           # app renders without an exception
python scripts/run_smoke_test.py --release # expected exit 1: real data absent
python scripts/build_profiles.py           # expected exit 1: verified jobs absent
python scripts/validate_sources.py         # expected exit 1: source manifest empty
uv pip check --python .venv/Scripts/python.exe
git diff --check
```

The smoke harness emits Streamlit's benign missing-ScriptRunContext warning
before AppTest initializes its context. No server-side application exception was
observed. Real PDS decoding, actual Earthdata acquisition, prepared-data browser
rankings, online/offline mapping, source rights and independent scientific sanity
checks remain unverified. Browser automation encountered stale element references
for the body dropdown; its state transition is covered by AppTest instead.
