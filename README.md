# TerraTwin AI

An offline-first terrain analog shortlisting tool for Analognauts, built from the
TerraTwin AI MVP Technical Architecture Agent Guide (v1.0, November 10, 2026).

**Status: first implementation pass.** The numerical engine, local raster intake,
profile preparation, and Streamlit shell are implemented. No scientific reference
or Earth candidate profiles are bundled yet. The app deliberately says
**No validated scientific profiles loaded** and disables analysis until verified
products are prepared. This is not the completed scientific MVP.

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
- Explore, Methodology and Sources/readiness tabs; no synthetic user-facing results.
- Synthetic numerical and raster fixtures confined to tests and temporary directories.
- An app smoke test and a separate scientific release gate.

The PDS adapter delegates supported label decoding to GDAL and requires a manually
audited interpretation. It is **not** a universal PDS parser, and it has not yet
been validated against a real MOLA or LOLA raster. A valid metadata schema is not
evidence of a correct scientific interpretation.

## Prepare real data

Read [the acquisition guide](docs/data-acquisition.md) for required source products,
label/sidecar fields, ROI contracts, exact archive entry points and current blockers.
Large rasters, original labels, and local interpretation sidecars belong under
`data/raw/`, which is ignored by Git. Register verified source records in
[the manifest](data/metadata/sources.csv), verified Earth polygons in
[the catalog](data/catalog/earth_sites.geojson), and jobs in
[the pipeline configuration](config/pipeline.yaml).

```powershell
.venv/Scripts/python.exe scripts/validate_sources.py
.venv/Scripts/python.exe scripts/prepare_planetary.py --config config/pipeline.yaml
.venv/Scripts/python.exe scripts/prepare_earth.py --sites data/catalog/earth_sites.geojson
.venv/Scripts/python.exe scripts/build_profiles.py --config config/pipeline.yaml
.venv/Scripts/python.exe scripts/run_smoke_test.py
.venv/Scripts/python.exe scripts/run_smoke_test.py --release
```

The first two preparation scripts validate inputs; `build_profiles.py` performs
extraction. All CLIs support `--help` and exit nonzero on blocking input errors.
With the current empty manifest/catalog/job list, preparation and release checks
are **expected to fail with an actionable message**. The ordinary app smoke test
must pass even without scientific data.

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
remaining acceptance criteria and known limitations. The next scientific milestone
is a verified Mars/Moon/two-Earth raster availability checkpoint, then an end-to-end
real comparison. Expand to ten distinct Earth ROIs only after validating that slice.

## Attribution and license

Original code is Apache-2.0 licensed; see [LICENSE](LICENSE).
Dataset rights are independent of this code license. No third-party raster is
redistributed in this initial pass. See [source credits](docs/sources.md).
Credentials belong in environment variables or a local secret store, never Git.
