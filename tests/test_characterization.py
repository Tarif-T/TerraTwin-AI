"""Synthetic context verifies missingness and prevents unsupported resource inference."""

import copy

import pytest
from conftest import changed

from terratwin.characterization import characterize_filter, summarize_climate, summarize_geology
from terratwin.config import ROOT, read_yaml
from terratwin.mission import mission_scoring


def climate():
    return dict(
        daily_units={"temperature_2m_mean": "°C", "precipitation_sum": "mm"},
        daily=dict(
            time=["2020-02-28", "2020-02-29", "2020-03-01"],
            temperature_2m_mean=[-2, 0, 2],
            precipitation_sum=[1, 2, 3],
        ),
    )


def test_climate_leap_day_units_and_complete_totals():
    result = summarize_climate(climate(), "2020-02-28", "2020-03-01")
    assert result["mean_temperature_c"] == 0
    assert result["freezing_mean_day_fraction"] == pytest.approx(1 / 3)
    assert result["mean_annual_precipitation_mm"] is None
    assert "do not measure" in result["resource_inference"]


def test_missing_climate_never_becomes_zero_or_inflated_total():
    payload = climate()
    payload["daily"]["temperature_2m_mean"][0] = None
    payload["daily"]["precipitation_sum"][0] = None
    result = summarize_climate(payload, "2020-02-28", "2020-03-01")
    assert result["mean_temperature_c"] is None
    assert result["mean_annual_precipitation_mm"] is None
    assert result["complete_precipitation_years"] == 0


def test_complete_leap_year_precipitation_total():
    from datetime import date, timedelta

    payload = climate()
    payload["daily"] = dict(
        time=[(date(2020, 1, 1) + timedelta(days=n)).isoformat() for n in range(366)],
        temperature_2m_mean=[0] * 366,
        precipitation_sum=[2] * 366,
    )
    result = summarize_climate(payload, "2020-01-01", "2020-12-31")
    assert result["mean_annual_precipitation_mm"] == 732
    assert result["complete_precipitation_years"] == 1


@pytest.mark.parametrize("change", ["units", "duplicate", "negative", "fill"])
def test_bad_climate_inputs_rejected(change):
    payload = climate()
    if change == "units":
        payload["daily_units"]["temperature_2m_mean"] = "K"
    elif change == "duplicate":
        payload["daily"]["time"][1] = payload["daily"]["time"][0]
    elif change == "negative":
        payload["daily"]["precipitation_sum"][0] = -1
    else:
        payload["daily"]["temperature_2m_mean"][0] = -999
    with pytest.raises(ValueError):
        summarize_climate(payload, "2020-02-28", "2020-03-01")


def test_geology_keeps_conflicting_finest_sources_and_does_not_promote_broad_map():
    rows = [
        dict(map_id=1, source_id=10, name="Alluvium", lith="unconsolidated", scale="large"),
        dict(map_id=2, source_id=11, name="Basalt", lith="basalt", scale="large"),
        dict(map_id=3, source_id=12, name="Granite", lith="granite", scale="tiny"),
    ]
    payload = {"success": {"data": rows, "refs": {"10": "source A", "11": "source B"}}}
    result = summarize_geology(payload)
    assert len(result["units"]) == 2
    assert set(result["lithology_classes"]) == {"unconsolidated", "volcanic"}
    assert "plutonic" not in result["lithology_classes"]
    assert "not whole-ROI" in result["spatial_scope"]
    assert summarize_geology({"success": {"data": []}})["status"] == "no_mapped_unit"


def test_context_filters_require_real_evidence_and_correct_location(earth_sites):
    site = earth_sites[0]
    assert characterize_filter(site, None)
    assert not characterize_filter(site, None, max_precipitation=250)
    context = dict(
        latitude=site.centroid_lat,
        longitude=site.centroid_lon,
        climate={"mean_annual_precipitation_mm": 10, "mean_temperature_c": -5},
        geology={"lithology_classes": ["volcanic"]},
    )
    assert characterize_filter(
        site, context, max_precipitation=250, max_temperature=0, geology_class="volcanic"
    )
    assert not characterize_filter(site, context, geology_class="sedimentary")
    with pytest.raises(ValueError, match="location differs"):
        characterize_filter(changed(site, centroid_lat=site.centroid_lat + 1), context)


def test_mission_presets_are_versioned_and_change_terrain_priorities(scoring_config):
    presets = read_yaml(ROOT / "config/missions.yaml")["missions"]
    baseline = mission_scoring(scoring_config, presets[0])
    rover = mission_scoring(scoring_config, presets[1])
    assert baseline.version == scoring_config.version
    assert rover.version != baseline.version
    assert (
        rover.normalized_weights["steep_fraction_15deg"]
        > baseline.normalized_weights["steep_fraction_15deg"]
    )
    assert sum(rover.normalized_weights.values()) == pytest.approx(1)


def test_context_changes_export_hash_without_changing_terrain_score(
    reference, earth_sites, scoring_config
):
    import csv
    import io

    from terratwin.export.csv_export import export_analysis
    from terratwin.scoring.engine import rank_candidates

    results = rank_candidates(reference, earth_sites, scoring_config)
    context = {earth_sites[0].site_id: {"climate": {"mean_temperature_c": 5}}}
    first = list(
        csv.DictReader(
            io.StringIO(
                export_analysis(
                    reference, earth_sites, results, scoring_config, characterization=context
                )
            )
        )
    )[0]
    changed_context = copy.deepcopy(context)
    changed_context[earth_sites[0].site_id]["climate"]["mean_temperature_c"] = 6
    second = list(
        csv.DictReader(
            io.StringIO(
                export_analysis(
                    reference,
                    earth_sites,
                    results,
                    scoring_config,
                    characterization=changed_context,
                )
            )
        )
    )[0]
    assert first["input_data_hash"] != second["input_data_hash"]
    assert first["similarity_index"] == second["similarity_index"]
    assert first["resources_status"] == "not_assessed"
