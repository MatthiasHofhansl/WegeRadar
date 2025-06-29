"""
algorithm.py
============

Erkennt Aufenthalts-Orte in einer GPX-Spur, verschmilzt benachbarte Stops,
reichert sie mit Adressdaten an und bestimmt für jede Weg-Etappe ein
Ranking des wahrscheinlich genutzten Verkehrsmittels.

Für jeden Aufenthalt speichert das Skript:
    • Koordinaten lat / lon
    • Start- und End-Zeit (Europe/Berlin)
    • Name, Straße, Haus-Nr., PLZ, Stadt (per Nominatim)

Für jede Weg-Etappe (Stop i → Stop i+1):
    • next_dist_km_real       Distanz entlang der GPX-Punkte
    • next_speed_kmh_real     Durchschnittsgeschwindigkeit
    • next_mode_rank          Score-Dict inkl. 'best'
"""

from __future__ import annotations

# --------------------------------------------------------------------------- #
# Standard-Bibliotheken
# --------------------------------------------------------------------------- #
import os
import time
from datetime import datetime, timezone
from functools import lru_cache
from math import radians, cos, sin, asin, sqrt
from typing import Dict, List, Tuple

# --------------------------------------------------------------------------- #
# Drittanbieter-Pakete
# --------------------------------------------------------------------------- #
import gpxpy
import requests
import osmnx as ox                       # Overpass-/OSM-Zugriff
from shapely.geometry import Point
try:
    import rtree                         # optional, beschleunigt Spatial-Index
except ImportError:
    pass

# --------------------------------------------------------------------------- #
# Zeitzone
# --------------------------------------------------------------------------- #
try:
    from zoneinfo import ZoneInfo           # Py ≥ 3.9
except ImportError:                         # Py 3.8
    from datetime import timezone as ZoneInfo  # type: ignore
    ZoneInfo = lambda tz: timezone.utc         # type: ignore

BERLIN = ZoneInfo("Europe/Berlin")

# --------------------------------------------------------------------------- #
# Parameter
# --------------------------------------------------------------------------- #
DIST_THRESHOLD_M       = 50             # Radius fürs erste Stop-Clustering
MIN_STOP_DURATION_SEC  = 180            # Mindest-Aufenthaltsdauer (3 min)
NOMINATIM_SLEEP_SEC    = 1              # Wartezeit pro Geocode-Request
MAX_GAP_SEC_SAME_ADDR  = 10 * 60        # Max. Lücke zw. identischen Stops
MERGE_DIST_M           = 150            # Radius bei Punkt 6
SNAP_RADIUS_M          = 10             # Punkt ↔ Netz (Klassifizierung) in m

# --------------------------------------------------------------------------- #
# Verkehrsmittel-Klassifizierung (deutsche Bezeichnungen)
# --------------------------------------------------------------------------- #
# Typische Geschwindigkeitsbereiche (km/h) – Kernbereich.
# Um Messfehler abzufangen, gibt es ±1 km/h „weiche“ Übergänge.
_SPEED_BANDS = {
    "Zu Fuß":       (0,  7),
    "Fahrrad":      (7,  30),
    "Auto":         (24, 300),
    "Bus":          (15, 90),
    "Straßenbahn":  (15, 90),
    "Zug":          (40, 250),
}
_MARGIN_KMH = 1.0                       # weicher Übergang um jede Band-Grenze

# OSM-Tag-Filter je Modus
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


def _speed_score(speed_kmh: float, mode: str) -> float:
    """
    Geschwindigkeits-Score ∈[0,1] mit weichem Übergang (±1 km/h).
    Innerhalb des Kernbandes = 1, außerhalb ±Margin linear abfallend.
    """
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


@lru_cache(maxsize=128)
def _load_osm(bbox: tuple[float, float, float, float],
              tags: dict) -> ox.geometries.geopandas.GeoDataFrame:  # type: ignore
    """Lädt OSM-Geometrien für eine Bounding-Box (north, south, east, west)."""
    north, south, east, west = bbox
    return ox.geometries_from_bbox(north, south, east, west, tags)


def _foot_distance_factor(dist_km: float) -> float:
    """
    Gewichtung für „Zu Fuß“:  
    • bis 1 km      → Faktor 1  
    • 1 km … 4 km   → linear fallend auf 0  
    • > 4 km        → 0
    """
    if dist_km <= 1.0:
        return 1.0
    if dist_km >= 4.0:
        return 0.0
    return (4.0 - dist_km) / 3.0


def classify_transport(
    seg_pts: list[tuple[float, float]],
    speed_kmh: float,
    dist_km: float,
) -> dict:
    """
    Liefert z. B.:
        {"Straßenbahn": 0.78, "Bus": 0.15, … , "best": "Straßenbahn"}
    """
    if not seg_pts:
        return {"best": None}

    lats, lons = zip(*seg_pts)
    north, south = max(lats) + 0.001, min(lats) - 0.001   # Puffer ≈ 100 m
    east,  west  = max(lons) + 0.001, min(lons) - 0.001
    bbox = (north, south, east, west)

    scores: dict[str, float] = {}
    for mode, tag_filter in _TAG_FILTERS.items():
        # 1) Geschwindigkeits-Score
        s_score = _speed_score(speed_kmh, mode)

        # 2) Netz-Abdeckung
        try:
            gdf = _load_osm(bbox, tag_filter)
            if gdf.empty:
                c_score = 0.0
            else:
                idx = gdf.sindex
                match = 0
                buf_deg = SNAP_RADIUS_M / 111_320
                for lat, lon in seg_pts:
                    pt = Point(lon, lat)
                    cand = list(idx.intersection(pt.buffer(buf_deg).bounds))
                    if cand:
                        nearest = gdf.iloc[cand].distance(pt).min() * 111_320
                        if nearest <= SNAP_RADIUS_M:
                            match += 1
                c_score = match / len(seg_pts)
        except Exception:
            c_score = 0.0

        # 3) kombinierter Score
        score = 0.4 * s_score + 0.6 * c_score

        # 4) Spezial: „Zu Fuß“ wird bei langen Distanzen gedämpft
        if mode == "Zu Fuß":
            score *= _foot_distance_factor(dist_km)

        scores[mode] = score

    # normieren
    tot = sum(scores.values()) or 1.0
    for k in scores:
        scores[k] /= tot

    scores["best"] = max(scores, key=lambda m: scores[m])
    return scores


# --------------------------------------------------------------------------- #
# Hilfsfunktionen
# --------------------------------------------------------------------------- #
def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Großkreis-Distanz in Metern zwischen zwei Koordinaten."""
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6_371_000 * 2 * asin(sqrt(a))


# --------------------------------------------------------------------------- #
# Reverse-Geocoding mit Cache
# --------------------------------------------------------------------------- #
_NOMINATIM = "https://nominatim.openstreetmap.org/reverse"
_HDRS      = {"User-Agent": "WegeRadar/1.0 (kontakt@example.com)"}
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
    key = (round(lat, 5), round(lon, 5))   # ≈ 1 m
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
    for fld in ("name", "road", "house_number", "postcode", "city"):
        if a.get(fld, "") != b.get(fld, ""):
            return False
    return True


# --------------------------------------------------------------------------- #
# Dateiauswahl-Dialog (GUI-Helfer)
# --------------------------------------------------------------------------- #
def show_date_dialog(master, gpx_folder: str, last: str, first: str) -> str | None:
    prefix = f"{last}_{first}_"
    files = [
        f for f in os.listdir(gpx_folder)
        if f.startswith(prefix) and f.lower().endswith(".gpx")
    ]
    if not files:
        from tkinter import messagebox
        messagebox.showinfo("WegeRadar",
                            f"Keine GPX-Dateien für {last}, {first} gefunden.",
                            parent=master)
        return None

    date_map = {os.path.splitext(f)[0].split("_")[2]: f for f in files}
    if len(date_map) == 1:
        return next(iter(date_map))

    import tkinter as tk
    dlg = tk.Toplevel(master)
    dlg.title("GPX-Datei auswählen")
    dlg.resizable(False, False)
    dlg.transient(master)
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
    """
    Liest <last>_<first>_<date>.gpx, erzeugt Aufenthaltsorte, verschmilzt sie
    und ergänzt Distanz, Geschwindigkeit & Verkehrsmittel-Ranking.
    """
    path = os.path.join(gpx_folder, f"{last}_{first}_{date}.gpx")
    if not os.path.exists(path):
        return []

    # ---- GPX einlesen ---------------------------------------------------- #
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

    # --------------------------------------------------------------------- #
    # 1. Stop-Cluster finden
    # --------------------------------------------------------------------- #
    clusters: List[Tuple[float, float, datetime, datetime]] = []
    i, n = 0, len(pts)
    while i < n:
        j = i + 1
        while j < n and haversine(
            pts[i][1], pts[i][2], pts[j][1], pts[j][2]
        ) <= dist_m:
            j += 1

        duration = (pts[j - 1][0] - pts[i][0]).total_seconds()
        if duration >= min_stop_sec:
            lat = sum(p[1] for p in pts[i:j]) / (j - i)
            lon = sum(p[2] for p in pts[i:j]) / (j - i)
            clusters.append((lat, lon, pts[i][0], pts[j - 1][0]))
            i = j
        else:
            i += 1

    # Start- und End-Punkt immer aufnehmen
    coords: List[Tuple[float, float, datetime, datetime]] = [
        (pts[0][1], pts[0][2], pts[0][0], pts[0][0]),
        *clusters,
        (pts[-1][1], pts[-1][2], pts[-1][0], pts[-1][0]),
    ]

    # --------------------------------------------------------------------- #
    # 2. Stops verschmelzen, wenn sie in derselben Minute enden/starten
    # --------------------------------------------------------------------- #
    merged: List[Tuple[float, float, datetime, datetime]] = []
    for lat, lon, s_dt, e_dt in coords:
        if (
            merged
            and merged[-1][3].strftime("%Y-%m-%d %H:%M")
            == s_dt.strftime("%Y-%m-%d %H:%M")
        ):
            merged[-1] = (merged[-1][0], merged[-1][1], merged[-1][2], e_dt)
        else:
            merged.append((lat, lon, s_dt, e_dt))

    # --------------------------------------------------------------------- #
    # 3. Adressen holen
    # --------------------------------------------------------------------- #
    enriched: List[dict] = []
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

    # --------------------------------------------------------------------- #
    # 4. Adress-/Distanz-Merging
    # --------------------------------------------------------------------- #
    final: List[dict] = []
    for item in enriched:
        if not final:
            final.append(item)
            continue

        prev = final[-1]
        gap_sec = (item["start_dt"] - prev["end_dt"]).total_seconds()
        same_addr = _same_address(prev, item)
        close_enough = (
            haversine(prev["lat"], prev["lon"], item["lat"], item["lon"]) <= MERGE_DIST_M
        )

        if gap_sec <= MAX_GAP_SEC_SAME_ADDR and (same_addr or close_enough):
            prev["end_dt"] = item["end_dt"]
        else:
            final.append(item)

    # --------------------------------------------------------------------- #
    # 5. Distanz, Tempo & Verkehrsmittel je Weg-Etappe
    # --------------------------------------------------------------------- #
    for idx in range(len(final) - 1):
        end_prev_utc   = final[idx]["end_dt"].astimezone(timezone.utc)
        start_next_utc = final[idx + 1]["start_dt"].astimezone(timezone.utc)

        # Distanz entlang der Spur
        dist_m_real = 0.0
        started = False
        for i in range(len(pts) - 1):
            t0, lat0, lon0 = pts[i]
            t1, lat1, lon1 = pts[i + 1]

            if t1 < end_prev_utc:
                continue
            if not started and t0 >= end_prev_utc:
                started = True
            if started:
                dist_m_real += haversine(lat0, lon0, lat1, lon1)
            if started and t1 >= start_next_utc:
                break

        dist_km = round(dist_m_real / 1000.0, 2)
        time_h = (start_next_utc - end_prev_utc).total_seconds() / 3600
        speed_kmh = round(dist_km / time_h, 2) if time_h > 0 else None

        final[idx]["next_dist_km_real"] = dist_km
        if speed_kmh is not None:
            final[idx]["next_speed_kmh_real"] = speed_kmh

        # Verkehrsmittel-Ranking
        seg_pts = [
            (lat, lon)
            for t, lat, lon in pts
            if end_prev_utc <= t <= start_next_utc
        ]
        final[idx]["next_mode_rank"] = classify_transport(
            seg_pts,
            speed_kmh or 0.0,
            dist_km,
        )

    return final