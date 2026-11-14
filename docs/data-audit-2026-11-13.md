# Download recheck - November 13, 2026

Original raw files were not changed. Inspected file lengths, computed SHA256
hashes, reopened planetary labels, and read both Earth elevation and ancillary
arrays in full. This is input validation, not a completed scientific comparison.

| Input | Result |
| --- | --- |
| New NASADEM n36w117 | Structurally complete and readable; suitable to begin ROI preparation |
| Original NASADEM s01w047 | Unchanged; predominantly water |
| Mars MEGT44N000HB | All four files unchanged from the prior inspection; PDS4 label readable |
| Moon LDEM_64 IMG | Unchanged corrupted binary; still blocked |
| Moon PDS3 label | Extension corrected from .lbl.txt to .lbl; contents unchanged and readable |

## New Earth tile

The [Earth folder](../data/raw/Earth/NASADEM_HGT_s01w047/) contains both tiles.
Despite the folder's old s01w047 name, the new filenames identify n36w117.

- `n36w117.hgt`: 25,934,402 bytes; 3601 x 3601 signed 16-bit samples; WGS84.
- `n36w117.num` and `n36w117.swb`: each 12,967,201 bytes, matching the sample count.
- Nominal coverage: 36-37 N, 117-116 W. Raster extents include half a sample around
  the grid posts.
- Land: 12,943,909 cells, **99.82038%**. Water: **0.17962%**.
- Full ground elevation range: **-143 to 2168 m**.
- Ground P10 / median / P90: 205 / 915 / 1400 m. These are raw-tile checks, not
  matched-scale features or analog rankings.
- No elevation samples were masked by Rasterio's nodata rule. Water must still
  be excluded with the supplied SWB mask before terrain analysis.

Local SHA256 values:

| File | SHA256 |
| --- | --- |
| n36w117.hgt | `31395a35998dd9787daa3cbd8f501b42ee74f7609bd361c202eeb0cdb220f442` |
| n36w117.num | `121ca398c6d1a459e1a4cba480b88f8a8822088909235b13066f2884c34a3d2a` |
| n36w117.swb | `b32defe6d14e5fe87a10d6d3a63fec34d5160b921f1ad9a0ef8549db75dc7364` |

Original ZIP, exact download metadata, source URL, retrieval time and independent
publisher checksum verification are not present. Those provenance fields still
need registration before accepting scientific profiles.

## Remaining Moon blocker

[ldem_64.img](../data/raw/Moon/ldem_64.img) is still **530,918,904 bytes** rather
than the expected **530,841,600 bytes**. Its SHA256 is unchanged:
`da1658dc96bb8969be7ef10d571e08320a4793817ab2f91466311fc34b8ae764`.
It still starts with `ff fe`, the extra encoding marker identified by comparison
with the official binary in the [previous audit](data-audit-2026-11-11.md).
Renaming the label fixed its filename but did not repair this binary.

Re-download the original IMG as binary and retain its exact expected byte count.
Do not edit it with a text editor. No repair or replacement was attempted here.

## Next processing work

The Mars source and new Earth tile can enter study-ROI preparation, pending the
documented source/datum/mask checks. Define comparable physical footprints, apply
the Earth water mask, register provenance, and prepare actual feature profiles.
The full MVP still requires a corrected Moon source and at least ten distinct
Earth site profiles. No new production profiles have been generated in this audit.
