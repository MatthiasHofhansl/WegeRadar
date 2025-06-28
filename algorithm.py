# algorithm.py
import os
import time
import requests
import gpxpy
from math import radians, cos, sin, asin, sqrt
from datetime import timezone

# --------------------------------------------------------------------------- #
# Schwellenwerte (ggf. anpassen)
# --------------------------------------------------------------------------- #
DIST_THRESHOLD_M      = 50      # Radius, um Punkte demselben Ort zuzuordnen
MIN_STOP_DURATION_SEC = 180     # Mindestaufenthalt: 3 Minuten
NOMINATIM_SLEEP_SEC   = 1       # Höfliche Pause zw. API-Aufrufen

# --------------------------------------------------------------------------- #
# Distanz-Funktion (Haversine)
# --------------------------------------------------------------------------- #
def haversine(lat1, lon1, lat2, lon2):
    """Entfernung zweier Lat/Lon-Paare in Metern (Großkreis, Haversine)."""
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371000 * 2 * asin(sqrt(a))

# --------------------------------------------------------------------------- #
# Reverse-Geocoding (Nominatim) – einfacher Cache
# --------------------------------------------------------------------------- #
_GEOCACHE: dict[tuple[float, float], str] = {}
_NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
_NOMINATIM_HEADERS = {
    "User-Agent": "WegeRadar/1.0 (kontakt@example.com)"      # ggf. anpassen
}

def reverse_geocode(lat: float, lon: float) -> str:
    """
    Liefert für (lat, lon) eine menschen­lesbare Adresse.
    Bei Fehlschlag → 'Adresse nicht gefunden'.
    """
    key = (round(lat, 5), round(lon, 5))   # ~1 m Genauigkeit
    if key in _GEOCACHE:
        return _GEOCACHE[key]

    try:
        resp = requests.get(
            _NOMINATIM_URL,
            params={"format": "jsonv2", "lat": lat, "lon": lon, "zoom": 18},
            headers=_NOMINATIM_HEADERS,
            timeout=5
        )
        if resp.status_code == 200:
            data = resp.json()
            address = data.get("display_name") or "Adresse nicht gefunden"
        else:
            address = "Adresse nicht gefunden"
    except Exception:
        address = "Adresse nicht gefunden"

    _GEOCACHE[key] = address
    time.sleep(NOMINATIM_SLEEP_SEC)        # OSM-Policy: 1 s Pause
    return address

# --------------------------------------------------------------------------- #
# Dialog für Datumsauswahl (wird von GUI genutzt)
# --------------------------------------------------------------------------- #
def show_date_dialog(master, gpx_folder, last, first):
    prefix = f"{last}_{first}_"
    files = [f for f in os.listdir(gpx_folder)
             if f.startswith(prefix) and f.lower().endswith('.gpx')]
    if not files:
        from tkinter import messagebox
        messagebox.showinfo(
            "WegeRadar",
            f"Keine GPX-Dateien für {last}, {first} gefunden.",
            parent=master
        )
        return None

    date_map = {os.path.splitext(f)[0].split('_')[2]: f for f in files}
    if len(date_map) == 1:
        return next(iter(date_map))

    import tkinter as tk
    dlg = tk.Toplevel(master)
    dlg.title("GPX-Datei auswählen")
    dlg.resizable(False, False)
    dlg.transient(master)
    dlg.grab_set()

    tk.Label(dlg, text="Bitte Datum wählen:", font=("Arial", 12)).pack(pady=10)

    selected = {"date": None}

    def choose(d):
        selected["date"] = d
        dlg.destroy()

    for d in sorted(date_map):
        tk.Button(dlg, text=d, width=20,
                  command=lambda d=d: choose(d)).pack(pady=2)

    dlg.update_idletasks()
    w, h = dlg.winfo_width(), dlg.winfo_height()
    x = (dlg.winfo_screenwidth() - w) // 2
    y = (dlg.winfo_screenheight() - h) // 2
    dlg.geometry(f"{w}x{h}+{x}+{y}")
    dlg.wait_window()
    return selected["date"]

# --------------------------------------------------------------------------- #
# Kernfunktion: Stay-Point-Analyse + Start/End immer dabei
# --------------------------------------------------------------------------- #
def analyze_gpx(gpx_folder, last, first, date,
                dist_m: int = DIST_THRESHOLD_M,
                min_stop_sec: int = MIN_STOP_DURATION_SEC):
    """
    Liefert eine Liste von Tripeln (lat, lon, adresse).

    * Alle Aufenthaltsorte (≥ min_stop_sec innerhalb dist_m)
    * Immer zusätzlich: exakter Start- und Endpunkt
    """
    filename = f"{last}_{first}_{date}.gpx"
    path = os.path.join(gpx_folder, filename)
    if not os.path.exists(path):
        return []

    # -------- GPX einlesen -------- #
    with open(path, encoding="utf-8") as f:
        gpx = gpxpy.parse(f)

    pts = [(pt.time.replace(tzinfo=timezone.utc), pt.latitude, pt.longitude)
           for trk in gpx.tracks
           for seg in trk.segments
           for pt in seg.points
           if pt.time]
    if not pts:
        return []

    pts.sort(key=lambda x: x[0])            # chronologisch

    # -------- Staypoints bestimmen -------- #
    stay_points: list[tuple[float, float]] = []
    i, n = 0, len(pts)
    while i < n:
        j = i + 1
        while j < n and haversine(pts[i][1], pts[i][2],
                                  pts[j][1], pts[j][2]) <= dist_m:
            j += 1
        duration = (pts[j - 1][0] - pts[i][0]).total_seconds()
        if duration >= min_stop_sec:
            lats = [p[1] for p in pts[i:j]]
            lons = [p[2] for p in pts[i:j]]
            stay_points.append((sum(lats) / len(lats),
                                sum(lons) / len(lons)))
            i = j
        else:
            i += 1

    # -------- Start- & Endkoordinaten immer ergänzen -------- #
    coords: list[tuple[float, float]] = []
    start_lat, start_lon = pts[0][1], pts[0][2]
    end_lat,   end_lon   = pts[-1][1], pts[-1][2]

    coords.append((start_lat, start_lon))
    coords.extend(stay_points)
    coords.append((end_lat, end_lon))

    # -------- Reverse-Geocoding -------- #
    result: list[tuple[float, float, str]] = []
    for lat, lon in coords:
        addr = reverse_geocode(lat, lon)
        result.append((lat, lon, addr))

    return result