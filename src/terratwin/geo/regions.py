"""Physical study footprints with explicit body-specific coordinate systems."""

import numpy as np
from pyproj import Transformer
from shapely import transform
from shapely.geometry import Polygon, box, shape

from terratwin.geo.coordinates import validate_body_crs


def geographic_ring(crs: str, body: str, bounds: tuple) -> list[list[float]]:
    projected = validate_body_crs(crs, body, metric=True)
    converter = Transformer.from_crs(projected, projected.geodetic_crs, always_xy=True)
    left, bottom, right, top = bounds
    points = []
    corners = [(left, bottom), (right, bottom), (right, top), (left, top), (left, bottom)]
    for start, end in zip(corners, corners[1:]):
        for fraction in np.linspace(0, 1, 33, endpoint=False):
            x = start[0] + fraction * (end[0] - start[0])
            y = start[1] + fraction * (end[1] - start[1])
            points.append(list(converter.transform(x, y)))
    return points + [points[0]]


def validate_earth_footprint(geometry: dict, crs: str, bounds: tuple):
    projected = validate_body_crs(crs, "Earth", metric=True)
    converter = Transformer.from_crs("EPSG:4326", projected, always_xy=True)

    def project(coordinates):
        x, y = converter.transform(coordinates[:, 0], coordinates[:, 1])
        return np.column_stack([x, y])

    polygon = transform(shape(geometry), project)
    if not isinstance(polygon, Polygon) or not polygon.is_valid:
        raise ValueError("Earth study footprint must be one valid polygon")
    expected = box(*bounds)
    if polygon.symmetric_difference(expected).area > max(1.0, expected.area * 1e-8):
        raise ValueError("Catalog polygon does not match the measured analysis footprint")
