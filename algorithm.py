# algorithm.py
# ============
from __future__ import annotations
import os
import time
from datetime import datetime, timezone
from math import radians, cos, sin, asin, sqrt
from typing import Dict, List, Tuple

import gpxpy
import requests

# Versuche, GeoPandas einzubinden
try:
    import geopandas as gpd
    from shapely.geometry import Point
    _HAS_GEOPANDAS = True
except ImportError:
    _HAS_GEOPANDAS = False

# Zonen-Info (Zeitzone)
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

_SPEED_BANDS = {
    "Zu Fuß":       (0,  7),
    "Fahrrad":      (7,  30),
    "Auto":         (24, 300),
    "Bus":          (15, 90),
    "Straßenbahn":  (15, 90),
    "Zug":          (40, 250),
}
_MARGIN_KMH = 1.0

# In diesem Dict halten wir pro Modus eine Liste von GeoDataFrames, falls GeoPandas verfügbar ist
_osm_data: Dict[str, List[gpd.GeoDataFrame]] = {}

def load_osm_data(mapping: Dict[str, str]) -> None:
    """
    Nimmt ein Dict { "Auto": <pfad>, "Zu Fuß": <pfad>, usw. } entgegen,
    und liest diese Dateien ein (falls GeoPandas verfügbar).
    """
    global _osm_data
    # Leeren/neu initialisieren
    _osm_data = {
        "Auto": [],
        "Zu Fuß": [],
        "Fahrrad": [],
        "Bus": [],
        "Straßenbahn": [],
        "Zug": []
    }

    if not _HAS_GEOPANDAS:
        # Ohne GeoPandas können wir halt nichts machen
        return

    for mode, path in mapping.items():
        if not path:
            continue
        try:
            gdf = gpd.read_file(path)
            if gdf.crs is None:
                gdf.set_crs(epsg=4326, inplace=True)
            else:
                gdf.to_crs(epsg=4326, inplace=True)
            _osm_data[mode].append(gdf)
        except Exception:
            pass

def show_date_dialog(master, gpx_folder: str, last: str, first: str) -> str | None:
    """
    Fragt den User, welche GPX-Datei (Datum) er laden will, wenn es mehrere gibt.
    """
    prefix = f"{last}_{first}_"
    files = [
        f for f in os.listdir(gpx_folder)
        if f.startswith(prefix) and f.lower().endswith(".gpx")
    ]
    if not files:
        from tkinter import messagebox
        messagebox.showinfo(
            "WegeRadar",
            f"Keine GPX-Dateien für {last}, {first} gefunden.",
            parent=master
        )
        return None

    date_map = {os.path.splitext(f)[0].split("_")[2]: f for f in files if len(f.split("_")) >= 3}
    if len(date_map) == 1:
        return next(iter(date_map))

    import tkinter as tk
    dlg = tk.Toplevel(master)
    dlg.title("GPX-Datei auswählen")
    dlg.resizable(False, False)
    dlg.transient(master)
    dlg.grab_set()

    tk.Label(dlg, text="Bitte Datum wählen:", font=("Arial", 12)).pack(pady=10)
    sel: Dict[str | None] = {"d": None}

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

def reverse_geocode(lat: float, lon: float) -> Dict[str, str]:
    """
    Fragt Nominatim (OpenStreetMap), um eine Adresse zu erhalten.
    """
    # Einfacher Cache, rundet auf 5 Nachkommastellen
    key = (round(lat, 5), round(lon, 5))
    if key in _REVGEO_CACHE:
        return _REVGEO_CACHE[key]

    out = {"name": "", "road": "", "house_number": "", "postcode": "", "city": ""}
    try:
        r = requests.get(
            "https://nominatim.openstreetmap.org/reverse",
            params={
                "format": "jsonv2",
                "lat": lat,
                "lon": lon,
                "zoom": 18,
                "addressdetails": 1,
            },
            headers={"User-Agent": "WegeRadar/1.0"},
            timeout=5,
        )
        if r.status_code == 200:
            js = r.json()
            addr = js.get("address", {})
            name_val = js.get("name", "")
            if not name_val:
                # evtl. in js["address"]
                for k in ("amenity", "attraction", "leisure", "shop", "tourism"):
                    if addr.get(k):
                        name_val = addr[k]
                        break
            out["name"] = name_val or ""
            out["road"] = (
                addr.get("road")
                or addr.get("pedestrian")
                or addr.get("footway")
                or ""
            )
            out["house_number"] = addr.get("house_number", "")
            out["postcode"] = addr.get("postcode", "")
            out["city"] = (
                addr.get("city")
                or addr.get("town")
                or addr.get("village")
                or addr.get("hamlet")
                or ""
            )
    except Exception:
        pass

    _REVGEO_CACHE[key] = out
    time.sleep(NOMINATIM_SLEEP_SEC)
    return out

_REVGEO_CACHE: Dict[Tuple[float, float], Dict[str, str]] = {}

def _same_address(a: dict, b: dict) -> bool:
    for fld in ("name", "road", "house_number", "postcode", "city"):
        if a.get(fld, "") != b.get(fld, ""):
            return False
    return True

def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371000.0 * 2 * asin(sqrt(a))

def analyze_gpx(
    gpx_folder: str,
    last: str,
    first: str,
    date: str,
    dist_m: int = DIST_THRESHOLD_M,
    min_stop_sec: int = MIN_STOP_DURATION_SEC,
) -> List[dict]:
    """
    Liest die GPX-Datei (last_first_date.gpx), sammelt Stop-Infos (Cluster),
    führt Reverse-Geocoding durch, verknüpft Wege usw.
    """
    path = os.path.join(gpx_folder, f"{last}_{first}_{date}.gpx")
    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        gpx = gpxpy.parse(f)

    # Alle Punkte extrahieren
    pts: List[Tuple[datetime, float, float]] = []
    for trk in gpx.tracks:
        for seg in trk.segments:
            for pt in seg.points:
                if pt.time:
                    pts.append((pt.time.replace(tzinfo=timezone.utc), pt.latitude, pt.longitude))

    if not pts:
        return []

    pts.sort(key=lambda x: x[0])

    # Clusterbildung: Wo stand man "länger"?
    clusters: List[Tuple[float, float, datetime, datetime]] = []
    i, n = 0, len(pts)
    while i < n:
        j = i + 1
        while j < n and haversine_m(pts[i][1], pts[i][2], pts[j][1], pts[j][2]) <= dist_m:
            j += 1
        duration_s = (pts[j - 1][0] - pts[i][0]).total_seconds()
        if duration_s >= min_stop_sec:
            lat = sum(p[1] for p in pts[i:j]) / (j - i)
            lon = sum(p[2] for p in pts[i:j]) / (j - i)
            clusters.append((lat, lon, pts[i][0], pts[j - 1][0]))
            i = j
        else:
            i += 1

    # Start, Cluster, End
    coords: List[Tuple[float, float, datetime, datetime]] = [
        (pts[0][1], pts[0][2], pts[0][0], pts[0][0]),
        *clusters,
        (pts[-1][1], pts[-1][2], pts[-1][0], pts[-1][0]),
    ]

    # Eng zusammenliegende Stationen mergen
    merged: List[Tuple[float, float, datetime, datetime]] = []
    for lat, lon, s_dt, e_dt in coords:
        if (merged and
            merged[-1][3].strftime("%Y-%m-%d %H:%M") == s_dt.strftime("%Y-%m-%d %H:%M")):
            merged[-1] = (merged[-1][0], merged[-1][1], merged[-1][2], e_dt)
        else:
            merged.append((lat, lon, s_dt, e_dt))

    # Reverse-Geocoding
    places: List[dict] = []
    for lat, lon, s_dt, e_dt in merged:
        info = reverse_geocode(lat, lon)
        info["lat"] = lat
        info["lon"] = lon
        info["start_dt"] = s_dt.astimezone(BERLIN)
        info["end_dt"] = e_dt.astimezone(BERLIN)
        places.append(info)

    # Zusammenfassen, falls nahe beieinander
    final: List[dict] = []
    for item in places:
        if not final:
            final.append(item)
            continue
        last_item = final[-1]
        gap_s = (item["start_dt"] - last_item["end_dt"]).total_seconds()
        close_enough = (haversine_m(
            last_item["lat"], last_item["lon"], item["lat"], item["lon"]
        ) <= MERGE_DIST_M)
        if gap_s <= MAX_GAP_SEC_SAME_ADDR and (close_enough or _same_address(last_item, item)):
            # Gleicher Ort
            last_item["end_dt"] = item["end_dt"]
        else:
            final.append(item)

    # Jetzt Weginfos (Distanz, Geschwindigkeit, Transport) zwischen Stationen
    for idx in range(len(final) - 1):
        start_t = final[idx]["end_dt"].astimezone(timezone.utc)
        end_t = final[idx+1]["start_dt"].astimezone(timezone.utc)

        dist_m_total = 0.0
        started = False
        for i in range(len(pts) - 1):
            t0, la0, lo0 = pts[i]
            t1, la1, lo1 = pts[i+1]
            if t1 < start_t:
                continue
            if not started and t0 >= start_t:
                started = True
            if started:
                dist_m_total += haversine_m(la0, lo0, la1, lo1)
            if started and t1 >= end_t:
                break

        dist_km = round(dist_m_total / 1000, 2)
        dt_h = (end_t - start_t).total_seconds() / 3600.0
        speed_kmh = round(dist_km / dt_h, 2) if dt_h > 0 else None

        final[idx]["next_dist_km_real"] = dist_km
        if speed_kmh is not None:
            final[idx]["next_speed_kmh_real"] = speed_kmh

        # Punkte in diesem Segment -> OSM-basiertes Matching
        seg_points = [
            (la, lo)
            for t, la, lo in pts
            if start_t <= t <= end_t
        ]
        transported = classify_transport(seg_points, speed_kmh or 0.0, dist_km)
        final[idx]["next_mode_rank"] = transported

        # Haltestellen in diesem Weg
        HALT_SPEED_THRESHOLD = 3.0
        MIN_HALT_DURATION = 10
        halts = []
        halt_start = None

        for i in range(len(pts) - 1):
            t_curr, la_curr, lo_curr = pts[i]
            t_next, la_next, lo_next = pts[i+1]
            if not (start_t <= t_curr <= end_t and start_t <= t_next <= end_t):
                continue

            d_m = haversine_m(la_curr, lo_curr, la_next, lo_next)
            d_s = (t_next - t_curr).total_seconds()
            sp_kmh = (d_m / d_s) * 3.6 if d_s > 0 else 0.0

            if sp_kmh <= HALT_SPEED_THRESHOLD:
                if halt_start is None:
                    halt_start = t_curr
            else:
                if halt_start:
                    ht_dur = (t_curr - halt_start).total_seconds()
                    if ht_dur >= MIN_HALT_DURATION:
                        halts.append(ht_dur)
                    halt_start = None

        if halt_start:
            ht_dur = (end_t - halt_start).total_seconds()
            if ht_dur >= MIN_HALT_DURATION:
                halts.append(ht_dur)

        final[idx]["next_halt_count"] = len(halts)
        final[idx]["next_halt_avg_duration"] = round(sum(halts)/len(halts), 1) if halts else 0.0

    return final

def classify_transport(
    seg_pts: List[Tuple[float, float]],
    speed_kmh: float,
    dist_km: float,
) -> dict:
    """
    Stellt anhand von Speedbands und OSM (falls vorhanden) das Verkehrsmittel fest.
    """
    if not seg_pts:
        return {"best": None}

    # 1) Geschwindigkeitsbasierte Score
    scores = {}
    for mode, (lo, hi) in _SPEED_BANDS.items():
        val = 0.0
        # Basic Speed-Check
        if lo <= speed_kmh <= hi:
            val = 1.0
        else:
            # Toleranz an den Rändern
            if lo - _MARGIN_KMH < speed_kmh < lo:
                val = (speed_kmh - (lo - _MARGIN_KMH)) / _MARGIN_KMH
            elif hi < speed_kmh < hi + _MARGIN_KMH:
                val = ((hi + _MARGIN_KMH) - speed_kmh) / _MARGIN_KMH

        # Spezieller Bonus für sehr kurze Distanzen bei "Zu Fuß"
        if mode == "Zu Fuß":
            if dist_km <= 1:
                val += 0.5

        scores[mode] = val

    # 2) OSM-Matching (falls GeoPandas verfügbar)
    if _HAS_GEOPANDAS:
        from shapely.geometry import Point
        max_dist_deg = 0.0002
        for (lat, lon) in seg_pts:
            pt = Point(lon, lat)
            for mode in _osm_data:
                for gdf in _osm_data[mode]:
                    if not gdf.empty:
                        dmin = gdf.distance(pt).min()
                        if dmin <= max_dist_deg:
                            scores[mode] += 0.5
                            break

    # 3) Normalisieren
    total = sum(scores.values())
    if total > 0:
        for m in scores:
            scores[m] /= total

    best_mode = max(scores.keys(), key=lambda k: scores[k]) if scores else None
    scores["best"] = best_mode
    return scores

# Ende des Codes