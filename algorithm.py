"""
algorithm.py
============

Hauptaufgaben
-------------
1. Aufenthalts-Orte (Stops) aus GPX-Tracks erkennen
2. Weg-Etappen dazwischen analysieren
3. Wahrscheinlichstes Verkehrsmittel pro Etappe bestimmen
4. **Neu:** OpenStreetMap-Netz einmalig offline speichern / laden  
   → keine Overpass-Requests nach dem Erst-Download

Wichtigste Parameter
--------------------
DIST_THRESHOLD_M      … Radius für Stop-Clustering (50 m)  
MIN_STOP_DURATION_SEC … Mindest­aufenthalt (3 min)  
SNAP_RADIUS_M         … max. Abstand GPS ↔ OSM-Weg (10 m)  
FOOT_MAX_KM           … „Zu Fuß“ nur ≤ 4 km Distanz  
Gewichtung Scores     … Speed 40 % + Coverage 40 % + Limit 20 %
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Standard-Bibliotheken
# --------------------------------------------------------------------------- #
import json
import os
import re
import time
from datetime import datetime, timezone
from functools import lru_cache
from math import asin, cos, radians, sin, sqrt
from pathlib import Path
from typing import Dict, List, Tuple

# --------------------------------------------------------------------------- #
# Drittanbieter-Pakete
# --------------------------------------------------------------------------- #
import gpxpy
import geopandas as gpd
import osmnx as ox
import requests
from shapely.geometry import Point

try:
    import rtree  # noqa: F401  (beschleunigt Spatial-Index)
except ImportError:
    pass

# --------------------------------------------------------------------------- #
# Zeitzone
# --------------------------------------------------------------------------- #
try:
    from zoneinfo import ZoneInfo  # Py ≥ 3.9
except ImportError:  # Py 3.8
    from datetime import timezone as ZoneInfo  # type: ignore

    ZoneInfo = lambda tz: timezone.utc  # type: ignore

BERLIN = ZoneInfo("Europe/Berlin")

# --------------------------------------------------------------------------- #
# Parameter
# --------------------------------------------------------------------------- #
DIST_THRESHOLD_M = 50
MIN_STOP_DURATION_SEC = 180
NOMINATIM_SLEEP_SEC = 1
MAX_GAP_SEC_SAME_ADDR = 10 * 60
MERGE_DIST_M = 150
SNAP_RADIUS_M = 10

FOOT_MAX_KM = 4  # > 4 km → Zu Fuß-Score = 0

# --------------------------------------------------------------------------- #
# Geschwindigkeits-Bänder (km/h) – deutsche Bezeichnungen
# --------------------------------------------------------------------------- #
_SPEED_BANDS = {
    "Zu Fuß": (0, 7),
    "Fahrrad": (7, 30),
    "Auto": (24, 300),
    "Bus": (15, 90),
    "Straßenbahn": (15, 90),
    "Zug": (40, 250),
}

# Tags zum Filtern
_TAG_FILTERS = {
    "Zu Fuß": {"highway": ["footway", "pedestrian", "path", "living_street"]},
    "Fahrrad": {"highway": ["cycleway"]},
    "Auto": {
        "highway": [
            "motorway",
            "trunk",
            "primary",
            "secondary",
            "tertiary",
            "unclassified",
            "residential",
            "service",
        ]
    },
    "Bus": {
        "highway": [
            "busway",
            "bus_guideway",
            "primary",
            "secondary",
            "tertiary",
            "unclassified",
            "residential",
        ]
    },
    "Straßenbahn": {"railway": ["tram"]},
    "Zug": {"railway": ["rail", "light_rail", "subway"]},
}

# --------------------------------------------------------------------------- #
# Globale Variablen für Offline-Netz
# --------------------------------------------------------------------------- #
_OSM_GDF: gpd.GeoDataFrame | None = None
_OSM_BBOX: tuple[float, float, float, float] | None = None


# --------------------------------------------------------------------------- #
# Hilfsfunktionen Scores
# --------------------------------------------------------------------------- #
def _speed_score(v_kmh: float, mode: str) -> float:
    lo, hi = _SPEED_BANDS[mode]
    if v_kmh <= lo:
        return 0.0
    if v_kmh >= hi:
        return 1.0
    return (v_kmh - lo) / (hi - lo)


def _parse_maxspeed(val) -> float | None:
    """String/Int → km/h oder None."""
    if val in (None, ""):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    m = re.search(r"(\d+)", str(val))
    if not m:
        return None
    speed = float(m.group(1))
    if "mph" in str(val).lower():
        speed *= 1.60934
    return speed


def _limit_score(
    mode: str,
    speed_kmh: float,
    seg_pts: list[tuple[float, float]],
    gdf: gpd.GeoDataFrame,
) -> float:
    """Auto/Bus: vergleiche mit OSM-maxspeed → Score ∈ {1, 0.5, 0}."""
    if mode not in ("Auto", "Bus") or speed_kmh == 0 or gdf.empty:
        return 1.0
    limits: list[float] = []
    idx = gdf.sindex
    buf_deg = SNAP_RADIUS_M / 111_320
    for lat, lon in seg_pts:
        pt = Point(lon, lat)
        cand = list(idx.intersection(pt.buffer(buf_deg).bounds))
        for _, row in gdf.iloc[cand].iterrows():
            ms = _parse_maxspeed(row.get("maxspeed"))
            if ms:
                limits.append(ms)
                break
    if not limits:
        return 1.0
    avg = sum(limits) / len(limits)
    if speed_kmh <= avg:
        return 1.0
    if speed_kmh <= 1.5 * avg:
        return 0.5
    return 0.0


# --------------------------------------------------------------------------- #
# Offline-Netz Verwaltung
# --------------------------------------------------------------------------- #
def ensure_osm_network(
    path: str,
    bbox: tuple[float, float, float, float],
    ask_overwrite_callback,
) -> bool:
    """
    • Existiert die Datei und deckt die BBox (+ 50 km) ab → nichts tun.  
    • Sonst: Nutzer ggf. fragen → Netz herunterladen, speichern, Meta-JSON schreiben.
    """
    meta = Path(path).with_suffix(".json")
    need_dl = True
    if Path(path).exists() and meta.exists():
        try:
            saved = tuple(json.loads(meta.read_text())["bbox"])
            n, s, e, w = bbox
            N, S, E, W = saved
            if n <= N and s >= S and e <= E and w >= W:
                need_dl = False
            elif not ask_overwrite_callback():
                return False
        except Exception:
            pass

    if need_dl:
        tags = {"highway": True, "railway": True, "maxspeed": True}
        ox.settings.use_cache = False
        gdf = ox.geometries_from_bbox(*bbox, tags)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        gdf.to_file(path, layer="osm", driver="GPKG")
        meta.write_text(json.dumps({"bbox": bbox, "timestamp": datetime.utcnow().isoformat()}))
    return True


def set_osm_path(path: str) -> None:
    """Nach ensure_osm_network() einmalig aufrufen → globales GDF laden."""
    global _OSM_GDF, _OSM_BBOX
    _OSM_GDF = gpd.read_file(path, layer="osm")
    with open(Path(path).with_suffix(".json")) as f:
        _OSM_BBOX = tuple(json.load(f)["bbox"])


def _load_osm_cached(bbox: tuple[float, float, float, float], tags: dict):
    """Gibt OSM-Ausschnitt zurück – offline, falls globales GDF gesetzt."""
    if _OSM_GDF is None:
        return ox.geometries_from_bbox(*bbox, tags)
    north, south, east, west = bbox
    return _OSM_GDF.cx[west:east, south:north]


# --------------------------------------------------------------------------- #
# Verkehrsmittel-Klassifizierung
# --------------------------------------------------------------------------- #
def classify_transport(
    seg_pts: list[tuple[float, float]],
    speed_kmh: float,
    dist_km: float,
) -> dict:
    if not seg_pts:
        return {"best": None}

    lats, lons = zip(*seg_pts)
    # +100-m-Puffer
    north, south = max(lats) + 0.001, min(lats) - 0.001
    east, west = max(lons) + 0.001, min(lons) - 0.001
    bbox = (north, south, east, west)

    scores: dict[str, float] = {}
    for mode, tag_filter in _TAG_FILTERS.items():
        # 1 Geschwindigkeit
        s_speed = _speed_score(speed_kmh, mode)

        # 2 Coverage
        try:
            gdf = _load_osm_cached(bbox, tag_filter)
            if gdf.empty:
                s_cov = 0.0
            else:
                idx = gdf.sindex
                match = 0
                buf_deg = SNAP_RADIUS_M / 111_320
                for lat, lon in seg_pts[:: max(1, len(seg_pts) // 100)]:  # ausdünnen
                    pt = Point(lon, lat)
                    cand = list(idx.intersection(pt.buffer(buf_deg).bounds))
                    if cand:
                        nearest = gdf.iloc[cand].distance(pt).min() * 111_320
                        if nearest <= SNAP_RADIUS_M:
                            match += 1
                s_cov = match / len(seg_pts)
        except Exception:
            s_cov = 0.0

        # 3 Limit-Score (Auto/Bus)
        s_lim = (
            _limit_score(mode, speed_kmh, seg_pts, gdf) if mode in ("Auto", "Bus") else 1.0
        )

        # 4 Gesamt
        if mode in ("Auto", "Bus"):
            total = 0.4 * s_speed + 0.4 * s_cov + 0.2 * s_lim
        else:
            total = 0.4 * s_speed + 0.6 * s_cov

        # 5 “Zu Fuß” nur ≤ 4 km
        if mode == "Zu Fuß" and dist_km > FOOT_MAX_KM:
            total = 0.0

        scores[mode] = total

    # Normieren
    tot = sum(scores.values()) or 1
    for k in scores:
        scores[k] /= tot
    scores["best"] = max(scores, key=scores.get)
    return scores


# --------------------------------------------------------------------------- #
# Geodistanz
# --------------------------------------------------------------------------- #
def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6_371_000 * 2 * asin(sqrt(a))


# --------------------------------------------------------------------------- #
# Reverse-Geocoding (Nominatim + Cache)
# --------------------------------------------------------------------------- #
_NOMINATIM = "https://nominatim.openstreetmap.org/reverse"
_HDRS = {"User-Agent": "WegeRadar/1.0 (kontakt@example.com)"}
_GEOCACHE: Dict[Tuple[float, float], Dict[str, str]] = {}


def _extract_name(js: dict) -> str:
    if js.get("name"):
        return js["name"]
    addr = js.get("address", {})
    for k in ("amenity", "attraction", "leisure", "shop", "tourism"):
        if addr.get(k):
            return addr[k]
    return ""


def reverse_geocode(lat: float, lon: float) -> Dict[str, str]:
    key = (round(lat, 5), round(lon, 5))  # ≈ 1 m
    if key in _GEOCACHE:
        return _GEOCACHE[key]

    result = {k: "" for k in ("name", "road", "house_number", "postcode", "city")}
    try:
        r = requests.get(
            _NOMINATIM,
            params={
                "format": "jsonv2",
                "lat": lat,
                "lon": lon,
                "zoom": 18,
                "addressdetails": 1,
            },
            headers=_HDRS,
            timeout=5,
        )
        if r.status_code == 200:
            js = r.json()
            addr = js.get("address", {})
            result.update(
                {
                    "name": _extract_name(js),
                    "road": addr.get("road")
                    or addr.get("pedestrian")
                    or addr.get("footway")
                    or "",
                    "house_number": addr.get("house_number", ""),
                    "postcode": addr.get("postcode", ""),
                    "city": addr.get("city")
                    or addr.get("town")
                    or addr.get("village")
                    or addr.get("hamlet")
                    or "",
                }
            )
    except Exception:
        pass

    _GEOCACHE[key] = result
    time.sleep(NOMINATIM_SLEEP_SEC)
    return result


def _same_address(a: dict, b: dict) -> bool:
    return all(a.get(f, "") == b.get(f, "") for f in ("name", "road", "house_number", "postcode", "city"))


# --------------------------------------------------------------------------- #
# GPX-Dateiauswahl (GUI-Helper)
# --------------------------------------------------------------------------- #
def show_date_dialog(master, gpx_folder: str, last: str, first: str) -> str | None:
    prefix = f"{last}_{first}_"
    files = [
        f for f in os.listdir(gpx_folder) if f.startswith(prefix) and f.lower().endswith(".gpx")
    ]
    if not files:
        from tkinter import messagebox

        messagebox.showinfo("WegeRadar", f"Keine GPX-Dateien für {last}, {first} gefunden.", parent=master)
        return None

    date_map = {os.path.splitext(f)[0].split("_")[2]: f for f in files}
    if len(date_map) == 1:
        return next(iter(date_map))

    import tkinter as tk

    dlg = tk.Toplevel(master)
    dlg.title("GPX-Datei auswählen")
    dlg.transient(master)
    dlg.resizable(False, False)
    dlg.grab_set()

    tk.Label(dlg, text="Bitte Datum wählen:", font=("Arial", 12)).pack(pady=10)
    sel: dict[str | None] = {"d": None}

    def choose(d: str):
        sel["d"] = d
        dlg.destroy()

    for d in sorted(date_map):
        tk.Button(dlg, text=d, width=22, command=lambda d=d: choose(d)).pack(pady=2)

    dlg.update_idletasks()
    w, h = dlg.winfo_width() + 40, dlg.winfo_height() + 20
    x = (dlg.winfo_screenwidth() - w) // 2
    y = (dlg.winfo_screenheight() - h) // 2
    dlg.geometry(f"{w}x{h}+{x}+{y}")
    dlg.wait_window()
    return sel["d"]


# --------------------------------------------------------------------------- #
# Hauptfunktion – Analyse & Aufbereitung
# --------------------------------------------------------------------------- #
def analyze_gpx(
    gpx_folder: str,
    last: str,
    first: str,
    date: str,
    dist_m: int = DIST_THRESHOLD_M,
    min_stop_sec: int = MIN_STOP_DURATION_SEC,
) -> List[dict]:
    path = os.path.join(gpx_folder, f"{last}_{first}_{date}.gpx")
    if not os.path.exists(path):
        return []

    with open(path, encoding="utf-8") as f:
        gpx = gpxpy.parse(f)

    pts = [
        (pt.time.replace(tzinfo=timezone.utc), pt.latitude, pt.longitude)
        for trk in gpx.tracks
        for seg in trk.segments
        for pt in seg.points
        if pt.time
    ]
    if not pts:
        return []

    pts.sort(key=lambda x: x[0])

    # ---- 1 Stop-Cluster -------------------------------------------- #
    clusters: list[tuple[float, float, datetime, datetime]] = []
    i, n = 0, len(pts)
    while i < n:
        j = i + 1
        while j < n and haversine(pts[i][1], pts[i][2], pts[j][1], pts[j][2]) <= dist_m:
            j += 1
        duration = (pts[j - 1][0] - pts[i][0]).total_seconds()
        if duration >= min_stop_sec:
            lat = sum(p[1] for p in pts[i:j]) / (j - i)
            lon = sum(p[2] for p in pts[i:j]) / (j - i)
            clusters.append((lat, lon, pts[i][0], pts[j - 1][0]))
            i = j
        else:
            i += 1

    coords = [
        (pts[0][1], pts[0][2], pts[0][0], pts[0][0]),
        *clusters,
        (pts[-1][1], pts[-1][2], pts[-1][0], pts[-1][0]),
    ]

    # ---- 2 Stops zusammenlegen, wenn Minute identisch --------------- #
    merged: list[tuple[float, float, datetime, datetime]] = []
    for lat, lon, s_dt, e_dt in coords:
        if merged and merged[-1][3].strftime("%Y-%m-%d %H:%M") == s_dt.strftime("%Y-%m-%d %H:%M"):
            merged[-1] = (merged[-1][0], merged[-1][1], merged[-1][2], e_dt)
        else:
            merged.append((lat, lon, s_dt, e_dt))

    # ---- 3 Reverse-Geocoding --------------------------------------- #
    enriched: list[dict] = []
    for lat, lon, s_dt, e_dt in merged:
        addr = reverse_geocode(lat, lon)
        addr.update(
            {
                "lat": lat,
                "lon": lon,
                "start_dt": s_dt.astimezone(BERLIN),
                "end_dt": e_dt.astimezone(BERLIN),
            }
        )
        enriched.append(addr)

    # ---- 4 Adress-/Distanz-Merging --------------------------------- #
    final: list[dict] = []
    for item in enriched:
        if not final:
            final.append(item)
            continue
        prev = final[-1]
        gap_sec = (item["start_dt"] - prev["end_dt"]).total_seconds()
        same_addr = _same_address(prev, item)
        close = haversine(prev["lat"], prev["lon"], item["lat"], item["lon"]) <= MERGE_DIST_M
        if gap_sec <= MAX_GAP_SEC_SAME_ADDR and (same_addr or close):
            prev["end_dt"] = item["end_dt"]
        else:
            final.append(item)

    # ---- 5 Etappen analysieren ------------------------------------- #
    for idx in range(len(final) - 1):
        end_prev = final[idx]["end_dt"].astimezone(timezone.utc)
        start_next = final[idx + 1]["start_dt"].astimezone(timezone.utc)

        dist_m_real = 0.0
        started = False
        for i in range(len(pts) - 1):
            t0, lat0, lon0 = pts[i]
            t1, lat1, lon1 = pts[i + 1]
            if t1 < end_prev:
                continue
            if not started and t0 >= end_prev:
                started = True
            if started:
                dist_m_real += haversine(lat0, lon0, lat1, lon1)
            if started and t1 >= start_next:
                break

        dist_km = round(dist_m_real / 1000.0, 2)
        time_h = (start_next - end_prev).total_seconds() / 3600
        speed_kmh = round(dist_km / time_h, 2) if time_h > 0 else 0.0

        final[idx]["next_dist_km_real"] = dist_km
        final[idx]["next_speed_kmh_real"] = speed_kmh

        seg_pts = [(lat, lon) for t, lat, lon in pts if end_prev <= t <= start_next]
        final[idx]["next_mode_rank"] = classify_transport(seg_pts, speed_kmh, dist_km)

    return final