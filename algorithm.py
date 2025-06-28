"""
algorithm.py
============

Erkennt Aufenthalts‐Orte in einer GPX‐Datei.

* Punkte werden zu Clustern (Orten) zusammengefasst,
  wenn sie ≥ 3 min in einem Radius von 50 m liegen.

* Start- und Endpunkt der Aufzeichnung werden immer ausgegeben.

* Wenn zwei aufeinander­folgende Orte sich in **derselben Minute berühren**
  (Ende Ort A und Start Ort B haben identisches YYYY-MM-DD HH:MM),
  werden sie **verschmolzen**:
      – Koordinaten/Adresse stammen von Ort A  
      – Startzeit bleibt von Ort A  
      – Endzeit wird auf die Endzeit von Ort B gesetzt
"""

from __future__ import annotations

import os, time, requests, gpxpy
from math import radians, cos, sin, asin, sqrt
from datetime import timezone, datetime
from typing import Dict, List, Tuple

try:                                               # Zeitzonen
    from zoneinfo import ZoneInfo
except ImportError:                                # Fallback (Python < 3.9)
    from datetime import timezone as ZoneInfo      # type: ignore
    ZoneInfo = lambda tz: timezone.utc             # type: ignore

# --------------------------------------------------------------------------- #
# Parameter
# --------------------------------------------------------------------------- #
DIST_THRESHOLD_M      = 50
MIN_STOP_DURATION_SEC = 180
NOMINATIM_SLEEP_SEC   = 1

# --------------------------------------------------------------------------- #
# Hilfsfunktionen
# --------------------------------------------------------------------------- #
def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Meter-Distanz zwischen zwei Koordinaten (Großkreis)."""
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    return 6371000 * 2 * asin(sqrt(a))

_GEOCACHE: Dict[Tuple[float, float], Dict[str, str]] = {}
_NOMINATIM = "https://nominatim.openstreetmap.org/reverse"
_HDRS      = {"User-Agent": "WegeRadar/1.0 (kontakt@example.com)"}

def _extract_name(js: dict) -> str:
    if js.get("name"):
        return js["name"]
    addr = js.get("address", {})
    for k in ("amenity", "attraction", "leisure", "shop", "tourism"):
        if addr.get(k):
            return addr[k]
    return ""

def reverse_geocode(lat: float, lon: float) -> Dict[str, str]:
    """Liefert Name, Straße, Hausnr., PLZ, Stadt (mit Cache & Rate-Limit)."""
    key = (round(lat, 5), round(lon, 5))
    if key in _GEOCACHE:
        return _GEOCACHE[key]

    res = {k: "" for k in ("name", "road", "house_number", "postcode", "city")}
    try:
        r = requests.get(
            _NOMINATIM,
            params={"format": "jsonv2", "lat": lat, "lon": lon,
                    "zoom": 18, "addressdetails": 1},
            headers=_HDRS, timeout=5
        )
        if r.status_code == 200:
            js   = r.json()
            addr = js.get("address", {})
            res.update({
                "name":         _extract_name(js),
                "road":         addr.get("road") or addr.get("pedestrian")
                                or addr.get("footway") or "",
                "house_number": addr.get("house_number", ""),
                "postcode":     addr.get("postcode", ""),
                "city":         addr.get("city") or addr.get("town")
                                or addr.get("village") or addr.get("hamlet") or ""
            })
    except Exception:
        pass

    _GEOCACHE[key] = res
    time.sleep(NOMINATIM_SLEEP_SEC)
    return res

# --------------------------------------------------------------------------- #
# Dialog: GPX-Datei auswählen
# --------------------------------------------------------------------------- #
def show_date_dialog(master, gpx_folder: str, last: str, first: str) -> str | None:
    prefix = f"{last}_{first}_"
    files  = [f for f in os.listdir(gpx_folder)
              if f.startswith(prefix) and f.lower().endswith(".gpx")]
    if not files:
        from tkinter import messagebox
        messagebox.showinfo(
            "WegeRadar",
            f"Keine GPX-Dateien für {last}, {first} gefunden.",
            parent=master,
        )
        return None

    date_map = {os.path.splitext(f)[0].split("_")[2]: f for f in files}
    if len(date_map) == 1:
        return next(iter(date_map))

    import tkinter as tk
    dlg = tk.Toplevel(master); dlg.title("GPX-Datei auswählen")
    dlg.resizable(False, False); dlg.transient(master); dlg.grab_set()

    tk.Label(dlg, text="Bitte Datum wählen:", font=("Arial", 12)).pack(pady=10)
    sel: dict[str | None] = {"d": None}
    def choose(d: str): sel["d"] = d; dlg.destroy()
    for d in sorted(date_map):
        tk.Button(dlg, text=d, width=22, command=lambda d=d: choose(d)).pack(pady=2)

    dlg.update_idletasks()
    w, h = dlg.winfo_width()+40, dlg.winfo_height()+20
    x = (dlg.winfo_screenwidth()-w)//2
    y = (dlg.winfo_screenheight()-h)//2
    dlg.geometry(f"{w}x{h}+{x}+{y}")
    dlg.wait_window()
    return sel["d"]

# --------------------------------------------------------------------------- #
# Kernfunktion
# --------------------------------------------------------------------------- #
BERLIN = ZoneInfo("Europe/Berlin")

def analyze_gpx(
    gpx_folder: str,
    last: str,
    first: str,
    date: str,
    dist_m: int = DIST_THRESHOLD_M,
    min_stop_sec: int = MIN_STOP_DURATION_SEC,
) -> List[dict]:
    """Analysiert eine GPX-Datei und gibt eine Liste von Orts-Dicts zurück."""
    file_path = os.path.join(gpx_folder, f"{last}_{first}_{date}.gpx")
    if not os.path.exists(file_path):
        return []

    # ---- GPX einlesen ---------------------------------------------------- #
    with open(file_path, encoding="utf-8") as f:
        gpx = gpxpy.parse(f)

    pts = [
        (pt.time.replace(tzinfo=timezone.utc), pt.latitude, pt.longitude)
        for trk in gpx.tracks
        for seg in trk.segments
        for pt  in seg.points
        if pt.time
    ]
    if not pts:
        return []

    pts.sort(key=lambda x: x[0])

    # ---- Cluster bilden -------------------------------------------------- #
    clusters: List[Tuple[float, float, datetime, datetime]] = []
    i, n = 0, len(pts)
    while i < n:
        j = i + 1
        while j < n and haversine(pts[i][1], pts[i][2],
                                  pts[j][1], pts[j][2]) <= dist_m:
            j += 1
        if (pts[j-1][0] - pts[i][0]).total_seconds() >= min_stop_sec:
            lat  = sum(p[1] for p in pts[i:j]) / (j - i)
            lon  = sum(p[2] for p in pts[i:j]) / (j - i)
            clusters.append((lat, lon, pts[i][0], pts[j-1][0]))
            i = j
        else:
            i += 1

    # ---- Start/Endpunkt ergänzen ---------------------------------------- #
    coords: List[Tuple[float, float, datetime, datetime]] = [
        (pts[0][1],  pts[0][2],  pts[0][0],  pts[0][0]),  # Start
        *clusters,
        (pts[-1][1], pts[-1][2], pts[-1][0], pts[-1][0])  # Ende
    ]

    # ---- Überlappung in gleicher Minute verschmelzen -------------------- #
    merged: List[Tuple[float, float, datetime, datetime]] = []
    for lat, lon, s_dt, e_dt in coords:
        if not merged:
            merged.append((lat, lon, s_dt, e_dt))
            continue

        prev_lat, prev_lon, prev_s, prev_e = merged[-1]
        if prev_e.strftime("%Y-%m-%d %H:%M") == s_dt.strftime("%Y-%m-%d %H:%M"):
            # Verschmelzen → Endzeit des neuen Ortes übernehmen
            merged[-1] = (prev_lat, prev_lon, prev_s, e_dt)
        else:
            merged.append((lat, lon, s_dt, e_dt))

    # ---- Reverse-Geocoding & Ergebnis ----------------------------------- #
    result: List[dict] = []
    for lat, lon, start_dt, end_dt in merged:
        addr = reverse_geocode(lat, lon)
        addr.update({
            "lat": lat, "lon": lon,
            "start_dt": start_dt.astimezone(BERLIN),
            "end_dt":   end_dt.astimezone(BERLIN)
        })
        result.append(addr)

    return result