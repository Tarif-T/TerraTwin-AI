# Challenge implementation and validation

## Current delivery

The app compares Mars and Moon study regions with ranked Earth candidates, maps
locations, shows differences, and exports reproducible results. It now supports
multi-domain research assessments. Scientific acceptance remains distinct from
functional software acceptance.

- Three references: Jezero, Shackleton south pole, Mare Tranquillitatis pit region.
- Sixteen Earth regions: desert, arid, volcanic, Arctic and Antarctic examples.
  Fifteen pass terrain QA; ArcticDEM 26_29 remains rejected rather than hidden.
- Fifty terrain/supporting source records; sixteen cached climate/geology summaries.
- Twenty-four scientific source records and twenty-nine scoped observations: eleven
  primary-source transcriptions plus thirteen original MEDA CSV/label/index/README records.
- Surface, volcanic-cave robotics, and water/ice research scenarios.
- An attributed novelty/expert review register, bounded acquisition planning,
  and checksummed evidence import with conflict rejection.

## Requirement coverage

| Requirement | Implemented capability | Scientific limit / outstanding evidence |
| --- | --- | --- |
| Moon/Mars terrain matching | 60 km footprints, 1 km grid, four features; ranked Earth shortlist | No spatial crater morphology, small hazards or landing-pad assessment |
| Geology | Earth centroid mapping; published Jezero and lunar mare material categories | No matched whole-ROI mineral maps; Shackleton geology unmeasured |
| Environment | Earth ERA5 climate; gravity context; real Jezero MEDA detector temperature/pressure for sols 100–101 with hourly charts and coverage | No matched local cross-body environment model or lunar thermal/illumination/radiation series |
| Resources | Published cave ice presence; strict compatible-abundance gate | Abundance and extraction feasibility unknown; no eligible resource ranking |
| Caves | Lunar pit/conduit setting; Lava Beds cave lengths/ice reports; volcanic-setting comparison | Pit depth is not cave length; traversability, stability and underground morphology unverified |
| Candidate discovery | Bounded ArcticDEM search and deterministic NASADEM acquisition plans | No worldwide completeness or uniform-area sampling; plans require acquisition and QA |
| New analog identification | Known Lava Beds baseline distinguished from unreviewed candidates; scoped literature records | No candidate certified novel; no prior report in a bounded search does not prove novelty |
| Findings presentation | Map, evidence cards, comparisons, research tables, domain breakdown, citations and CSV | Online basemap requires network; offline coordinate overview available |
| Validation | Numerical recomputation, UI/export parity and published-context regression | Not independent expert review, held-out scientific evaluation or field validation |

See [the MEDA environmental evidence report](meda-environment.md) for the latest
measurements, publisher checksum verification, sampling limits and uncertainty issue.

Resource rankings intentionally remain empty without comparable abundance measurements.
Earth air temperature is never compared to lunar surface temperature. Body-mean
pressure remains context rather than pretending to be local Jezero or Shackleton weather.
Environmental scoring currently uses gravity alone with a provisional partial-evidence
coverage of 0.5. Scenario weights remain uncalibrated engineering choices.

The cave scenario identifies Lava Beds as a known published baseline against Mare
Tranquillitatis. Its 90.90 contextual index reflects coarse terrain, material and
subsurface-setting overlap; it is not 90.90% mission suitability. The 95% configured
evidence coverage measures availability under that scenario, not confidence or
completeness of cave characterization. Named-cave reports provide regional context,
not measurements of every Earth ROI cell.

## Validation

- 121 automated tests pass; Ruff lint passes.
- All 19 profiles have independently recomputed features and deterministic raw-to-grid checks.
- Independent terrain arithmetic checks cover every reference and mission preset.
- All three real reference selectors pass UI/table/CSV parity checks.
- Nine research reference/scenario runs are deterministic and exported separately.
- Real research UI matches cave exports, clears stale scenario exports and reports missing resources.
- Local MEDA summaries reproduce the raw data and original labels; UI matches summaries
  and removes the local-data export when switching to a lunar target.
- Published-context regression confirms the known cave baseline and missingness gates.
  Published labels informed these checks; this is not independent scientific evaluation.

## Use the new workflows

In Research evidence, select a target and scenario, then Run evidence assessment.
Inspect domains, missing evidence, scoped observations and source links. Download
the assessment CSV for inputs, observations, configuration, hashes and citations.

Plan additional Earth candidate regions generates a bounded acquisition plan. Save
the download in the project root as candidate_search.yaml and run:

```powershell
.venv/Scripts/python.exe scripts/expand_earth_catalog.py --candidates candidate_search.yaml --download --register --build
```

Protected NASADEM downloads require Earthdata authentication. Planning is not
measurement: ocean, absent or incomplete granules may fail acquisition or QA.
Use the existing ArcticDEM workflow for high-latitude searches.

The review register saves append-only local records with reviewer, timestamp,
scope, citations and limitations. Reviewer identities are self-reported and
unverified. Saving a record does not automatically certify rankings or novelty.

Import additional measured evidence accepts the strict EvidenceBundle schema in
[science.py](../src/terratwin/science.py). Use [the current bundle](../data/metadata/science_evidence.json)
as a structural example: version, sources and observations. Source snapshots must
exist inside the workspace with matching SHA256 hashes. Subjects must be prepared
Earth site IDs, planetary profile IDs, or body:Earth/body:Moon/body:Mars.
Existing IDs cannot silently change; revised claims need new versioned IDs.

Resource comparison needs real water_ice_mass_fraction observations on both sides,
unit fraction, values 0..1, and matching statistics and spatial scopes. Never enter
guessed values to pass a gate. Unknown values stay null. Import checks structure
and provenance integrity; a reviewer must assess sampling compatibility and uncertainty.
No synthetic resource measurements are present in production data.

## Reproduce

Stop Streamlit before replacing Parquet files on Windows, then run:

```powershell
.venv/Scripts/python.exe -m scripts.prepare_cave_sites
.venv/Scripts/python.exe -m scripts.prepare_scientific_evidence
.venv/Scripts/python.exe -m scripts.prepare_meda
.venv/Scripts/python.exe scripts/build_profiles.py
.venv/Scripts/python.exe scripts/prepare_characterization.py
.venv/Scripts/python.exe scripts/validate_real_slice.py
.venv/Scripts/python.exe scripts/validate_research.py
.venv/Scripts/python.exe scripts/run_smoke_test.py --release
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check src scripts tests app.py
```

## Evidence

- [Terrain numerical validation](../data/processed/real_validation.json)
- [Research regression report](../data/processed/research_validation.json)
- [Mars terrain ranking](../data/processed/mars_analysis.csv)
- [Shackleton terrain ranking](../data/processed/moon_analysis.csv)
- [Pit-region terrain ranking](../data/processed/moon_tranquillitatis_pit_60km_v1_analysis.csv)
- [Pit-region cave evidence assessment](../data/processed/moon_tranquillitatis_pit_60km_v1_cave_robotics_evidence.csv)
- [Scientific observations and citations](../data/metadata/science_evidence.json)
- [Jezero MEDA environmental summary CSV](../data/processed/jezero_meda_sols100_101.csv)
- [Terrain source manifest](../data/metadata/sources.csv)

Curated snapshots are labeled structured transcriptions of inspected primary
sources, not publisher-provided HTML checksums. MEDA records retain original
publisher responses and verify CSV MD5 against the original PDS labels.
Local hashes support integrity and
reproducibility, not scientific correctness or NASA endorsement. Original terrain
files, including the damaged lunar download, were preserved. New USGS 3DEP and
verified LOLA products were added separately.
