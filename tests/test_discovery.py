"""Synthetic source tiles test bounded, score-independent discovery proposals."""

import pytest

from scripts.discover_earth_regions import tile_proposals

VRT = """<VRTDataset><GeoTransform>-1200096,32,0,-1099904,0,-32</GeoTransform>
<VRTRasterBand><ComplexSource>
<SourceFilename>/vsis3/pgc-opendata-dems/arcticdem/mosaics/v4.1/32m/29_29/29_29_32m_v4.1_dem.tif</SourceFilename>
<DstRect xOff="0" yOff="0" xSize="3131" ySize="3131"/>
</ComplexSource></VRTRasterBand></VRTDataset>"""


def test_discovery_derives_geolocation_and_filters_bounding_box():
    proposals = tile_proposals(VRT, [-100, 72, -80, 78])
    assert len(proposals) == 1
    assert proposals[0]["longitude"] == pytest.approx(-90)
    assert proposals[0]["latitude"] == pytest.approx(75.0684143989)
    assert proposals[0]["source_url"].startswith("https://pgc-opendata-dems.s3.")
    assert tile_proposals(VRT, [-80, 72, -70, 78]) == []


def test_discovery_rejects_unsupported_domain():
    with pytest.raises(ValueError, match="Arctic region"):
        tile_proposals(VRT, [-100, -80, -70, -60])
