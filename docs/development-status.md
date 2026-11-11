# First implementation pass

## Guide review

All 23 pages of the supplied v1.0 guide were reviewed, including mandatory stack,
science constraints, canonical schemas, scoring pseudocode, acceptance tests and
the master implementation prompt. The implementation follows the requested
numerical-first sequence. The repository initially contained only a title README.

## Tickets

| Ticket | Status | Evidence / remaining work |
| --- | --- | --- |
| T-01 Scaffold | Implemented | Python 3.11 environment, package, config, Streamlit shell, README, license |
| T-02 Contracts | Initial implementation | Strict Pydantic schemas, manifest reader, >=10 synthetic test-only records; production records pending |
| T-03 Features | Implemented and unit-tested | Analytical slopes, relief, roughness, masks, empty samples, quality thresholds |
| T-04 PDS | Adapter prepared | Local audited metadata + GDAL; actual Mars/Moon product decoding not validated |
| T-05 Earth | Adapter prepared | Local NASADEM guardrails, metric ROI, masks, no upsampling; real clips pending |
| T-06 Real profiles | Not complete | No verified source rasters, ROI catalog or measured profiles |
| T-07 Scoring | Implemented and unit-tested | Identity, monotonicity, missingness, deterministic ordering, quality and export checks |
| T-08/T-09 App/evidence/export | Initial integration | Empty-state smoke tested; real-data golden path pending |
| T-10 Integration/offline | Partial | Synthetic raster mechanics and empty app offline; real prepared-data release blocked |
| T-11 Compare/weights | Deferred P1 | No production sliders or two-site page yet |
| T-12 Pitch | Not complete | Demo script covers honest prototype state; real screenshots pending |

## Commands and assumptions

The environment was created with `uv venv --python 3.11 .venv` and dependencies
installed with `uv pip install --python .venv/Scripts/python.exe -e '.[dev]'`.
Validation commands are documented in [README](../README.md).
The first pass has 56 passing tests, clean Ruff checks, compatible dependencies,
and a verified browser-rendered shell. See [verification evidence](verification.md).

Assumptions introduced: fully valid roughness windows, central differences with
edge exclusion, effectively complete source support for aggregated ground cells,
conservative missing-reference coverage (resolves a discrepancy in the PDF), and
explicit manually audited metadata for PDS semantics. Details are in
[methodology](methodology.md).

New dependencies are declared in [pyproject.toml](../pyproject.toml). Affine is
constrained below version 3 because Rasterio 1.4 emits deprecation warnings with
Affine 3. The tested environment is captured in
[constraints](../constraints-py311-windows.txt).

## Next exact tasks

1. Validate one real MOLA and one LOLA product against labels/SIS and shaded relief;
   select scientific reference geolocations and body-correct local ROIs.
2. Obtain two NASADEM clips and their ground masks/metadata through authorized
   Earthdata access; document exact Earth polygons and provenance.
3. Enforce automated polygon/analysis footprint equivalence and complete parent
   provenance for any converted/mosaicked products.
4. Generate the first real profiles, independently check feature values, run a
   genuine comparison, and expand to >=10 geographically distinct Earth ROIs.
5. Exercise map/table/details/CSV parity with real profiles, supply an offline map
   fallback, run sensitivity analysis, and complete scientific/release review.

No credentials are required to run the shell/tests. A working empty app does not
satisfy the guide's real-data release criteria.
