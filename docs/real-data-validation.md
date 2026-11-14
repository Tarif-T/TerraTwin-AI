# First real-data comparison

## Outcome

A real MOLA Jezero profile and real NASADEM Death Valley-area profile are prepared,
registered with provenance, loaded by Streamlit, and compared using scoring_v1.
The terrain similarity index is **94.0642908733 / 100**, with **100% weighted
feature coverage**. The app displays 94.06 / 100 and offers the matching CSV.

This is a numerically verified **limited prototype**, not a scientifically
validated analog discovery. There is only one Earth candidate. Rank 1 establishes
no superiority, the model's tolerances are broad engineering defaults, and four
aggregate features do not compare crater shape or spatial arrangement.

## Fixed study regions and scale

| Property | Mars | Earth |
| --- | --- | --- |
| Profile | mars_jezero_60km_v1 | earth_n36w117_60km_v1 |
| Region | Jezero crater study area | Death Valley-area tile-centered exploratory ROI |
| Center | 18.41 N, 77.69 E, planetocentric | 36.5 N, 116.5 W, WGS84 |
| Location evidence | [USGS/IAU Gazetteer feature 14300](https://planetarynames.wr.usgs.gov/Feature/14300) | [Original provider granule metadata](https://cmr.earthdata.nasa.gov/search/concepts/G2816846943-LPCLOUD.umm_json), tile midpoint |
| Physical footprint | 60 x 60 km | 60 x 60 km |
| Grid / roughness window | 1000 m / 3 x 3 km | 1000 m / 3 x 3 km |
| Projection | Local azimuthal equidistant, Mars sphere R=3396000 m | Local azimuthal equidistant, WGS84 |
| Vertical datum | MOLA GMM3 areoid | NASADEM EGM96 geoid |
| Retained raster cells | 3600/3600 (100%) | 3592/3600 (99.7778%) |

Centers and footprints were fixed before scoring. The Earth polygon is generated
from the physical bounds and checked by reprojection against the measured square.
The planetary footprint explicitly retains its Mars coordinate model; it is not
misrepresented as Earth WGS84 GeoJSON. Absolute heights are not compared in scoring.

## Measured features

| Feature | Mars | Earth | Component similarity |
| --- | ---: | ---: | ---: |
| Median slope (degrees) | 1.8805139866 | 1.6581225710 | 0.9780063251 |
| P90-P10 relief (m) | 697.9246059957 | 525.9304645946 | 0.8419841060 |
| Median local elevation standard deviation (m) | 28.2512684634 | 27.6888951072 | 0.9971920828 |
| Slope >15 degrees fraction | 0.0056480380 | 0.0161579892 | 0.9740673032 |

MOLA supplies 3364 valid slope and roughness samples. Earth supplies 3342 valid
slope and 3332 fully valid roughness samples. Boundary exclusion and masks explain
the derivative count differences. Masking SWB water removes eight aggregated Earth
cells relative to the otherwise identical unmasked preparation.

![Actual measured grids and hillshade](../data/processed/real_terrain_review.png)

The image was generated from the saved measurement grids and visually checked:
the Mars ROI contains crater-scale topography and the Earth ROI contains a basin
and rugged terrain. This is a plausibility review, not independent geolocation or
scientific suitability certification. Each elevation panel uses its own datum and
color scale. The different landform arrangements illustrate the model's limits.

## Provenance

[sources.csv](../data/metadata/sources.csv) registers four original source members:
MOLA MEGT44N000HB IMG and NASADEM n36w117 HGT, SWB and NUM. Supporting source hashes
are checked before processing and all four source IDs survive into the comparison.

- The full 129,761,280-byte MOLA IMG was streamed from PDS and SHA256 compared with
  the user's download. They match. [Integrity evidence](../data/metadata/evidence/mars_image_integrity.json).
- Original local Mars PDS4 XML matches the remotely retrieved XML. Processing uses
  the precise PDS4 grid and no invented nodata constant; zero remains valid terrain.
- NASADEM's original CMR granule record was retrieved, fixing collection version,
  footprint and exact download URL. Local HGT/SWB/NUM hashes and byte counts match
  the inspected files. The original ZIP's publisher checksum is not supplied in
  that metadata and has **not** been independently verified.
- The [NASADEM user guide](https://lpdaac.usgs.gov/documents/1318/NASADEM_User_Guide_V12.pdf)
  supports the big-endian metre heights, EGM96 datum and SWB interpretation.
- Original user download timestamps are unknown. Manifest access times identify
  metadata verification; notes explicitly distinguish them from raw download dates.
- MOLA has interpolated bins: 100% nonmissing coverage does not mean direct
  altimeter observations cover every cell. This limitation appears in the export.
- The processing manifest records all input/label/interpretation/config hashes,
  analysis-grid checksums, code digest, git commit, package versions, CRS and bounds.

No original raw raster was edited or replaced. Large original files remain ignored
by Git. The Moon binary is excluded because its byte count and contents remain invalid.

## Numerical and application validation

- Independent scalar calculations reproduce every stored feature with maximum
  absolute error **3.56e-15** (well below the 1e-8 acceptance tolerance).
- Repeating raw-to-metric-grid preparation produces exactly equal arrays, including masks.
- Independently recomputed scoring agrees within 1e-10; CSV retains unrounded scores.
- AppTest using the actual prepared files verifies the ranked table/CSV parity,
  working download control, and unavailable Moon clearing/blocking stale output.
- The live browser displays the actual Jezero reference, Earth candidate, measured
  score, evidence/source links and CSV control. Basemap loading is network dependent.
- **63 automated tests pass**, including new ground-mask application/checksum,
  mismatched-footprint rejection and corrupt PDS array length rejection. Ruff passes.

Changing each weight individually by +/-10% relative to its configured value,
then normalizing, gives scores from **93.77694 to 94.36942**. Removing slope gives
**91.57340**; removing roughness gives **92.65056**. These are limited sensitivity
checks; a one-candidate dataset cannot test ranking stability across sites.

## Reproduce and inspect

```powershell
.venv/Scripts/python.exe scripts/prepare_real_slice.py
.venv/Scripts/python.exe scripts/validate_sources.py
.venv/Scripts/python.exe scripts/prepare_planetary.py
.venv/Scripts/python.exe scripts/prepare_earth.py
.venv/Scripts/python.exe scripts/build_profiles.py
.venv/Scripts/python.exe scripts/validate_real_slice.py
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check .
```

The registration command expects the inspected raw downloads and caches verified
metadata and the remote MOLA integrity result. Rebuild after code/config changes.
Validation checks code/config/grid hashes and fails on stale artifacts. The regular
app reads prepared files and requires no download or Earthdata credential.

Outputs:

- [Analysis CSV](../data/processed/real_analysis.csv)
- [Machine-readable numerical validation](../data/processed/real_validation.json)
- [Processing manifest](../data/processed/processing_manifest.json)
- [Planetary profiles](../data/processed/planetary_profiles.parquet)
- [Earth profiles](../data/processed/earth_profiles.parquet)

The full `scripts/run_smoke_test.py --release` gate still fails as expected:
there is no valid Moon profile and fewer than ten distinct Earth sites. Next obtain
those inputs, complete Earth ZIP verification if available, expand independent
expert/literature review, and calibrate/evaluate on separate geographic regions.
