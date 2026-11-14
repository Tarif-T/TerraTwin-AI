# Application verification - November 13, 2026

Story: select a planetary reference, rank eligible Earth profiles, inspect feature
evidence, and export the current analysis without stale reference results.

## Verified software behavior

- Full suite: **60 passed** (`python -m pytest -q`).
- Ruff: all checks passed (`python -m ruff check .`).
- App smoke test: renders without an exception.
- Live server: `GET /_stcore/health` returned HTTP 200 and `ok`.
- Browser: live Explore screen renders and correctly disables analysis when
  prepared scientific profiles are absent.
- Four additional AppTest workflows cover ranking/evidence/CSV parity, candidate
  selection updates, switching Mars to Moon without stale analysis, and the
  all-candidates-ineligible state.

Successful ranking tests use explicitly synthetic fixtures in isolated automated
test sessions. No synthetic profiles are saved in production data directories or
shown in the live demo. In these tests, the prepared-data loader is replaced at
the application boundary; they do not establish real NASA input correctness.
CSV assertions compare the generated payload against the UI table; they do not
exercise a browser save-to-disk operation. Online map tile behavior is not verified.

New test coverage: [test_app_flow.py](../tests/test_app_flow.py).

## Real-data verification remains blocked

`python scripts/run_smoke_test.py --release` exits **1**, correctly reporting:

```text
Release blocked: No validated scientific profiles loaded.
Required: planetary_profiles.parquet, earth_profiles.parquet
```

The processed folder contains no scientific profile tables and pipeline jobs
remain empty. Raw downloads are not automatically imported by the application.
The data audit found a readable Mars source and new land-dominated NASADEM tile;
the Moon binary still needs replacement. Exact study ROIs, source provenance,
mask handling and compatible physical-scale preprocessing must be completed
before a real reference-to-Earth ranking can be validated.

This verification establishes functional software behavior, not scientific
accuracy, full MVP acceptance, or production readiness.
