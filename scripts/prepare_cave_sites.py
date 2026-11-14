"""Prepare real cave-region terrain and a new lunar pit-region reference.

Published cave dimensions remain separate from kilometre-scale terrain metrics.
USGS native elevations are area-averaged to ~30 m to bound subsequent ROI reads.
ESA WorldCover masks water/unknown classes on the derived source grid.
"""

import csv
import json
from datetime import datetime, timezone

import numpy as np
import rasterio
import yaml
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.vrt import WarpedVRT

from scripts.prepare_challenge_data import obtain
from terratwin.config import ROOT, read_yaml
from terratwin.geo.regions import geographic_ring
from terratwin.ingest.manifest import load_manifest, sha256_file
from terratwin.models import SourceRecord

USGS = "https://prd-tnm.s3.amazonaws.com/StagedProducts/Elevation/13/TIFF/current/n42w122/"
WC = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
LOLA = (
    "https://pds-geosciences.wustl.edu/lro/lro-l-lola-3-rdr-v1/"
    "lrolol_1xxx/data/lola_gdr/cylindrical/img/"
)


def prepare():
    now = datetime.now(timezone.utc).isoformat()
    folder = ROOT / "data/raw/Earth/USGS_LavaBeds"
    folder.mkdir(exist_ok=True)
    original, label = folder / "USGS_13_n42w122.tif", folder / "USGS_13_n42w122.xml"
    obtain(USGS + original.name, original, limit=450_000_000)
    obtain(USGS + label.name, label)
    wc = folder / "ESA_WorldCover_10m_2021_v200_N39W123_Map.tif"
    obtain(WC + wc.name, wc, limit=100_000_000)
    derived, mask = folder / "USGS_n42w122_30m_average.tif", folder / "worldcover_land_uint8.bin"
    if not derived.exists() or not mask.exists():
        with rasterio.open(original) as src:
            shape = (src.height // 3, src.width // 3)
            data = src.read(1, out_shape=shape, resampling=Resampling.average)
            transform = src.transform * Affine.scale(src.width / shape[1], src.height / shape[0])
            meta = src.profile.copy()
            meta.update(width=shape[1], height=shape[0], transform=transform, compress="deflate")
            with rasterio.open(derived, "w", **meta) as dst:
                dst.write(data, 1)
            with (
                rasterio.open(wc) as cover,
                WarpedVRT(
                    cover,
                    crs=src.crs,
                    transform=transform,
                    width=shape[1],
                    height=shape[0],
                    resampling=Resampling.nearest,
                ) as aligned,
            ):
                classes = aligned.read(1)
                # Water=80, unclassified/nodata=0; snow/ice is not equated to water.
                np.isin(classes, [0, 80], invert=True).astype("uint8").tofile(mask)
    manifest_path = ROOT / "data/metadata/sources.csv"
    sources = load_manifest(manifest_path)
    pipeline_path = ROOT / "config/pipeline.yaml"
    pipeline = read_yaml(pipeline_path)
    catalog_path = ROOT / "data/catalog/earth_sites.geojson"
    catalog = json.loads(catalog_path.read_text())
    planetary_path = ROOT / "data/catalog/planetary_rois.json"
    planetary = json.loads(planetary_path.read_text())
    bounds = [-30000, -30000, 30000, 30000]
    roi_id = "earth_lava_beds_roi_60km_v1"
    notes = (
        "USGS 3DEP n42w122 native 1/3 arcsecond NAD83/NAVD88 metre elevations, "
        "downsampled exactly 3x using area averaging to bound native ROI memory. "
        "ESA WorldCover 2021 v200 nearest classes retain land except water(80)/unknown(0). "
        "Fixed tile-center ROI (41.5,-121.5) includes public Lava Beds cave area; "
        "surface features do not measure underground geometry."
    )
    records = []
    for source_id, dataset, path, url, pixel in [
        ("USGS_LAVA_BEDS_30M", "USGS_3DEP", derived, USGS + original.name, 30.9),
        ("USGS_LAVA_BEDS_NATIVE", "USGS_3DEP_native", original, USGS + original.name, 10.3),
        ("WORLDCOVER_LAVA_BEDS", "ESA_WorldCover", wc, WC + wc.name, 10),
        ("WORLDCOVER_LAVA_BEDS_MASK", "ESA_WorldCover_mask", mask, WC + wc.name, 30.9),
    ]:
        record = SourceRecord(
            source_id=source_id,
            provider="USGS / ESA WorldCover consortium",
            dataset=dataset,
            version="CONUS current / WorldCover 2021 v200",
            product_url=USGS + label.name,
            download_url=url,
            accessed_utc=now,
            license_or_rights="USGS public-domain elevations; WorldCover CC-BY 4.0, "
            "Zanaga et al. (2022), DOI 10.5281/zenodo.7254221; modified Copernicus Sentinel data",
            checksum_sha256=sha256_file(path),
            planetary_body="Earth",
            horizontal_datum="WGS84" if dataset == "ESA_WorldCover" else "NAD83",
            vertical_datum="Not applicable: categorical land cover"
            if dataset.startswith("ESA_")
            else "NAVD88",
            pixel_size_m=pixel,
            processing_version="terrain_v1",
            roi_id=roi_id,
            processing_notes=notes + " Local hashes are not publisher checksums.",
        )
        if source_id in sources and sources[source_id].checksum_sha256 != record.checksum_sha256:
            raise ValueError("Registered cave-region source changed")
        sources[source_id] = record
        records.append((source_id, path))
    crs = "+proj=aeqd +lat_0=41.5 +lon_0=-121.5 +datum=WGS84 +units=m +type=crs"
    sidecar = ROOT / "data/metadata/interpretations/earth_lava_beds.yaml"
    with rasterio.open(derived) as ds:
        source_crs, nodata = ds.crs.to_wkt(), ds.nodata
    interpretation = dict(
        body="Earth",
        product_type="topographic_elevation",
        sample_unit="m",
        source_crs=source_crs,
        horizontal_datum="NAD83",
        vertical_datum="NAVD88",
        latitude_type="geodetic",
        longitude_convention="-180_180",
        scale=1,
        offset=0,
        nodata=nodata,
        latitude_bounds_deg=[24, 50],
        label_path="../../" + label.relative_to(ROOT / "data").as_posix(),
        label_sha256=sha256_file(label),
        mask_path="../../" + mask.relative_to(ROOT / "data").as_posix(),
        mask_sha256=sha256_file(mask),
        mask_land_value=1,
        interpretation_evidence=notes,
    )
    sidecar.write_text(yaml.safe_dump(interpretation, sort_keys=False), encoding="utf-8")
    identity = dict(
        profile_id="earth_lava_beds_60km_v1",
        site_id="earth_lava_beds",
        roi_id=roi_id,
        region_name="Lava Beds volcanic/cave-region study ROI",
        site_name="Lava Beds volcanic/cave-region study ROI",
        country="United States",
        centroid_lat=41.5,
        centroid_lon=-121.5,
    )
    if not any(j["identity"]["profile_id"] == identity["profile_id"] for j in pipeline["jobs"]):
        pipeline["jobs"].append(
            dict(
                raster_path=derived.relative_to(ROOT).as_posix(),
                interpretation_path=sidecar.relative_to(ROOT).as_posix(),
                source_id=records[0][0],
                destination_crs=crs,
                bounds_m=bounds,
                identity=identity,
                supporting_files={
                    key: path.relative_to(ROOT).as_posix() for key, path in records[1:]
                },
                warnings=["Cave dimensions and resource reports require separate site evidence."],
            )
        )
        catalog["features"].append(
            dict(
                type="Feature",
                geometry=dict(type="Polygon", coordinates=[geographic_ring(crs, "Earth", bounds)]),
                properties=dict(
                    **{
                        k: identity[k]
                        for k in (
                            "site_id",
                            "site_name",
                            "country",
                            "roi_id",
                            "centroid_lat",
                            "centroid_lon",
                        )
                    },
                    seed_or_candidate="known_analog_region",
                    reason_selected="Public NASA BRAILLE cave analog region; fixed center before "
                    "scoring",
                    analysis_crs=crs,
                    analysis_bounds_m=bounds,
                    area_km2=3600,
                    known_analog_reference="https://www.nasa-braille.org/about-braille/the-field-site/lava-tubes",
                    geolocation_source=USGS + label.name,
                ),
            )
        )
    lunar = ROOT / "data/raw/Moon/LOLA_global_verified"
    for ext in ("xml", "lbl", "img"):
        obtain(LOLA + "ldem_64." + ext, lunar / ("ldem_64." + ext), limit=550_000_000)
    moon_label, moon_image = lunar / "ldem_64.xml", lunar / "ldem_64.img"
    if moon_image.stat().st_size != 530841600:
        raise ValueError("New LOLA global image has incorrect byte count")
    lat, lon = 8.3355, 33.222
    crs = f"+proj=aeqd +lat_0={lat} +lon_0={lon} +R=1737400 +units=m +type=crs"
    moon_id, moon_roi, source_id = (
        "moon_tranquillitatis_pit_60km_v1",
        "moon_tranquillitatis_pit_roi_60km_v1",
        "LOLA_LDEM64_VERIFIED",
    )
    notes = (
        "New official global LOLA PDS4 image; corrupted original preserved. HEIGHT=DN*0.5; "
        "do not add radius offset. 60 km ROI centered on LROC Pits Atlas Mare Tranquillitatis "
        "pit (8.3355,33.222). 1 km terrain grid does not resolve pit or underground passage."
    )
    with rasterio.open(moon_label) as ds:
        moon_crs = ds.crs.to_wkt()
    sources[source_id] = SourceRecord(
        source_id=source_id,
        provider="NASA PDS / LOLA team",
        dataset="LOLA_GDR",
        version="1.0 PDS4",
        product_url=LOLA + moon_label.name,
        download_url=LOLA + moon_image.name,
        accessed_utc=now,
        license_or_rights="PDS public data; attribute NASA LRO LOLA team",
        checksum_sha256=sha256_file(moon_image),
        planetary_body="Moon",
        horizontal_datum="DE421 mean Earth/polar axis; sphere R=1737400 m",
        vertical_datum="Height above 1737400 m lunar reference sphere",
        pixel_size_m=473.802,
        processing_version="terrain_v1",
        roi_id=moon_roi,
        processing_notes=notes,
    )
    sidecar = ROOT / "data/metadata/interpretations/moon_tranquillitatis_pit.yaml"
    sidecar.write_text(
        yaml.safe_dump(
            dict(
                body="Moon",
                product_type="topographic_elevation",
                sample_unit="m",
                source_crs=moon_crs,
                horizontal_datum=sources[source_id].horizontal_datum,
                vertical_datum=sources[source_id].vertical_datum,
                latitude_type="planetocentric",
                longitude_convention="0_360",
                scale=0.5,
                offset=0,
                nodata=None,
                value_interpretation="lola_height",
                latitude_bounds_deg=[-90, 90],
                raster_data_path="../../" + moon_image.relative_to(ROOT / "data").as_posix(),
                label_path="../../" + moon_label.relative_to(ROOT / "data").as_posix(),
                label_sha256=sha256_file(moon_label),
                interpretation_evidence=notes,
            ),
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    if not any(j["identity"]["profile_id"] == moon_id for j in pipeline["jobs"]):
        pipeline["jobs"].append(
            dict(
                raster_path=moon_label.relative_to(ROOT).as_posix(),
                interpretation_path=sidecar.relative_to(ROOT).as_posix(),
                source_id=source_id,
                destination_crs=crs,
                bounds_m=bounds,
                identity=dict(
                    profile_id=moon_id,
                    roi_id=moon_roi,
                    region_name="Mare Tranquillitatis pit-region 60 km study",
                ),
                warnings=["Orbital pit/conduit evidence is separate from kilometre-scale terrain."],
            )
        )
        planetary["regions"].append(
            dict(
                profile_id=moon_id,
                roi_id=moon_roi,
                body="Moon",
                center_lat=lat,
                center_lon=lon,
                analysis_crs=crs,
                bounds_m=bounds,
                area_km2=3600,
                geolocation_source="https://lroc.im-ldi.com/atlases/pits/3",
                body_geographic_ring=geographic_ring(crs, "Moon", bounds),
            )
        )
    for path, value in ((catalog_path, catalog), (planetary_path, planetary)):
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    pipeline_path.write_text(yaml.safe_dump(pipeline, sort_keys=False), encoding="utf-8")
    with manifest_path.open("w", encoding="utf-8", newline="") as stream:
        rows = [s.model_dump(mode="json") for s in sources.values()]
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print("Registered Lava Beds and lunar pit-region terrain inputs", flush=True)


if __name__ == "__main__":
    prepare()
