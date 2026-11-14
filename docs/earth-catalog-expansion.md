# Earth catalog expansion

Ten additional exploratory regions were selected before scoring and have now been
processed alongside the original Death Valley-area ROI. All eleven profiles pass
terrain QA. Regional names are orientation labels, not geological certification.

## Current acquisition state

All thirty extracted HGT/SWB/NUM files were supplied in
`data/raw/Earth/NASADEM_archives/`. Their byte sizes, raster grids, elevation
availability, water-mask classes and local checksums passed validation. They are
registered and processed; no Earthdata sign-in is needed to use the prepared app.
Original ZIPs were not supplied, so ZIP CRC and publisher checksum verification
remain unavailable. See [current rankings and validation](real-data-validation.md).

The instructions below support reproducing downloads or adding files later.
The importer also accepts complete extracted sets in the same directory.

## Download these ZIPs

Sign in with your [NASA Earthdata account](https://urs.earthdata.nasa.gov/).
Open each official ZIP link below and save it with its original filename in
`data/raw/Earth/NASADEM_archives/`. Keep the ZIPs intact; the importer extracts
and verifies the HGT, SWB water mask, and NUM members.

| Region | Tile / ZIP download | ROI center (lat, lon) | NASA metadata |
| --- | --- | --- | --- |
| Atacama-area exploratory ROI | [s24w069](https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/NASADEM_HGT.001/NASADEM_HGT_s24w069/NASADEM_HGT_s24w069.zip) | -23.5, -68.5 | [CMR](https://cmr.earthdata.nasa.gov/search/concepts/G2816780587-LPCLOUD.umm_json) |
| Namib-area exploratory ROI | [s25e015](https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/NASADEM_HGT.001/NASADEM_HGT_s25e015/NASADEM_HGT_s25e015.zip) | -24.5, 15.5 | [CMR](https://cmr.earthdata.nasa.gov/search/concepts/G2816781121-LPCLOUD.umm_json) |
| Afar-area exploratory ROI | [n13e040](https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/NASADEM_HGT.001/NASADEM_HGT_n13e040/NASADEM_HGT_n13e040.zip) | 13.5, 40.5 | [CMR](https://cmr.earthdata.nasa.gov/search/concepts/G2816780171-LPCLOUD.umm_json) |
| Oman exploratory ROI | [n22e058](https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/NASADEM_HGT.001/NASADEM_HGT_n22e058/NASADEM_HGT_n22e058.zip) | 22.5, 58.5 | [CMR](https://cmr.earthdata.nasa.gov/search/concepts/G2816798168-LPCLOUD.umm_json) |
| Altiplano-area exploratory ROI | [s20w068](https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/NASADEM_HGT.001/NASADEM_HGT_s20w068/NASADEM_HGT_s20w068.zip) | -19.5, -67.5 | [CMR](https://cmr.earthdata.nasa.gov/search/concepts/G2816779267-LPCLOUD.umm_json) |
| Qaidam-area exploratory ROI | [n37e095](https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/NASADEM_HGT.001/NASADEM_HGT_n37e095/NASADEM_HGT_n37e095.zip) | 37.5, 95.5 | [CMR](https://cmr.earthdata.nasa.gov/search/concepts/G2816851833-LPCLOUD.umm_json) |
| Saudi Arabia exploratory ROI | [n25e040](https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/NASADEM_HGT.001/NASADEM_HGT_n25e040/NASADEM_HGT_n25e040.zip) | 25.5, 40.5 | [CMR](https://cmr.earthdata.nasa.gov/search/concepts/G2816810237-LPCLOUD.umm_json) |
| Central Australia exploratory ROI | [s25e135](https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/NASADEM_HGT.001/NASADEM_HGT_s25e135/NASADEM_HGT_s25e135.zip) | -24.5, 135.5 | [CMR](https://cmr.earthdata.nasa.gov/search/concepts/G2816813233-LPCLOUD.umm_json) |
| Mojave-area exploratory ROI | [n34w116](https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/NASADEM_HGT.001/NASADEM_HGT_n34w116/NASADEM_HGT_n34w116.zip) | 34.5, -115.5 | [CMR](https://cmr.earthdata.nasa.gov/search/concepts/G2816845590-LPCLOUD.umm_json) |
| Central Sahara exploratory ROI | [n24e010](https://data.lpdaac.earthdatacloud.nasa.gov/lp-prod-protected/NASADEM_HGT.001/NASADEM_HGT_n24e010/NASADEM_HGT_n24e010.zip) | 24.5, 10.5 | [CMR](https://cmr.earthdata.nasa.gov/search/concepts/G2816802963-LPCLOUD.umm_json) |

## Import, process and validate

From the project folder in PowerShell:

```powershell
.venv/Scripts/python.exe scripts/expand_earth_catalog.py --register --build
```

This resumes from available ZIPs; it preserves existing raw files, validates member
names, byte sizes and ZIP CRCs, records archive/member SHA256 hashes, registers
sources and densified ROI boundaries, builds metric grids and profiles, and checks
independent scores, rank order, rejection handling, weight sensitivity, and UI/CSV
parity. Only processed profiles appear on the app map or in rankings. Sites failing
coverage thresholds are excluded from eligible results. Local hashes and ZIP CRCs
do not constitute independent publisher checksum verification.

If Earthdata access is already configured in a local `.netrc`/`_netrc`, use:

```powershell
.venv/Scripts/python.exe scripts/expand_earth_catalog.py --download --register --build
```

Browser sign-in alone does not authenticate the Python downloader. The manual ZIP
route works without configuring Python credentials. Never share passwords in chat
or save them in this repository. If NASA requests application authorization, complete
that step on the NASA site.

To refresh the public metadata checklist without acquiring protected rasters:

```powershell
.venv/Scripts/python.exe scripts/expand_earth_catalog.py
```

After import, inspect `data/processed/real_analysis.csv` and
`data/processed/real_validation.json`. The current validator verifies all candidates,
including full ordering and sensitivity rankings, against the Jezero reference.
The separate release check still requires a valid lunar profile and at least ten
eligible Earth sites per reference:

```powershell
.venv/Scripts/python.exe scripts/run_smoke_test.py --release
```

This is a preselected catalog search. Worldwide candidate discovery and expert
validation of analog suitability remain separate work.
