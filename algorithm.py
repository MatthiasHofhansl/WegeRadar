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

    # Nur Geschwindigkeit & Distanz für Heuristik
    scores: Dict[str, float] = {}
    for mode in _SPEED_BANDS:
        s_score = _speed_score(speed_kmh, mode)
        score = s_score

        if mode == "Zu Fuß":
            score *= _foot_distance_factor(dist_km)

        scores[mode] = score

    # normieren
    tot = sum(scores.values()) or 1.0
    for k in scores:
        scores[k] /= tot

    scores["best"] = max(scores, key=lambda m: scores[m])
    return scores

# ---- Geo/Adressen-Tools ---------------------------------------------------

_NOMINATIM = "https://nominatim.openstreetmap.org/reverse"
_HDRS = {"User-Agent": "WegeRadar/1.0 (kontakt@example.com)"}
_GEOCACHE: Dict[Tuple[float, float], Dict[str, str]] = {}

def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6_371_000 * 2 * asin(sqrt(a))

def _extract_name(js: dict) -> str:
    if js.get("name"):
        return js["name"]
    addr = js.get("address", {})
    for k in ("amenity", "attraction", "leisure", "shop", "tourism"):
        if addr.get(k):
            return addr[k]
    return ""

def reverse_geocode(lat: float, lon: float) -> Dict[str, str]:
    key = (round(lat, 5), round(lon, 5))
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
            result.update({
                "name": _extract_name(js),
                "road": addr.get("road") or addr.get("pedestrian") or addr.get("footway") or "",
                "house_number": addr.get("house_number", ""),
                "postcode": addr.get("postcode", ""),
                "city": addr.get("city") or addr.get("town") or addr.get("village") or addr.get("hamlet") or "",
            })
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

    clusters: List[Tuple[float, float, datetime, datetime]] = []
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

    coords: List[Tuple[float, float, datetime, datetime]] = [
        (pts[0][1], pts[0][2], pts[0][0], pts[0][0]),
        *clusters,
        (pts[-1][1], pts[-1][2], pts[-1][0], pts[-1][0]),
    ]

    merged: List[Tuple[float, float, datetime, datetime]] = []
    for lat, lon, s_dt, e_dt in coords:
        if (
            merged
            and merged[-1][3].strftime("%Y-%m-%d %H:%M") == s_dt.strftime("%Y-%m-%d %H:%M")
        ):
            merged[-1] = (merged[-1][0], merged[-1][1], merged[-1][2], e_dt)
        else:
            merged.append((lat, lon, s_dt, e_dt))

    enriched: List[dict] = []
    for lat, lon, s_dt, e_dt in merged:
        addr = reverse_geocode(lat, lon)
        addr.update({
            "lat": lat,
            "lon": lon,
            "start_dt": s_dt.astimezone(BERLIN),
            "end_dt": e_dt.astimezone(BERLIN),
        })
        enriched.append(addr)

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

    for idx in range(len(final) - 1):
        end_prev_utc = final[idx]["end_dt"].astimezone(timezone.utc)
        start_next_utc = final[idx + 1]["start_dt"].astimezone(timezone.utc)

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

        seg_pts = [
            (lat, lon)
            for t, lat, lon in pts
            if end_prev_utc <= t <= start_next_utc
        ]

        final[idx]["next_mode_rank"] = classify_transport(
            seg_pts,
            speed_kmh or 0.0,
            dist_km
        )

        # Haltemuster wie gehabt
        HALT_SPEED_THRESHOLD = 3.0
        MIN_HALT_DURATION = 10

        halts = []
        halt_start = None
        for i in range(len(pts) - 1):
            t0, lat0, lon0 = pts[i]
            t1, lat1, lon1 = pts[i + 1]

            if not (end_prev_utc <= t0 <= start_next_utc and end_prev_utc <= t1 <= start_next_utc):
                continue

            dist_m = haversine(lat0, lon0, lat1, lon1)
            duration_s = (t1 - t0).total_seconds()
            speed_kmh_i = (dist_m / duration_s) * 3.6 if duration_s > 0 else 0

            if speed_kmh_i <= HALT_SPEED_THRESHOLD:
                if halt_start is None:
                    halt_start = t0
            else:
                if halt_start:
                    halt_duration = (t0 - halt_start).total_seconds()
                    if halt_duration >= MIN_HALT_DURATION:
                        halts.append(halt_duration)
                    halt_start = None

        if halt_start:
            halt_duration = (start_next_utc - halt_start).total_seconds()
            if halt_duration >= MIN_HALT_DURATION:
                halts.append(halt_duration)

        final[idx]["next_halt_count"] = len(halts)
        final[idx]["next_halt_avg_duration"] = round(sum(halts)/len(halts), 1) if halts else 0.0

    return final