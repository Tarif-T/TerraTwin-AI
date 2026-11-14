"""Synthetic MEDA tables exercise units, checksums, missingness and sampling support."""

import hashlib
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from terratwin.config import content_hash
from terratwin.environment import load_meda_context
from terratwin.ingest.meda import summarize_meda
from terratwin.science import Observation, compare_observations


@pytest.fixture
def meda_table(tmp_path):
    csv = tmp_path / "synthetic.CSV"
    csv.write_bytes(
        b"SCLK,LMST,LTST,PRESSURE,PRESSURE_UNCERTAINTY,TRANSDUCER\r\n"
        b"10,00100M00:00:00.000,test,750,,1\r\n"
        b"10.5,00100M00:00:00.500,test,9999999999,,1\r\n"
        b"11,00100M00:00:01.000,test,,,1\r\n"
    )
    fields = "".join(
        f"<Field_Delimited><name>{name}</name><unit>{unit}</unit></Field_Delimited>"
        for name, unit in [
            ("SCLK", "second"),
            ("LMST", ""),
            ("LTST", ""),
            ("PRESSURE", "pascal"),
            ("PRESSURE UNCERTAINTY", "kelvin"),
            ("TRANSDUCER", ""),
        ]
    )
    label = tmp_path / "synthetic.xml"
    label.write_text(
        f"""<Product_Observational xmlns="http://pds.nasa.gov/pds4/pds/v1"
        xmlns:m="http://pds.nasa.gov/pds4/mission/mars2020/v1">
        <Identification_Area><logical_identifier>urn:nasa:pds:mars2020_meda:data_derived_env:we__0100_der_ps_test</logical_identifier><version_id>test</version_id></Identification_Area>
        <Observation_Area><Time_Coordinates><start_date_time>2021-05-31T22:23:00Z</start_date_time>
        <stop_date_time>2021-06-01T22:06:16Z</stop_date_time></Time_Coordinates>
        <m:start_sol_number>100</m:start_sol_number></Observation_Area>
        <File_Area_Observational><File><file_name>{csv.name}</file_name>
        <file_size>{csv.stat().st_size}</file_size><md5_checksum>{hashlib.md5(csv.read_bytes()).hexdigest()}</md5_checksum></File>
        <Table_Delimited><records>3</records><field_delimiter>Comma</field_delimiter>
        <Record_Delimited>{fields}</Record_Delimited></Table_Delimited></File_Area_Observational>
        </Product_Observational>""",
        encoding="utf-8",
    )
    return csv, label


def test_sentinels_and_blank_values_do_not_become_measurements(meda_table):
    result = summarize_meda(*meda_table)
    stats = result["summaries"][0]
    assert result["publisher_md5_verified"]
    assert stats["sample_count"] == 1 and stats["missing_count"] == 2
    assert stats["observed_median"] == stats["observed_min"] == stats["observed_max"] == 750
    assert stats["occupied_sclk_second_bins"] == 1
    assert stats["approximate_sol_time_coverage"] < 0.00002
    assert stats["instrument_uncertainty"] is None
    assert stats["uncertainty_label_unit"] == "kelvin"
    assert result["hourly"][1]["median"] is None


def test_publisher_checksum_detects_same_length_corruption(meda_table):
    csv, label = meda_table
    csv.write_bytes(csv.read_bytes().replace(b",750,", b",760,"))
    with pytest.raises(ValueError, match="MD5"):
        summarize_meda(csv, label)


@pytest.mark.parametrize(
    "old,new,expected",
    [
        ("<unit>pascal</unit>", "<unit>kelvin</unit>", "unit"),
        ("<records>3</records>", "<records>4</records>", "record count"),
        ("<m:start_sol_number>100", "<m:start_sol_number>101", "solar times"),
    ],
)
def test_incompatible_label_fails(meda_table, old, new, expected):
    csv, label = meda_table
    label.write_text(label.read_text().replace(old, new))
    with pytest.raises(ValueError, match=expected):
        summarize_meda(csv, label)


def test_environment_summary_reproduced_not_just_hash_checked(tmp_path, meda_table):
    csv, label = meda_table
    product = summarize_meda(csv, label)
    product["source_ids"] = ["TEST_CSV", "TEST_LABEL"]
    bundle = SimpleNamespace(
        sources=[
            SimpleNamespace(source_id="TEST_CSV", snapshot_path=csv.name),
            SimpleNamespace(source_id="TEST_LABEL", snapshot_path=label.name),
        ]
    )
    folder = tmp_path / "data/processed"
    folder.mkdir(parents=True)
    context = dict(subject_id="test", products=[product], processing_hash=content_hash([product]))
    path = folder / "planetary_environment.json"
    path.write_text(json.dumps(context))
    assert load_meda_context(tmp_path, bundle, "test") == context
    assert load_meda_context(tmp_path, bundle, "different_target") is None
    product["summaries"][0]["observed_median"] = 1
    context["processing_hash"] = content_hash([product])
    path.write_text(json.dumps(context))
    with pytest.raises(ValueError, match="reproduce"):
        load_meda_context(tmp_path, bundle, "test")


def temporal_observation(**updates):
    return Observation.model_validate(
        dict(
            observation_id="test",
            subject_id="test",
            domain="environment",
            quantity="surface_pressure_pa",
            value=750,
            unit="Pa",
            statistic="observed_sample_median",
            scope="named_site",
            status="measured",
            source_ids=["test"],
            interpretation="Synthetic temporal observation for compatibility testing only.",
            measurement_start_utc="2021-05-31T22:23:00Z",
            measurement_stop_utc="2021-06-01T22:06:16Z",
            sampling_basis="partial_sol_samples",
            measurement_method="synthetic sensor",
            **updates,
        )
    )


def test_temporal_comparison_requires_explicit_sampling_protocol():
    one = temporal_observation()
    assert compare_observations([one], [one], "surface_pressure_pa", 100)["similarity"] is None
    two = Observation.model_validate(
        {**one.model_dump(), "comparison_protocol": "reviewed_test_protocol_v1"}
    )
    assert compare_observations([two], [two], "surface_pressure_pa", 100)["similarity"] == 1
    other = Observation.model_validate(
        {**two.model_dump(), "sampling_basis": "climatological_mean"}
    )
    assert compare_observations([two], [other], "surface_pressure_pa", 100)["similarity"] is None


@pytest.mark.parametrize(
    "changes",
    [
        dict(measurement_stop_utc=None),
        dict(measurement_stop_utc="2020-01-01T00:00:00Z"),
        dict(measurement_method=None),
        dict(uncertainty_value=3),
        dict(uncertainty_value=-1, uncertainty_unit="Pa"),
    ],
)
def test_temporal_contract_rejects_invalid_support(changes):
    with pytest.raises(ValidationError):
        Observation.model_validate({**temporal_observation().model_dump(), **changes})
