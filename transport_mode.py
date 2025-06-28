"""
transport_mode.py
=================

Ermittelt das wahrscheinlichste Verkehrsmittel für eine Weg-Etappe
auf Basis von

    • Map-Matching gegen das OSM-Netz (OSRM /match)
    • OSM‐Way-Tags über Overpass
    • gemessener Ø-Geschwindigkeit

Erkennt: Zu Fuß, Fahrrad, Auto, Bus, Straßenbahn, Zug (inkl. U-Bahn).
"""

from __future__ import annotations

import requests, math, time
from collections import Counter
from typing import List, Tuple

OSRM_URL     = "https://router.project-osrm.org"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# --------------------------------------------------------------------------- #
# Hilfsfunktionen
# --------------------------------------------------------------------------- #
def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi  = phi2 - phi1
    dlamb = math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlamb/2)**2
    return R * 2 * math.asin(math.sqrt(a))

def map_match(points: List[Tuple[float, float]], timestamps: List[int]) -> dict:
    """
    Ruft OSRM /match auf und gibt die JSON-Antwort zurück.
    points : [(lat, lon), ...]  – in originaler Reihenfolge
    timestamps : [unix_sec, ...] – dieselbe Länge wie points
    """
    coords = ";".join(f"{lon},{lat}" for lat, lon in points)
    ts     = ";".join(str(t) for t in timestamps)
    url = f"{OSRM_URL}/match/v1/driving/{coords}"
    params = {
        "annotations": "true",
        "timestamps": ts,
        "radiuses": ";".join(["30"] * len(points)),   # 30-m Toleranz
        "overview": "false",
    }
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()
    return r.json()

def fetch_way_tags(way_ids: List[int]) -> dict[int, dict]:
    """
    Holt für eine Liste OSM-Way-IDs die Tags per Overpass.
    Rückgabe: {way_id: {tag: value, ...}, ...}
    """
    ids = ",".join(str(w) for w in way_ids)
    query = f"[out:json][timeout:25]; way(id:{ids}); out tags;"
    r = requests.get(OVERPASS_URL, params={"data": query}, timeout=30)
    r.raise_for_status()
    data = r.json()
    return {e["id"]: e.get("tags", {}) for e in data["elements"]}

def _share(cnt: Counter, keys: List[str]) -> float:
    total = sum(cnt.values()) or 1
    return sum(cnt[k] for k in keys) / total * 100

def _count_bus_stops(points: List[Tuple[float, float]]) -> int:
    # Grobe Heuristik: Overpass-Query für Haltestellen entlang des Tracks.
    # BBOX um alle Punkte (±50 m) – genügt hier als Näherung.
    lats = [lat for lat, _ in points]
    lons = [lon for _, lon in points]
    min_lat, max_lat = min(lats) - 0.0005, max(lats) + 0.0005
    min_lon, max_lon = min(lons) - 0.0005, max(lons) + 0.0005
    bbox = f"{min_lat},{min_lon},{max_lat},{max_lon}"
    q = (
        '[out:json][timeout:25];'
        f'node["highway"="bus_stop"]({bbox});'
        'out count;'
    )
    try:
        r = requests.get(OVERPASS_URL, params={"data": q}, timeout=25)
        r.raise_for_status()
        return r.json()["elements"][0]["tags"]["total"]
    except Exception:
        return 0

# --------------------------------------------------------------------------- #
# Hauptfunktion
# --------------------------------------------------------------------------- #
def classify_segment(
    seg_points: List[Tuple[int, float, float]],  # (unix_ts, lat, lon)
    dist_km: float,
    speed_kmh: float,
) -> str:
    """
    Liefert das wahrscheinlichste Verkehrsmittel.
    """
    if len(seg_points) < 2:
        return "Unbekannt"

    # --- Map-Match ---
    pts  = [(lat, lon) for _, lat, lon in seg_points]
    ts   = [ts for ts, _, _ in seg_points]
    try:
        mm = map_match(pts, ts)

        way_ids = set()
        for match in mm.get("matchings", []):
            way_ids.update(match.get("way_ids", []))
        if not way_ids:
            raise RuntimeError("keine Ways")

        tags = fetch_way_tags(list(way_ids))
    except Exception:
        # Fallback auf Geschwindigkeit-Heuristik
        tags = {}
        way_ids = []

    # --- Way-Statistik ---
    cat_meters = Counter()
    for wid in way_ids:
        t = tags.get(wid, {})
        if "railway" in t:
            cat_meters[t["railway"]] += 1
        elif "highway" in t:
            cat_meters[t["highway"]] += 1

    tram_share  = _share(cat_meters, ["tram"])
    rail_share  = _share(cat_meters, ["rail", "subway", "light_rail"])
    foot_share  = _share(cat_meters, ["footway", "pedestrian", "path"])
    cycle_share = _share(cat_meters, ["cycleway", "path"])
    # Road-Share nutzen wir nicht direkt

    # --- Regel-Heuristik ---
    if tram_share > 80:
        return "Straßenbahn"
    if rail_share > 70:
        return "Zug"
    if foot_share > 60 and speed_kmh < 7:
        return "Zu Fuß"
    if cycle_share > 50 and 10 <= speed_kmh <= 30:
        return "Fahrrad"

    if speed_kmh > 25:
        # Bus vs. Auto über Haltestellen-Dichte
        bus_stops = _count_bus_stops(pts)
        return "Bus" if bus_stops >= 3 else "Auto"

    return "Unbekannt"