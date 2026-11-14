# Terrain comparison v1

## Physical comparability

Inputs must be topographic elevation, converted from the source's documented
scale/offset to metres, and projected using the correct body's coordinate model.
Earth WGS84/UTM must never define Mars or Moon geometry. The current adapter accepts
north-up, single-band products whose CRS GDAL can decode and whose interpretation
has been audited against the original label. Unknown semantics block processing.

Provisional defaults: square 60 km ROI, 1000 m analysis cells and a 3-cell roughness
window. The common scale may be changed only for all compared profiles, with the
physical roughness window reported. Source spacing is checked at nine locations
in the ROI; grids coarser than the target are rejected. This check is conservative
for local, ordinary study regions and is not validated for pole/dateline crossings.

Area-average downsampling preserves source masks. A destination cell must have
effectively complete valid source support (fraction >= 1 - 1e-6) to be retained.
This conservative rule avoids counting partially masked aggregates as fully
observed terrain. It may reject some otherwise useful boundary cells.

## Features

| Feature | Definition | Unit |
| --- | --- | --- |
| `slope_median_deg` | Median atan(hypot(dz/dx, dz/dy)) | degrees |
| `relief_p90_p10_m` | P90 minus P10 of valid ROI elevations | m |
| `roughness_local_std_m` | Median population standard deviation of fully valid square windows | m |
| `steep_fraction_15deg` | Fraction of valid slopes strictly greater than 15 degrees | 0-1 |

Slope uses central differences with metre spacing. The center and four adjacent
cells must all be valid. The outer edge is excluded. Roughness uses fully valid
windows, excludes edge windows, and divides by N (`ddof=0`). Relief uses all valid
ROI elevation cells. Invalid, masked and nonfinite raster cells are excluded from
measurements. Empty samples yield null, never zero. Elevation, slope and roughness
sample counts are recorded in the processing manifest.

There is no derivative margin in the current output ROI: the boundary is excluded
from derivative metrics consistently on every body. This is a documented first-pass
choice; buffered clipping remains a follow-up improvement.

## Scoring and missing measurements

For each available feature, similarity is `exp(-abs(earth-reference)/tolerance)`.
The index is 100 times the weighted mean of available similarities. Weights are
normalized using accurate floating-point summation. Missing features contribute
neither a value nor a weight to the score denominator.

Weighted coverage is available weight divided by all configured weight. The PDF's
section 8.3 suggests adjusting the denominator for missing reference features,
while its formula and pseudocode retain all configured weights. This implementation
follows the latter, more conservative rule: missing reference features reduce
coverage and are disclosed, alongside `reference_feature_coverage`. This prevents
an incomplete reference from appearing fully comparable.

Eligibility requires coverage >= 0.75, `qa_pass`, and raster validity >= 0.90 for
both reference and candidate. A reference failing raster quality blocks the run.
Eligible sites sort by descending index, descending coverage and ascending site ID.
Rejected sites have no rank and remain visible separately. Mismatched physical
scales or feature definitions block comparison rather than being silently accepted.

Engineering defaults from the guide: weights 0.40/0.30/0.20/0.10 and tolerances
10 degrees / 1000 m / 200 m / 0.40 in the feature order above. These require
sensitivity review on real data. Scores imply no probability or cross-body
environmental equivalence.

## Reproducibility

CSV exports retain unrounded scores, active normalized weights, tolerances,
thresholds, source IDs, reference ID, physical scale and processing version.
Input hashes cover canonical sorted profile records; run IDs also include scoring
settings. The processing manifest records source/label/interpretation/config
checksums, grid bounds, CRS, sample counts, git commit and numerical package versions.
Creation timestamps change across preparation runs; the numerical calculations and
ordering remain deterministic for fixed inputs/configuration.

The first real slice uses Jezero's USGS/IAU Gazetteer center (18.41 N, 77.69 E)
and the n36w117 provider-tile midpoint (36.5 N, 116.5 W). Both local azimuthal
equidistant study grids cover 60 x 60 km. These choices were fixed before scores
were examined. Earth selection reflects available data, not a scored discovery.
Analysis rasters and their checksums are saved alongside profiles. A second,
scalar-loop implementation independently checks features and the score; raw-to-grid
repeat processing checks determinism. These checks establish numerical agreement
on the same grids, not independent expert validation of analog suitability.
