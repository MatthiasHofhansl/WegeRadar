# algorithm.py
from __future__ import annotations
import os
import time
from datetime import datetime, timezone
from functools import lru_cache
from math import radians, cos, sin, asin, sqrt
from typing import Dict, List, Tuple

import gpxpy
import requests

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from datetime import timezone as ZoneInfo  # type: ignore
    ZoneInfo = lambda tz: timezone.utc         # type: ignore

BERLIN = ZoneInfo("Europe/Berlin")

DIST_THRESHOLD_M = 50
MIN_STOP_DURATION_SEC = 180
NOMINATIM_SLEEP_SEC = 1
MAX_GAP_SEC_SAME_ADDR = 600
MERGE_DIST_M = 150

# ---- Verkehrsmittel-Heuristik ---------------------------------------------

_SPEED_BANDS = {
    "Zu Fuß":       (0,  7),
    "Fahrrad":      (7,  30),
    "Auto":         (24, 300),
    "Bus":          (15, 90),
    "Straßenbahn":  (15, 90),
    "Zug":          (40, 250),
}
_MARGIN_KMH = 1.0

_TAG_FILTERS = {
    "Zu Fuß":      {"highway": ["footway", "pedestrian", "path", "living_street"]},
    "Fahrrad":     {"highway": ["cycleway"]},
    "Auto":        {"highway": ["motorway", "trunk", "primary", "secondary",
                                "tertiary", "unclassified", "residential", "service"]},
    "Bus":         {"highway": ["busway", "bus_guideway", "primary", "secondary",
                                "tertiary", "unclassified", "residential"]},
    "Straßenbahn": {"railway": ["tram"]},
    "Zug":         {"railway": ["rail", "light_rail", "subway"]},
}

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
_HDRS = {"User-Agent": "WegeRadar/1.0 (kontakt@example.com)"}


def _speed_score(speed_kmh: float, mode: str) -> float:
    lo, hi = _SPEED_BANDS[mode]
    if speed_kmh <= lo - _MARGIN_KMH or speed_kmh >= hi + _MARGIN_KMH:
        return 0.0
    if lo <= speed_kmh <= hi:
        return 1.0
    if lo - _MARGIN_KMH < speed_kmh < lo:
        return (speed_kmh - (lo - _MARGIN_KMH)) / _MARGIN_KMH
    if hi < speed_kmh < hi + _MARGIN_KMH:
        return ((hi + _MARGIN_KMH) - speed_kmh) / _MARGIN_KMH
    return 0.0


def _foot_distance_factor(dist_km: float) -> float:
    if dist_km <= 1.0:
        return 1.0
    if dist_km >= 4.0:
        return 0.0
    return (4.0 - dist_km) / 3.0


def classify_transport(
    seg_pts: List[Tuple[float, float]],
    speed_kmh: float,
    dist_km: float,
) -> dict:
    if not seg_pts:
        return {"best": None}

    scores: Dict[str, float] = {}
    for mode in _SPEED_BANDS:
        s_score = _speed_score(speed_kmh, mode)
        score = s_score
        if mode == "Zu Fuß":
            score *= _foot_distance_factor(dist_km)
        scores[mode] = score

    tot = sum(scores.values()) or 1.0
    for k in scores:
        scores[k] /= tot
    scores["best"] = max(scores, key=lambda m: scores[m])
    return scores


def get_osm_tags(lat: float, lon: float, radius: int = 10) -> Dict[str, str]:
    """
    Führt eine Overpass-API-Abfrage um den gegebenen Punkt aus und sammelt OSM-Tags.
    """
    query = f"""
[out:json];
(
  way(around:{radius},{lat},{lon});
  node(around:{radius},{lat},{lon});
);
out tags;
"""
    time.sleep(1)  # Zur Schonung des Overpass-Servers
    response = requests.post(OVERPASS_URL, data={"data": query}, headers=_HDRS)
    tags: Dict[str, str] = {}
    if response.ok:
        data = response.json()
        for elem in data.get("elements", []):
            for k, v in elem.get("tags", {}).items():
                if k not in tags:
                    tags[k] = v
    return tags


def classify_main_mode(
    pts: List[Tuple[datetime, float, float]],
    start_dt: datetime,
    end_dt: datetime,
) -> dict:
    """
    Bestimme das dominierende Verkehrsmittel durch Aggregation
    der Distanzen jedes lokal wahrscheinlichsten Modus,
    gefiltert nach OSM-Tags, über alle Punkte zwischen
    start_dt und end_dt. Wenn eine öffentliche
    Verkehrsart (Bus, Straßenbahn, Zug) über OSM erkannt wird,
    wird diese gegenüber anderen Modi priorisiert.
    """
    dist_sum: Dict[str, float] = {mode: 0.0 for mode in _SPEED_BANDS}
    total_dist = 0.0
    started = False

    for i in range(len(pts) - 1):
        t0, lat0, lon0 = pts[i]
        t1, lat1, lon1 = pts[i + 1]
        if not started:
            if t0 >= start_dt and t1 >= start_dt:
                started = True
            else:
                continue
        if t0 > end_dt:
            break

        # Distanz und Geschwindigkeit
        d = haversine(lat0, lon0, lat1, lon1)
        dt_h = (t1 - t0).total_seconds() / 3600
        v = (d / 1000.0) / dt_h if dt_h > 0 else 0.0

        # OSM-Tags am Segment-Mittelpunkt
        mid_lat = (lat0 + lat1) / 2
        mid_lon = (lon0 + lon1) / 2
        osm_tags = get_osm_tags(mid_lat, mid_lon)

        # Lokale Scores mit Tag-Filter
        local_scores: Dict[str, float] = {}
        for m in _SPEED_BANDS:
            score = _speed_score(v, m)
            if m == "Zu Fuß":
                score *= _foot_distance_factor(d / 1000.0)
            filters = _TAG_FILTERS.get(m)
            if filters:
                match = False
                for key, vals in filters.items():
                    if key in osm_tags and osm_tags[key] in vals:
                        match = True
                        break
                if not match:
                    score = 0.0
            local_scores[m] = score

        best_loc = max(local_scores, key=lambda m: local_scores[m])
        dist_sum[best_loc] += d
        total_dist += d

    if total_dist == 0:
        return {"best": None}

    # Wahrscheinlichkeiten berechnen
    probs = {m: dist_sum[m] / total_dist for m in dist_sum}

    # Priorisierung öffentlicher Verkehrsmittel
    pt_modes = ["Bus", "Straßenbahn", "Zug"]
    pt_dist = {m: dist_sum[m] for m in pt_modes}
    if any(pt_dist[m] > 0 for m in pt_modes):
        # Wähle das PT mit größter Distanz
        best_pt = max(pt_modes, key=lambda m: pt_dist[m])
        probs["best"] = best_pt
    else:
        probs["best"] = max(probs, key=lambda m: probs[m])

    return probs

# Rest der Datei unverändert: reverse_geocode, _extract_name, _same_address,
# analyse_gpx, app.py, benutzeroberfläche.py bleiben wie zuvor.
