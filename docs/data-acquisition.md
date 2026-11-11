# Real data acquisition and intake contract

No verified rasters, Earth ROI polygons or scientific feature rows have been
prepared. Exact Earth tile IDs cannot be selected before the actual ROI footprints
are documented. Do not fill the catalog with approximate coordinates from the seed
names in the architecture guide.

## Required files and current state

| Body | Required local source | State |
| --- | --- | --- |
| Mars | MOLA MEGDR topography IMG, original PDS XML/LBL and any companion HDR | Not downloaded; candidate `megt44n000hb.img` at 128 pixels/degree, for the proposed Jezero-area investigation |
| Moon | LOLA GDR topography IMG and original XML/LBL | Not downloaded; global `ldem_64.img`, `ldem_64.lbl`, `ldem_64.xml` identified in the official directory; final study ROI not selected |
| Earth | NASADEM_HGT.001 elevation tiles/clips, original metadata, and a validated ground/nodata mask | None downloaded; first two then at least ten geographically distinct ROI footprints required |

Archive filenames above were located in the official directories on November 10,
2026; their raster bytes, checksums, scale and georeferencing have **not** been
validated. They are acquisition candidates, not accepted sources. A 1 km grid is
provisional until actual source spacing supports it at every ROI.

- [MOLA archive and naming rules](https://pds-geosciences.wustl.edu/missions/mgs/megdr.html)
- [Candidate MOLA directory](https://pds-geosciences.wustl.edu/mgs/urn-nasa-pds-mgs_mola_topography_derived/meg128/)
- [LOLA archive](https://pds-geosciences.wustl.edu/missions/lro/lola.htm)
- [LOLA cylindrical IMG directory](https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/cylindrical/img/)
- [NASADEM_HGT.001 DOI](https://doi.org/10.5067/MEaSUREs/NASADEM/NASADEM_HGT.001)

The DOI fetch returned HTTP 403 from the research tool during this pass. Authorized
Earthdata access/manual download may be needed. No credentials were supplied or
accessed. Do not substitute a different DEM silently.

## Procedure

1. Select documented study-region coordinates and an exact physical ROI, without
   inspecting analog scores first. Preserve the scientific geolocation citation.
2. Download original products/labels into `data/raw/` using an authorized pathway.
   Preserve source filenames and documentation. Use the topography layer, never
   radius, areoid, counts or uncertainty as elevation.
3. Inspect labels/SIS for body, latitude type, longitude convention, radii, vertical
   datum, orientation, nodata, unit and scale/offset. Verify GDAL's decoded CRS and
   a shaded-relief view independently before accepting an interpretation.
4. For tiled Earth ROIs, mosaic and mask water offline first. The current adapter
   accepts one single-band raster per job; retain original provenance for the
   intermediate mosaic. NASADEM ROIs must lie wholly between 56 S and 60 N.
5. Register a complete manifest row in [sources.csv](../data/metadata/sources.csv).
   The `source_id` should identify the exact product, not just its dataset family.
   Preserve provider, version, rights, original URLs, retrieval timestamp, SHA256,
   body/datum, source pixel spacing and ROI ID. One source row currently associates
   a local input file with one ROI. Multi-file provenance/mosaic acquisition needs
   additional parent-product tracking before scientific acceptance.
6. Add verified Earth GeoJSON polygon(s) and their documented centroid/identity to
   [the catalog](../data/catalog/earth_sites.geojson). Coordinates are WGS84 and
   the centroid must be covered by the polygon. No synthetic catalog entries.
7. Add a local interpretation YAML beside the original files and a preparation
   job to [pipeline.yaml](../config/pipeline.yaml), using the fields below.
8. Validate sources and adapters, build profiles, inspect QA reports, cross-check
   features independently, and run the release gate. Source/rights and visual
   plausibility reviews remain human scientific validation steps.

## Interpretation YAML fields

All fields are required. This is a field contract, **not** a usable scientific
record; do not copy invented numerical defaults into a product interpretation.

| Field | Required meaning |
| --- | --- |
| `body` | Earth, Mars or Moon |
| `product_type` | `topographic_elevation` only |
| `source_crs` | Exact audited CRS/WKT, with correct planetary geometry |
| `horizontal_datum`, `vertical_datum` | Exact descriptions matching manifest |
| `latitude_type` | `geodetic`, `planetocentric` or `planetographic` |
| `longitude_convention` | `-180_180` or `0_360` |
| `sample_unit` | `m`; conversion to metres must be included in scale/offset |
| `scale`, `offset`, `nodata` | Explicit finite values established from source documentation |
| `label_path` | Original label/metadata path relative to interpretation YAML |
| `label_sha256` | SHA256 of that original metadata file |
| `interpretation_evidence` | Label fields/SIS section supporting the interpretation (>=20 characters) |

The finite nodata contract intentionally blocks products whose missing-value
semantics have not been established. GDAL scale metadata are not applied twice:
Rasterio raw samples are converted once with the audited scale/offset.

## Pipeline job fields

Each `jobs` entry contains `raster_path`, `interpretation_path`, `source_id`,
`destination_crs`, `bounds_m: [left, bottom, right, top]`, and an `identity` mapping.
Paths resolve from the repository root. Destination CRS must be a body-correct
local metric projection; bounds must match the declared square footprint.

The identity mapping contains `profile_id`, `region_name`, and `roi_id`; Earth
also needs `site_id`, `site_name`, `country`, `centroid_lat`, and `centroid_lon`
matching its catalog entry. Measurements, QA, hashes, source IDs, scale and body
are pipeline-generated and cannot be overridden by identity fields.

The current intake checks polygon/centroid identity but does not yet prove the
catalog polygon equals the projected analysis footprint. Verify that manually
before accepting any scientific output; automated footprint-equivalence checks
are a remaining ticket.

## Blocking and unsupported inputs

Missing files/labels/checksums, unknown units/semantics, wrong planetary radii,
unsupported GDAL decoding, rotated grids, non-north-up orientation, coarse source
resolution, ROI mismatch and NASADEM coverage violations block processing.
Dateline/polar study regions and automatic longitude-branch reconciliation are
not validated yet. Manually interpreted metadata must not conceal those cases.

Original source rasters are not included in Git. Do not distribute small clips or
derived tables until the exact dataset's rights and attribution are reviewed.
