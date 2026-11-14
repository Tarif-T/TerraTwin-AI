# Discover and rank new Earth locations

The Discover Earth tab searches outside the existing catalog. It automatically
downloads public Copernicus GLO-90 elevation, water-mask and original XML metadata
for systematically sampled geographic tiles, builds real terrain profiles, applies
QA, and ranks new coordinates against a chosen Mars or Moon reference.

This is measured geographic discovery rather than a download checklist or a reranking
of the sixteen catalog profiles. Results are new to this catalog; their status as
previously unpublished scientific analogs remains unreviewed.

## App workflow

1. Open Discover Earth and choose a planetary target.
2. Enter west, south, east and north search bounds.
3. Choose a budget of 1–30 regions, then Discover and rank new Earth locations.
4. Watch background progress; cancel if needed. Completed runs remain selectable
   through Saved discovery search and Open saved discovery search.
5. Inspect ranked coordinates, feature differences, water/source coverage and maps.
   Download the ranking CSV, footprint GeoJSON and complete evidence JSON.

Only the explicit start action launches a network job. Ordinary Explore and Research
evidence workflows remain local. Jobs do not replace catalog tables or interrupt
the app. Search files, status, logs, saved metric grids and provenance remain under
the run directory; original downloads are cached separately with integrity receipts.

## Verified real example

A search submitted through the app form used bounds west -118, south 34, east -115,
north 36 and a four-region budget against the Jezero reference. Four new regions
were measured, all passed QA, and no tile downloads failed.

| Rank | Latitude | Longitude | Terrain similarity index / 100 |
| ---: | ---: | ---: | ---: |
| 1 | 34.50 | -116.50 | 96.9292 |
| 2 | 35.50 | -115.50 | 96.2552 |
| 3 | 34.50 | -117.50 | 93.8823 |
| 4 | 35.50 | -116.50 | 87.2762 |

The index uses the existing four-feature exponential terrain method. It is not a
probability of suitability or a claim these are the closest locations worldwide.
These ranks apply to the measured candidates in this particular bounded sample.

- [Verified ranking CSV](../data/processed/discovery/e5b6c63d91384fe2a33e8ed10e4ad500/rankings.csv)
- [Complete evidence, sources and footprints](../data/processed/discovery/e5b6c63d91384fe2a33e8ed10e4ad500/results.json)
- [Independent numerical and UI validation](../data/processed/discovery/e5b6c63d91384fe2a33e8ed10e4ad500/validation.json)

## Source interpretation and checks

The [public Copernicus GLO-90 collection](https://registry.opendata.aws/copernicus-dem/)
supplies 2021-release Cloud Optimized GeoTIFFs without an Earthdata login. Its
[AWS processing documentation](https://copernicus-dem-30m.s3.amazonaws.com/readme.html)
explains the tile naming and removed overlap rows. The original per-tile XML
identifies WGS84-G1150 horizontal coordinates and EGM2008 metre heights.

The elevation product is a digital surface model: vegetation, buildings, snow/ice
and infilled elevations may remain. It is not guaranteed bare terrain. Original
water masks are checked for matching dimensions, projection and alignment. Only
class 0 (no water) is retained; ocean, lake and river cells are excluded before
averaging. Class interpretation follows the Copernicus product handbook.

All candidates use 60 × 60 km local metric footprints, a 1 km analysis grid and
3 × 3 km roughness windows matching the planetary profiles. Cells with incomplete
source/land support remain masked. The normal 90% valid-cell and feature-coverage
gates control eligibility; rejected profiles remain visible rather than becoming
apparently good water/zero-elevation matches.

Downloaded objects have bounded sizes and retain URL, acquisition time, byte count,
ETag and SHA256 receipts. Simple 32-hex ETags are also checked against downloaded
MD5. This is object-integrity evidence, not independent scientific certification.
Modified caches fail validation. Saved result/CSV/request digests and raster digests
are checked on reopening; features and rankings are recomputed from the saved grids.
Full Copernicus attribution is retained in the app and evidence export.

## Search scope

- Supported in-app bounds are non-dateline boxes between 40 S and 40 N. At these
  latitudes a 60 km footprint fits inside a single degree tile. Polar discovery
  still uses the separate ArcticDEM workflow; the in-app search does not claim
  worldwide operational coverage.
- The source coverage index defines available tiles. Centers inside the box are
  filtered before scoring; centers within 60 km of existing catalog locations are
  excluded. The chosen budget samples an ordered latitude/longitude sequence evenly.
  Selection is deterministic and is not an equal-area or exhaustive global search.
- Bounds constrain centers; full 60 km footprints may extend outside the box.
- Ocean tiles absent from the coverage index are not invented. Download failures,
  absent masks and failed QA are recorded. A search may legitimately return fewer
  candidates than requested, or none.
- Each run saves its reference and scoring snapshot. Switching targets hides the
  previous target's results rather than displaying a stale ranking. A fresh search
  is needed for a different reference. Saved searches keep their original bounds.
- Terrain discovery does not establish matching geology, environment, resources,
  cave accessibility, land access rights, scientific novelty or mission suitability.

## Validation

130 tests pass, including bounded input validation, deterministic pre-score selection,
catalog-distance exclusion, receipt/MD5 checks, cache corruption, real metric-grid
processing with temporary synthetic rasters, water rejection, cancellation and saved
result corruption. Synthetic fixtures never enter production discovery results.

The real four-region search additionally passed independent scalar feature
recomputation, independent ranking arithmetic, app table/export parity, all three
download controls and clearing results when switching planetary targets. Its
form submission was exercised with actual public-source acquisition and a background
worker. No external expert or field validation is implied.

```powershell
.venv/Scripts/python.exe -m scripts.validate_discovery --run e5b6c63d91384fe2a33e8ed10e4ad500
.venv/Scripts/python.exe -m pytest -q
```
