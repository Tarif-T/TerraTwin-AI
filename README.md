# TerraTwin AI

An offline-first terrain analog shortlisting tool for Analognauts, built from the
TerraTwin AI MVP Technical Architecture Agent Guide (v1.0, November 10, 2026).

**Status: operational terrain shortlisting and scoped multi-domain evidence assessment.**
Three measured references (Jezero, Shackleton and Mare Tranquillitatis pit region)
are compared with 16 Earth regions; 15 Earth profiles pass terrain QA.
The app includes mission presets, Earth climate/geology context, published planetary
geology and cave evidence, resource missingness gates, bounded acquisition planning,
checksummed evidence import, and an attributed novelty/expert review register.
The local environmental view includes original Jezero MEDA detector temperatures
and derived pressure for sols 100–101, with publisher checksum verification,
hourly charts, sample coverage, uncertainty flags and CSV export.
Resource abundance, local cross-body thermal/radiation equivalence, cave traversability,
novelty and independent scientific suitability remain unvalidated.
See [the challenge progress report](docs/challenge-progress.md) for rankings,
validation, primary sources and the remaining research requirements.
See [the MEDA evidence report](docs/meda-environment.md) for local sensor data and limits.

The original damaged global lunar image was preserved. A newly downloaded public
LOLA polar product supplies Shackleton; a separate verified global LOLA download
supplies the pit-region reference. Antarctic REMA and a bounded
ArcticDEM search add polar candidates. The terrain dataset count/ranking gate
passes; it does not certify the full scientific challenge.

## Run locally

Use Python **3.11**. The project environment was created and tested with Python
3.11.14 on Windows. From the repository root in PowerShell:

```powershell
py -3.11 -m venv .venv
.venv/Scripts/python.exe -m pip install -c constraints-py311-windows.txt -e '.[dev]'
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m streamlit run app.py
```

If Python 3.11 is not installed and `uv` is available:

```powershell
uv venv --python 3.11 .venv
uv pip install --python .venv/Scripts/python.exe -c constraints-py311-windows.txt -e '.[dev]'
```

On Linux/macOS, substitute `.venv/bin/python` for `.venv/Scripts/python.exe`.
The constraints file records the tested Windows environment; other platforms may
need a new, tested resolution. Conda-forge is an alternative for GDAL/Rasterio if
binary wheels are unavailable. Do not change the system Python environment.

## What is implemented

- Pydantic contracts for measurements, provenance, profiles and scoring settings.
- Four physical-grid terrain features, with masks and valid sample counts.
- Exponential weighted similarity, explicit coverage gating, stable ranking and CSV export.
- Checksummed local NASADEM/PDS intake with audited interpretation sidecars.
- Bounded metric ROI reprojection, downsampling, quality checks and Parquet output.
- Explore, Methodology, Sources/readiness and Research evidence tabs; real user-facing profiles.
- Synthetic numerical and raster fixtures confined to tests and temporary directories.
- An app smoke test and a separate scientific release gate.

The PDS adapter delegates supported label decoding to GDAL and requires a manually
audited interpretation. It is **not** a universal PDS parser. The actual MOLA
products have been decoded and checked numerically, including the new LOLA polar DEM.
A valid metadata schema is not
evidence of a correct scientific interpretation.

## Prepare real data

Read [the acquisition guide](docs/data-acquisition.md) for required source products,
label/sidecar fields, ROI contracts, exact archive entry points and current blockers.
Large rasters and original labels belong under `data/raw/`, which is ignored by
Git. Audited sidecars are tracked under `data/metadata/interpretations/`.
Register source records in
[the manifest](data/metadata/sources.csv), verified Earth polygons in
[the catalog](data/catalog/earth_sites.geojson), and jobs in
[the pipeline configuration](config/pipeline.yaml).

To expand the existing study, download the ZIPs in the
[expansion checklist](docs/earth-catalog-expansion.md), keep their original filenames
in `data/raw/Earth/NASADEM_archives/`, then run:

```powershell
.venv/Scripts/python.exe scripts/expand_earth_catalog.py --register --build
```

The script resumes from available archives, validates ZIP members, appends source
records and ROIs, builds profiles, and verifies ranking order and UI/CSV parity.
If Earthdata credentials are already configured in a local `.netrc`/`_netrc`, add
`--download` to retrieve missing archives automatically. Do not put credentials
in source files or chat. `prepare_real_slice.py` below is only the initial two-ROI
bootstrap and intentionally refuses to overwrite an expanded study.

```powershell
.venv/Scripts/python.exe scripts/prepare_real_slice.py
.venv/Scripts/python.exe scripts/validate_sources.py
.venv/Scripts/python.exe scripts/prepare_planetary.py --config config/pipeline.yaml
.venv/Scripts/python.exe scripts/prepare_earth.py --sites data/catalog/earth_sites.geojson
.venv/Scripts/python.exe scripts/build_profiles.py --config config/pipeline.yaml
.venv/Scripts/python.exe scripts/validate_real_slice.py
.venv/Scripts/python.exe scripts/run_smoke_test.py
.venv/Scripts/python.exe scripts/run_smoke_test.py --release
```

The first two preparation scripts validate inputs; `build_profiles.py` performs
extraction. All CLIs support `--help` and exit nonzero on blocking input errors.
`prepare_real_slice.py` registers the exact inspected downloads, fetches metadata,
verifies the complete Mars image against PDS, and fixes the study footprints before
scoring. Original user download dates are unknown and recorded as such. It does
not require Earthdata credentials or rewrite raw images. The Earth ZIP publisher
checksum is unverified; that limitation is preserved in the app and exports.
The `--release` dataset count/ranking gate now passes for Mars and Moon.
Independent scientific assessment remains incomplete.

Expected prepared outputs are `data/processed/planetary_profiles.parquet`,
`data/processed/earth_profiles.parquet`, and
`data/processed/processing_manifest.json`. These files must be generated from
verified inputs; empty placeholder Parquet files are intentionally not checked in.

## Method and interpretation

The provisional analysis footprint is 60 x 60 km on a 1 km metric grid, with
a 3 x 3 cell roughness window. Coarser source data must trigger a coarser common
analysis scale. All compared profiles must share scale, footprint, feature version
and roughness kernel. See [methodology](docs/methodology.md) and
[limitations](docs/limitations.md).

Weights/tolerances in [scoring settings](config/scoring_v1.yaml) are engineering
defaults. The score is a **terrain similarity index**, not a probability, scientific
equivalence percentage, safety assessment or NASA endorsement. Absolute elevation
is never a scored feature. Climate, geology, composition and resources are not
part of baseline scoring.

## Verification and next milestones

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check .
.venv/Scripts/python.exe scripts/run_smoke_test.py
```

See [development status](docs/development-status.md) for ticket-level progress,
remaining acceptance criteria and known limitations. The Mars/one-Earth slice is
numerically verified; next obtain a corrected Moon raster and additional distinct
Earth ROIs, then assess scientific usefulness independently. See the saved CSV,
validation JSON and actual-grid terrain review under `data/processed/`.

## Attribution and license

Original code is Apache-2.0 licensed; see [LICENSE](LICENSE).
Dataset rights are independent of this code license. Small derived analysis grids,
profiles and source metadata are included; large original rasters are excluded.
See [source credits](docs/sources.md).
Credentials belong in environment variables or a local secret store, never Git.
