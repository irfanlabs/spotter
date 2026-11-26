from __future__ import annotations

from django.http import JsonResponse
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from .exceptions import PlaceNotFound
from .serializers import AnalyzeSerializer, HeatmapSerializer
from .services import analysis, geocoding


class HeavyThrottle(AnonRateThrottle):
    scope = "heavy"


@api_view(["GET"])
def health(request):
    return Response({"status": "ok"})


@api_view(["GET"])
def geocode(request):
    q = (request.query_params.get("q") or "").strip()
    if len(q) < 2:
        return Response({"results": []})
    if len(q) > 200:
        q = q[:200]
    results = geocoding.search(q)
    if not results and request.query_params.get("strict") == "1":
        raise PlaceNotFound(f"We couldn't find “{q}”. Try adding a city or state.")
    return Response({"results": [p.as_dict() for p in results]})


@api_view(["POST"])
@throttle_classes([HeavyThrottle])
def analyze(request):
    s = AnalyzeSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    d = s.validated_data
    result = analysis.analyze(
        analysis.Place(**d["origin"]),
        analysis.Place(**d["destination"]),
        d["departure"],
        d["load_weight_lb"],
        d.get("interval_miles"),
    )
    return Response(result)


@api_view(["POST"])
@throttle_classes([HeavyThrottle])
def heatmap(request):
    s = HeatmapSerializer(data=request.data)
    s.is_valid(raise_exception=True)
    d = s.validated_data
    return Response(analysis.heatmap(d["geometries"], d["departure"], d["load_weight_lb"]))


def api_not_found(request, exception=None):
    return JsonResponse({"error": {"code": "NOT_FOUND", "message": "Unknown API endpoint.", "details": {}}}, status=404)
