"""LOLA HEIGHT and polar-source boundaries are scientific intake requirements."""

import pytest

from terratwin.ingest.raster_input import RasterInterpretation, validate_lola_height


def test_lola_height_keeps_radius_offset_out_of_elevation(tmp_path):
    label = tmp_path / "SYNTHETIC.xml"
    label.write_text(
        """<Product_Observational xmlns="http://pds.nasa.gov/pds4/pds/v1">
    <Identification_Area><logical_identifier>urn:nasa:pds:lro_lola_rdr:data_gridded:ldem_test
    </logical_identifier></Identification_Area><Array_2D_Image><Element_Array>
    <data_type>SignedLSB2</data_type><scaling_factor>0.5</scaling_factor>
    <value_offset>1737400</value_offset></Element_Array></Array_2D_Image>
    </Product_Observational>""",
        encoding="utf-8",
    )
    metadata = RasterInterpretation(
        body="Moon",
        product_type="topographic_elevation",
        source_crs="+proj=stere +lat_0=-90 +R=1737400 +units=m +type=crs",
        horizontal_datum="SYNTHETIC Moon sphere",
        vertical_datum="Height above 1737400 m lunar reference sphere",
        latitude_type="planetocentric",
        longitude_convention="0_360",
        sample_unit="m",
        scale=0.5,
        offset=0,
        nodata=None,
        label_path=label.name,
        label_sha256="0" * 64,
        value_interpretation="lola_height",
        interpretation_evidence="SYNTHETIC TEST ONLY label",
    )
    validate_lola_height(label, metadata)
    with pytest.raises(ValueError, match="HEIGHT conversion"):
        validate_lola_height(label, metadata.model_copy(update={"offset": 1737400}))
    with pytest.raises(ValueError, match="HEIGHT conversion"):
        validate_lola_height(label, metadata.model_copy(update={"body": "Earth"}))
