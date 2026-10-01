"""Geospatial proximity ranking for retailer discovery (FR-R-02, doc 6.2).

The doc requires geographic ranking to be resolved *at the database query level*
through the Haversine formula as a custom ORM annotation, rather than by
loading rows and sorting in Python.

The expression is assembled from portable SQL scalar functions so the exact same
SQL runs on PostgreSQL (production) and SQLite (development).  Only the
upper-clamp function differs between the two engines, because PostgreSQL exposes
``LEAST`` while SQLite exposes a two-argument scalar ``MIN``.
"""
import math

from django.db import connection
from django.db.models import FloatField, Func, Value
from django.db.models.expressions import ExpressionWrapper

EARTH_RADIUS_KM = 6371.0088

_LAT_FIELDS = ("owner__latitude", "owner__longitude")


def _fn(name, *args, output_field=None):
    return Func(
        *args, function=name, output_field=output_field or FloatField()
    )


def _radians(x):
    return _fn("RADIANS", x)


def _sin(x):
    return _fn("SIN", x)


def _cos(x):
    return _fn("COS", x)


def _power(x, y):
    return _fn("POWER", x, y)


def _sqrt(x):
    return _fn("SQRT", x)


def _asin(x):
    return _fn("ASIN", x)


def _clamp_unit(x):
    """Force ``x`` into [0, 1] so ASIN can never fail on rounding drift."""
    fn = "LEAST" if connection.vendor == "postgresql" else "MIN"
    return Func(
        x,
        function=fn,
        template="%(function)s(%(expressions)s, 1.0)",
        output_field=FloatField(),
    )


def haversine_expression(lat1, lon1, lat2, lon2):
    """Build the great-circle distance (km) SQL expression for two coordinate pairs.

    ``lat1``/``lon1`` and ``lat2``/``lon2`` may each be a field reference, a
    :class:`~django.db.models.Value`, or a plain number.
    """
    lat_delta = ExpressionWrapper(
        (_radians(lat1) - _radians(lat2)) / 2.0, output_field=FloatField()
    )
    lon_delta = ExpressionWrapper(
        (_radians(lon1) - _radians(lon2)) / 2.0, output_field=FloatField()
    )

    inner = _power(_sin(lat_delta), 2) + (
        _cos(_radians(lat2)) * _cos(_radians(lat1)) * _power(_sin(lon_delta), 2)
    )

    return _asin(_sqrt(_clamp_unit(inner))) * (2 * EARTH_RADIUS_KM)


def annotate_distance_km(queryset, user, lat_field=_LAT_FIELDS[0],
                         lon_field=_LAT_FIELDS[1]):
    """Annotate ``distance_km`` relative to the viewer's registered location.

    Returns ``(queryset, has_origin)``.  When the viewer has no usable
    coordinates the queryset is returned untouched and ``has_origin`` is False,
    letting the caller fall back to recency ordering (doc 1.4.2 — the system
    depends on browser/location data, not a mapping API).
    """
    if user is None or user.latitude is None or user.longitude is None:
        return queryset, False

    queryset = queryset.annotate(
        distance_km=haversine_expression(
            Value(float(user.latitude)),
            Value(float(user.longitude)),
            lat_field,
            lon_field,
        )
    )
    return queryset, True


def haversine_km(lat1, lon1, lat2, lon2):
    """Pure-Python great-circle distance in km (used by tests and seeding)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d_phi = p2 - p1
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))
