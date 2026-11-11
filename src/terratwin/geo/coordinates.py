from pyproj import CRS


def validate_body_crs(definition: str, body: str, metric: bool = False) -> CRS:
    crs = CRS.from_user_input(definition)
    radius = crs.ellipsoid.semi_major_metre
    limits = {
        "Earth": (6_300_000, 6_500_000),
        "Mars": (3_300_000, 3_500_000),
        "Moon": (1_700_000, 1_800_000),
    }
    low, high = limits[body]
    if not low <= radius <= high:
        raise ValueError(f"CRS ellipsoid does not describe {body}")
    if metric and (
        not crs.is_projected
        or not crs.axis_info
        or any(axis.unit_name != "metre" for axis in crs.axis_info)
    ):
        raise ValueError("Analysis CRS must be projected with metre axes")
    return crs
