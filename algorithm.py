import os
import time
from math import radians, cos, sin, asin, sqrt
from datetime import timezone, datetime
from typing import Dict, List, Tuple

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from datetime import timezone as ZoneInfo
    ZoneInfo = lambda tz: timezone.utc

import requests
import gpxpy

# --------------------------------------------------------------------------- #
# Schwellenwerte
# --------------------------------------------------------------------------- #
DIST_THRESHOLD_M      = 50
MIN_STOP_DURATION_SEC = 180
NOMINATIM_SLEEP_SEC   = 1

# --------------------------------------------------------------------------- #
# Distanzfunktion
# --------------------------------------------------------------------------- #
def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371000 * 2 * asin(sqrt(a))

# --------------------------------------------------------------------------- #
# Reverse-Geocoding (Nominatim)
# --------------------------------------------------------------------------- #
_GEOCACHE: Dict[Tuple[float, float], Dict[str, str]] = {}
_NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
_NOMINATIM_HEADERS = {"User-Agent": "WegeRadar/1.0 (kontakt@example.com)"}

def _extract_name(js: dict) -> str:
    if js.get("name"):
        return js["name"]
    addr = js.get("address", {})
    for key in ("amenity", "attraction", "leisure", "shop", "tourism"):
        if addr.get(key):
            return addr[key]
    return ""

def reverse_geocode(lat: float, lon: float) -> Dict[str, str]:
    key = (round(lat, 5), round(lon, 5))
    if key in _GEOCACHE:
        return _GEOCACHE[key]

    result = {k: "" for k in ("name", "road", "house_number", "postcode", "city")}
    try:
        r = requests.get(
            _NOMINATIM_URL,
            params={"format": "jsonv2", "lat": lat, "lon": lon,
                    "zoom": 18, "addressdetails": 1},
            headers=_NOMINATIM_HEADERS, timeout=5)
        if r.status_code == 200:
            js = r.json()
            addr = js.get("address", {})
            result.update({
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

    _GEOCACHE[key] = result
    time.sleep(NOMINATIM_SLEEP_SEC)
    return result

# --------------------------------------------------------------------------- #
# Datumsauswahl-Dialog – jetzt größer & zentriert
# --------------------------------------------------------------------------- #
def show_date_dialog(master, gpx_folder, last, first):
    prefix = f"{last}_{first}_"
    files = [f for f in os.listdir(gpx_folder)
             if f.startswith(prefix) and f.lower().endswith(".gpx")]
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

    sel = {"d": None}
    def choose(d): sel["d"] = d; dlg.destroy()
    for d in sorted(date_map):
        tk.Button(dlg, text=d, width=22,  # etwas breiter
                  command=lambda d=d: choose(d)).pack(pady=2)

    # Größe und Position anpassen
    dlg.update_idletasks()
    w, h = dlg.winfo_width() + 40, dlg.winfo_height() + 20  # etwas größer
    screen_w = dlg.winfo_screenwidth()
    screen_h = dlg.winfo_screenheight()
    x = (screen_w - w) // 2
    y = (screen_h - h) // 2
    dlg.geometry(f"{w}x{h}+{x}+{y}")

    dlg.wait_window()
    return sel["d"]

# --------------------------------------------------------------------------- #
# Kernfunktion – unverändert (liefert Orte + Zeitstempel)
# --------------------------------------------------------------------------- #
BERLIN = ZoneInfo("Europe/Berlin")

def analyze_gpx(gpx_folder, last, first, date,
                dist_m=DIST_THRESHOLD_M,
                min_stop_sec=MIN_STOP_DURATION_SEC) -> List[dict]:
    filename = f"{last}_{first}_{date}.gpx"
    path = os.path.join(gpx_folder, filename)
    if not os.path.exists(path):
        return []

    with open(path, encoding="utf-8") as f:
        gpx = gpxpy.parse(f)

    pts = [(pt.time.replace(tzinfo=timezone.utc), pt.latitude, pt.longitude)
           for trk in gpx.tracks for seg in trk.segments for pt in seg.points
           if pt.time]
    if not pts:
        return []

    pts.sort(key=lambda x: x[0])

    clusters: List[Tuple[float, float, datetime]] = []
    i, n = 0, len(pts)
    while i < n:
        j = i + 1
        while j < n and haversine(pts[i][1], pts[i][2],
                                  pts[j][1], pts[j][2]) <= dist_m:
            j += 1
        if (pts[j-1][0] - pts[i][0]).total_seconds() >= min_stop_sec:
            lat = sum(p[1] for p in pts[i:j]) / (j - i)
            lon = sum(p[2] for p in pts[i:j]) / (j - i)
            clusters.append((lat, lon, pts[i][0]))
            i = j
        else:
            i += 1

    coords = [
        (pts[0][1],  pts[0][2],  pts[0][0]),
        *clusters,
        (pts[-1][1], pts[-1][2], pts[-1][0])
    ]

    result = []
    for lat, lon, start_dt in coords:
        addr = reverse_geocode(lat, lon)
        addr.update({
            "lat": lat,
            "lon": lon,
            "start_dt": start_dt.astimezone(BERLIN)
        })
        result.append(addr)
    return result