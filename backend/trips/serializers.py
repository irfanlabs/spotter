"""Request validation."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from rest_framework import serializers

from .domain import geo

MAX_LOAD_LB = 80_000  # US federal gross vehicle weight limit
MAX_AHEAD = timedelta(days=14)
MAX_PAST = timedelta(hours=2)


class PlaceSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=300, trim_whitespace=True)
    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)


class ZonedDateTimeField(serializers.DateTimeField):
    """A date-time that must carry a UTC offset. DRF would otherwise assume UTC,
    silently shifting a driver's local departure time by several hours."""

    def enforce_timezone(self, value):
        if value.tzinfo is None:
            raise serializers.ValidationError("Include a timezone offset, such as Z or -06:00.")
        return super().enforce_timezone(value)


def _validate_departure(value: datetime) -> datetime:
    value = value.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    if value < now - MAX_PAST:
        raise serializers.ValidationError("Departure can't be in the past.")
    if value > now + MAX_AHEAD:
        raise serializers.ValidationError("Weather forecasts only cover the next 14 days.")
    return value


class AnalyzeSerializer(serializers.Serializer):
    origin = PlaceSerializer()
    destination = PlaceSerializer()
    departure = ZonedDateTimeField()
    load_weight_lb = serializers.FloatField(min_value=0, max_value=MAX_LOAD_LB)
    interval_miles = serializers.ChoiceField(choices=[10, 25, 50], required=False, allow_null=True)

    def validate_departure(self, value):
        return _validate_departure(value)

    def validate(self, attrs):
        o, d = attrs["origin"], attrs["destination"]
        if geo.haversine_mi((o["lat"], o["lon"]), (d["lat"], d["lon"])) < 0.5:
            raise serializers.ValidationError({"destination": "Destination must be different from the origin."})
        return attrs


class HeatmapSerializer(serializers.Serializer):
    geometries = serializers.ListField(child=serializers.CharField(max_length=200_000), min_length=1, max_length=3)
    departure = ZonedDateTimeField()
    load_weight_lb = serializers.FloatField(min_value=0, max_value=MAX_LOAD_LB)

    def validate_departure(self, value):
        return _validate_departure(value)

    def validate_geometries(self, value):
        paths = []
        for g in value:
            try:
                path = geo.decode_polyline(g, 6)
            except ValueError as exc:
                raise serializers.ValidationError("Invalid route geometry.") from exc
            if len(path) < 2:
                raise serializers.ValidationError("Route geometry is too short.")
            paths.append(path)
        return paths
