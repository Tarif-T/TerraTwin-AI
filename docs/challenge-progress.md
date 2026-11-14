# Challenge development progress

## Delivered in this phase

- Real Moon support: NASA LOLA 20 m south-pole DEM, independently decoded HEIGHT=DN*0.5.
- A 60 x 60 km Shackleton study centered at USGS/IAU feature 5450 (-89.67,129.78).
- Original damaged global Moon download preserved and excluded.
- Antarctic REMA v2 surface model at the same 1 km measurement scale.
- Systematic, bounded ArcticDEM search: 3 additional fixed tile-centered ROIs.
- 15 Earth profiles total: 14 pass the 90% ground/source coverage threshold; one Arctic ROI fails and is excluded from eligible rankings.
- 15 geology interpretations from Macrostrat, preserving original geological-map citations.
- 15 Earth historical climate summaries (2015?2024 Copernicus ERA5 via Open-Meteo).
- Mission presets, evidence filters, candidate cards, two-site comparisons, measured terrain cross-sections, and an offline location overview.
- CSV exports contain location coordinates, selected mission/filters, climate, geology screening, evidence hashes and URLs.

## Current terrain rankings

### Mars reference

| Rank | Earth region | Terrain similarity / 100 |
| ---: | --- | ---: |
| 1 | Mojave-area exploratory ROI | 99.02 |
| 2 | Atacama-area exploratory ROI | 94.42 |
| 3 | Death Valley-area tile-centered ROI | 94.06 |
| 4 | Qaidam-area exploratory ROI | 92.63 |
| 5 | ArcticDEM search candidate 28_30 | 90.41 |

### Moon reference

| Rank | Earth region | Terrain similarity / 100 |
| ---: | --- | ---: |
| 1 | Antarctic REMA 18_35 tile-centered polar ROI | 51.18 |
| 2 | Qaidam-area exploratory ROI | 48.61 |
| 3 | Mojave-area exploratory ROI | 47.41 |
| 4 | Death Valley-area tile-centered ROI | 46.15 |
| 5 | ArcticDEM search candidate 28_30 | 45.34 |

## Scientific interpretation

Rankings still use four matched-scale terrain aggregates. Mission presets change
engineering weights; they are not trained or independently calibrated models.
The geological-fieldwork preset weights terrain for fieldwork and does not score
mineralogical similarity. Temperature, precipitation and lithology filters select
Earth field-test conditions; they do not imply environmental equivalence to Mars
or the Moon. Missing filter evidence never passes the requested condition.

Climate summaries describe the source model grid cell near each ROI centroid,
not a field station or a whole-ROI average. The model is fixed to ERA5 (0.25 degree)
for consistency. NASA POWER access failed; an initial ERA5-Land response lacked
precipitation, so that model is not used for the current summaries. Annual rainfall
is calculated only from complete calendar years; missing measurements remain null.

Geology describes mapped units at a single centroid, not geological proportions
of the 60 km footprint. The finest available mapping scale is selected; conflicting
maps at that scale are retained. Lithology classes come from explicit keyword
screening of original unit names, not inferred mineral concentrations.

ArcticDEM data masks retain only original SETSM cells, excluding filled/merged
and water-flattened cells. Snow/ice may remain. REMA is a surface model that may
include snow/ice; it is not a bare-rock analog survey. The lower-ranked or rejected
polar candidates are retained in the evidence rather than being discarded after
seeing scores. Candidate centers were chosen before scoring.

## Remaining challenge requirements

| Requirement | Current state | Work still needed |
| --- | --- | --- |
| Lunar and Mars terrain | Operational | Additional mission-specific targets and finer-scale hazard assessment |
| Geology | Real Earth centroid map context | Matched planetary/Earth geological distributions and mineral measurements |
| Environment | Real Earth temperature/precipitation context | Comparable planetary environment measurements, illumination and thermal models |
| Resources | Explicitly not assessed | Validated water/ice/mineral observations, uncertainty and extraction feasibility |
| Caves | Explicitly not assessed | Authoritative cave locations, morphology, access and subsurface evidence |
| Systematic candidate search | Bounded Arctic source-tile search | More regions/providers and a defensible global sampling strategy |
| Novelty | Every candidate unreviewed | Scoped literature search, baseline comparison and expert review |
| Scientific suitability | Not certified | Separated calibration/evaluation data and independent field validation |

No candidate is labeled a newly proven analog, a safe landing site, or a permanent
base location. A terrain grid with 1 km cells cannot resolve boulders, cave entrances,
wheel-scale hazards, or construction-scale ground conditions.

## Validation

- 89 automated tests pass, including lunar conversion, climate missingness, masks, presets, field filters, CSV provenance and body switching.
- Both real references pass raster QA with 100% retained analysis cells.
- All 17 stored profiles have independently checked features and deterministic source-to-grid reproduction.
- Independent arithmetic verifies ranking order and eligibility for every reference and mission preset.
- AppTest verifies real Mars and Moon table/CSV score parity and stale-result clearing.
- The release script now passes its two-reference / ten-eligible-Earth-site dataset gates. This does not certify the broader challenge or scientific suitability.

## Reproduce

```powershell
.venv/Scripts/python.exe scripts/prepare_challenge_data.py
.venv/Scripts/python.exe -m scripts.discover_earth_regions --max-tiles 3
.venv/Scripts/python.exe scripts/build_profiles.py
.venv/Scripts/python.exe scripts/prepare_characterization.py
.venv/Scripts/python.exe scripts/validate_real_slice.py
.venv/Scripts/python.exe scripts/run_smoke_test.py --release
.venv/Scripts/python.exe -m pytest -q
```

Stop the running Streamlit process before replacing prepared profile files on
Windows. File locks can prevent atomic replacement. Restart after the build.

## Evidence

- [Full numerical validation](../data/processed/real_validation.json)
- [Mars ranking CSV](../data/processed/mars_analysis.csv)
- [Moon ranking CSV](../data/processed/moon_analysis.csv)
- [Earth characterization](../data/processed/characterization.json)
- [Bounded discovery report](../data/metadata/discovery_report.json)
- [Source manifest](../data/metadata/sources.csv)

## Primary source documentation

- [LOLA polar source archive](https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/polar/img/)
- [USGS/IAU Shackleton coordinates](https://planetarynames.wr.usgs.gov/Feature/5450)
- [REMA source and citation](https://www.pgc.umn.edu/data/rema/)
- [ArcticDEM source and citation](https://www.pgc.umn.edu/data/arcticdem/)
- [PGC mask interpretation](https://www.pgc.umn.edu/guides/stereo-derived-elevation-models/pgc-dem-products-arcticdem-rema-and-earthdem/)
- [Open-Meteo historical API and ERA5 attribution](https://open-meteo.com/en/docs/historical-weather-api)
- [Macrostrat API](https://macrostrat.org/api)

Source data remain attributable to their providers. Local SHA256 hashes support
reproducibility but are not independent publisher checksum certification.
