# Architecture

```text
Verified local MOLA / LOLA / NASADEM + original labels + source manifest
    -> audited metadata / checksum / CRS / orientation validation
    -> bounded metric ROI reprojection and mask-preserving aggregation
    -> pure terrain features + quality report
    -> canonical Profile validation
    -> planetary_profiles.parquet / earth_profiles.parquet / processing_manifest.json
    -> prepared-bundle validation + deterministic weighted scoring
    -> Streamlit evidence / local tables / CSV
```

Numerical modules under `src/terratwin/geo` and `src/terratwin/scoring` are
independent of Streamlit. Acquisition/preparation run offline through scripts;
the application never loads raw global rasters or requires Earthdata credentials.
There is no hosted backend, authentication, database, CNN or React application.

Canonical contracts live in [models.py](../src/terratwin/models.py). Config validation
is shared by the CLI and app. Unavailable products block scientific rankings;
synthetic fixtures are allowed only in tests and temporary directories.
