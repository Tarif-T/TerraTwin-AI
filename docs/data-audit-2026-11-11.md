# Download inspection - November 11, 2026

All original files under `data/raw/` were inspected without modification. Checks
included SHA256 hashing, label/XML parsing, full raster block reads and sample
comparisons with the official archive. No scientific profiles were produced.

## Results

| Dataset | Result | Required action |
| --- | --- | --- |
| Mars MEGT44N000HB | Complete and readable at the structural level | Prefer PDS4 XML decoding; configure and verify ROI/provenance before extraction |
| Moon LDEM_64 | Binary differs from the official product | Re-download the IMG as binary; preserve the suspect copy for comparison |
| Earth NASADEM_HGT_s01w047 | Three layers present and structurally readable; mostly water | Obtain land-dominated tiles for documented terrestrial analog ROIs and preserve original download metadata |

## Mars

Local files: [IMG](../data/raw/Mars/megt44n000hb.img),
[PDS4 XML](../data/raw/Mars/megt44n000hb.xml),
[PDS3 label](../data/raw/Mars/megt44n000hb.lbl),
[ENVI header](../data/raw/Mars/megt44n000hb.hdr).

- Product: MEGT44N000HB.IMG, MOLA MEGDR topography, version 2.0 in PDS3.
- Expected and actual raster size: 129,761,280 bytes (5632 x 11520 signed 16-bit cells).
- Labels, header and raster are readable. Full raw range: -5062 to 3210 metres.
- Correct body radius in the source projection: 3,396,000 m.
- PDS4 grid spacing: 463.0576672 m. Footprint is approximately 0-44 N, 0-90 E.
- An HTTP range request to the official raster returned total length 129,761,280;
  its first 80 bytes match the local file. This is a sample comparison, not a full
  authoritative archive checksum comparison.
- Important: opening the IMG through its ENVI header treats 0 as nodata and masks
  27,474 zero-valued cells. The PDS4 XML has no declared missing constant and retains
  those values. Do not let the companion header silently remove valid zero elevation.
- PDS3 decoding uses rounded 463 m spacing and differs from the PDS4 grid transform.
  Prefer the maintained PDS4 XML and validate its footprint independently.
- Labels disclose interpolation where MOLA shot bins have no observations. Full
  raster readability does not imply complete direct altimeter observation coverage.

## Moon

Local files: [IMG](../data/raw/Moon/ldem_64.img),
[PDS4 XML](../data/raw/Moon/ldem_64.xml),
[PDS3 label saved with .txt suffix](../data/raw/Moon/ldem_64.lbl.txt).

- Expected size from dimensions: 11520 x 23040 x 2 = **530,841,600 bytes**.
- Actual local size: **530,918,904 bytes**, an excess of **77,304 bytes**.
- Official HTTP range response confirms total length **530,841,600 bytes**.
- Official first bytes: `3f 00 2e 00 3e 00 44 00 ...`.
- Local first bytes: `ff fe 3f 00 2e 00 3e 00 44 00 ...`.
- The local extra `ff fe` is consistent with a UTF-16LE byte-order mark. The file
  appears to have undergone text handling, but the precise cause is not established.
  Removing two bytes alone will not resolve the additional length discrepancy.
- GDAL can read the specified number of samples through the XML despite this
  corruption. Successful raster opening is therefore not an integrity check.
- Local full raw range is -18229 to 21514; label statistics are -18251 to 21546.
- Re-download the IMG using a binary downloader or browser Save Link As. Do not
  open/save the raster in a text editor. Keep its original filename and compare
  the exact byte count after download.
- The label content parses, but its filename should be `ldem_64.lbl` when preparing
  the standard companion-file set. Its existing `.lbl.txt` file has been preserved.
- Once the binary is corrected, distinguish relative HEIGHT = DN * 0.5 m from
  PLANETARY_RADIUS = DN * 0.5 + 1,737,400 m. The current generic intake needs a
  product-specific interpretation for this distinction before pipeline acceptance.

Official [Moon file directory](https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/lrolol_1xxx/data/lola_gdr/cylindrical/img/).

## Earth

Local [NASADEM tile folder](../data/raw/Earth/NASADEM_HGT_s01w047/).

- `s01w047.hgt`: 25,934,402 bytes, exactly 3601 x 3601 signed 16-bit samples.
- `s01w047.num`: 12,967,201 bytes, exactly one byte per sample.
- `s01w047.swb`: 12,967,201 bytes, exactly one byte per sample.
- Elevation is readable in WGS84; raw range -90 to 100 m. Nominal tile bounds:
  1 S to 0 latitude and 47 W to 46 W longitude. Rasterio includes half-cell pixel
  extents around the grid posts.
- Water mask: 1,165,552 land samples (8.98846%) and 11,801,649 water samples
  (91.01154%). Codes are 0=land and 255=water, according to the NASADEM user guide.
- This is a predominantly water-covered tile, not a good initial terrestrial
  terrain analog candidate. Zero-valued water elevations must be masked explicitly.
- Exact byte sizes and readable layers establish structural consistency, not
  independent proof of NASADEM version/authenticity. Original granule metadata,
  download URL, retrieval date and source checksum verification remain missing.
- Select documented, land-dominated candidate ROIs first, then download every tile
  intersecting each complete study footprint. Two initial Earth ROIs are needed;
  full MVP acceptance requires at least ten geographically distinct sites.

[NASADEM User Guide v1.2](https://lpdaac.usgs.gov/documents/1318/NASADEM_User_Guide_V12.pdf)
defines the elevation and ancillary layers and the water-mask codes.

## Local SHA256 inventory

| File | SHA256 |
| --- | --- |
| Mars/megt44n000hb.img | `14022166079edafc99650f354e5a634e6eb2c2ea544b444c01cd8ee55437df36` |
| Mars/megt44n000hb.xml | `f6de640ed5603eb03395616214c9a5707c9d49273f699d2cbeec53e93df6bd08` |
| Mars/megt44n000hb.lbl | `bc624a238ba6d71a770a09f959ead96f1c144970fae435b8ca5e26208b42eec5` |
| Mars/megt44n000hb.hdr | `4871add22f0e8096281ea6c3b79fc0555a541cf72785e4abe87055e38970d20a` |
| Moon/ldem_64.img (suspect) | `da1658dc96bb8969be7ef10d571e08320a4793817ab2f91466311fc34b8ae764` |
| Moon/ldem_64.xml | `13d388574ee3ac3f5afb66a1ca6aea6c42fcb38ecad8e8f9b4dc08f6964b6c18` |
| Moon/ldem_64.lbl.txt | `4e7a94c76c716a147b21ccf07669d004246b0d1b017b7d63d50befaa1a34142d` |
| Earth/s01w047.hgt | `d2828f928e3469e06001224057cb8ef896d421f68bac1c5e1e9db98bd57af2bd` |
| Earth/s01w047.num | `a9c109e902035118c716ef1578fef295b7276d03085effc35076318ff130154d` |
| Earth/s01w047.swb | `64bf537445ac81a20b868f0337413dda75b7cb4bdb32b0c08ac202e5d12c09e5` |

These are locally computed hashes for the inspected files, not publisher-issued
integrity certificates. No inspected raw file was renamed, repaired or overwritten.
