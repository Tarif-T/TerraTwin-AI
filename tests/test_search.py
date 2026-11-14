import pytest

from terratwin.search import plan_nasadem


def test_plan_is_bounded_distinct_and_deterministic():
    bbox = [-72, -28, -66, -20]
    plan = plan_nasadem(bbox, 12)
    assert plan == plan_nasadem(bbox, 12)
    assert len({c["tile"] for c in plan["candidates"]}) == 12
    for c in plan["candidates"]:
        tile = c["tile"]
        lat, lon = -int(tile[1:3]) + 0.5, -int(tile[4:]) + 0.5
        assert bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]


@pytest.mark.parametrize(
    "box,budget",
    [
        ([170, -20, -170, 20], 4),
        ([-70, 70, -60, 75], 4),
        ([-70, -30, -60, -20], 0),
        ([-70, -30, -60, -20], 41),
    ],
)
def test_invalid_or_polar_plans_rejected(box, budget):
    with pytest.raises(ValueError):
        plan_nasadem(box, budget)
