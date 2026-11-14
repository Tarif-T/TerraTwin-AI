# Current challenge expansion

Two references and 15 Earth profiles are prepared; 14 Earth profiles pass QA.
89 tests and the terrain dataset release gate pass. Mission presets, Earth
climate/geology context, systematic polar discovery and candidate comparisons
are implemented. Resources, caves and independent novelty/suitability review
remain incomplete. See [challenge progress](challenge-progress.md).

The earlier eleven-site milestone below is retained as development history.

# Development status

One real Mars reference and eleven distinct Earth profiles are prepared and numerically verified.
See [real-data validation](real-data-validation.md) for the actual measurements,
provenance, score and limits. The full two-body MVP remains blocked by missing valid lunar data.

## Guide review

All 23 pages of the supplied v1.0 guide were reviewed, including mandatory stack,
science constraints, canonical schemas, scoring pseudocode, acceptance tests and
the master implementation prompt. The implementation follows the requested
numerical-first sequence. The repository initially contained only a title README.

## Tickets

| Ticket | Status | Evidence / remaining work |
| --- | --- | --- |
| T-01 Scaffold | Implemented | Python 3.11 environment, package, config, Streamlit shell, README, license |
| T-02 Contracts | Implemented | Strict schemas and real manifest with 34 source members |
| T-03 Features | Implemented and unit-tested | Analytical slopes, relief, roughness, masks, empty samples, quality thresholds |
| T-04 PDS | Mars verified numerically | Actual MOLA decoded; full archive hash matches; Moon binary blocked |
| T-05 Earth | 11 real ROIs prepared | NASADEM HGT plus external SWB mask; bounds equivalence and source hashes checked |
| T-06 Real profiles | Partial | One Mars and eleven eligible Earth profiles; Moon missing |
| T-07 Scoring | Implemented and unit-tested | Identity, monotonicity, missingness, deterministic ordering, quality and export checks |
| T-08/T-09 App/evidence/export | Real slice working | Actual profile selection, score, evidence and CSV parity verified |
| T-10 Integration/offline | Partial | Real-grid independent arithmetic and deterministic processing verified; full release blocked |
| T-11 Compare/weights | Deferred P1 | No production sliders or two-site page yet |
| T-12 Pitch | Not complete | Demo script covers honest prototype state; real screenshots pending |

## Commands and assumptions

The environment was created with `uv venv --python 3.11 .venv` and dependencies
installed with `uv pip install --python .venv/Scripts/python.exe -e '.[dev]'`.
Validation commands are documented in [README](../README.md).
The current suite has 73 passing tests, including external masks, footprint
equivalence, PDS binary length rejection, NASADEM ZIP safeguards, append-only
registration, and independent multi-site ranking verification. Historical first-pass evidence is in
[verification](verification.md); current real-data evidence is in
[real-data validation](real-data-validation.md).

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

1. Replace and interpret the damaged LOLA IMG; define a documented lunar ROI.
2. Eleven Earth profiles are operational. Review the real ranking evidence and
   broaden the candidate catalog if the research question requires wider coverage.
3. Independently verify the Earth original ZIP against the provider where possible.
4. Review real rankings against independent expert assessments and literature;
   tune weights only with separated calibration/evaluation sites.
5. Supply an offline basemap fallback, broaden sensitivity analysis and complete
   the full two-body/ten-site scientific acceptance review.

No credentials are required to browse the prepared prototype. The working limited
comparison does not satisfy the guide's full real-data release criteria.
