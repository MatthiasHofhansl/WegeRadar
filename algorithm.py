"""
algorithm.py
============

Liest eine GPX-Datei, erkennt Aufenthalts-Orte und liefert zu jedem Ort

    • Koordinaten (lat, lon)
    • Start-Zeitstempel  (erster Punkt im Cluster)
    • End-Zeitstempel    (letzter Punkt im Cluster)
    • Adresse (Name, Straße, Hausnr., PLZ, Stadt)

Start- und Endpunkt der Aufzeichnung werden immer mit ausgegeben
(ihre Start- und End-Zeit sind identisch).
"""

from __future__ import annotations

import os
import time
from math import radians, cos, sin, asin, sqrt
from datetime import timezone, datetime
from typing import Dict, List, Tuple

import gpxpy
import requests

try:                                # Zeitzonen-Support
    from zoneinfo import ZoneInfo
except ImportError:                 # Python < 3.9 – Fallback: UTC
    from datetime import timezone as ZoneInfo  # type: ignore
    ZoneInfo = lambda tz: timezone.utc  # type: ignore[assignment]

# --------------------------------------------------------------------------- #
# Einstell-Parameter
# --------------------------------------------------------------------------- #
DIST_THRESHOLD_M: int      = 50     # ≥ Punkte in 50 m Umkreis gelten als „selber Ort“
MIN_STOP_DURATION_SEC: int = 180    # ≥ 3 min Aufenthalt
NOMINATIM_SLEEP_SEC: int   = 1      # OSM-Rate-Limit

# --------------------------------------------------------------------------- #
# Hilfsfunktion: Haversine-Distanz
# --------------------------------------------------------------------------- #
def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Großkreis-Distanz (in Metern) zwischen zwei Breiten/Längen."""
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371000 * 2 * asin(sqrt(a))

# --------------------------------------------------------------------------- #
# Reverse-Geocoding (Nominatim)
# --------------------------------------------------------------------------- #
_GEOCACHE: Dict[Tuple[float, float], Dict[str, str]] = {}
_NOMINATIM_URL   = "https://nominatim.openstreetmap.org/reverse"
_NOMINATIM_HDRS  = {"User-Agent": "WegeRadar/1.0 (kontakt@example.com)"}

def _extract_name(js: dict) -> str:
    """Versucht, einen sinnvollen Ortsnamen aus der Nominatim-Antwort zu ziehen."""
    if js.get("name"):
        return js["name"]
    address = js.get("address", {})
    for key in ("amenity", "attraction", "leisure", "shop", "tourism"):
        if address.get(key):
            return address[key]
    return ""

def reverse_geocode(lat: float, lon: float) -> Dict[str, str]:
    """
    Ruft Nominatim auf und gibt ein Dict mit
    name, road, house_number, postcode, city zurück.
    Ergebnisse werden gecached.
    """
    key = (round(lat, 5), round(lon, 5))          # ~1 m Genauigkeit
    if key in _GEOCACHE:
        return _GEOCACHE[key]

    result = {k: "" for k in ("name", "road", "house_number", "postcode", "city")}

    try:
        resp = requests.get(
            _NOMINATIM_URL,
            params={
                "format": "jsonv2",
                "lat": lat,
                "lon": lon,
                "zoom": 18,
                "addressdetails": 1,
            },
            headers=_NOMINATIM_HDRS,
            timeout=5,
        )
        if resp.status_code == 200:
            js    = resp.json()
            addr  = js.get("address", {})
            result.update(
                {
                    "name":         _extract_name(js),
                    "road":         addr.get("road")
                                    or addr.get("pedestrian")
                                    or addr.get("footway")
                                    or "",
                    "house_number": addr.get("house_number", ""),
                    "postcode":     addr.get("postcode", ""),
                    "city":         addr.get("city")
                                    or addr.get("town")
                                    or addr.get("village")
                                    or addr.get("hamlet")
                                    or "",
                }
            )
    except Exception:
        pass  # Bei Fehlern einfach leere Felder lassen

    _GEOCACHE[key] = result
    time.sleep(NOMINATIM_SLEEP_SEC)               # OSM-Policy einhalten
    return result

# --------------------------------------------------------------------------- #
# Dialog: GPX-Datei auswählen (bei mehreren Datums-Dateien)
# --------------------------------------------------------------------------- #
def show_date_dialog(master, gpx_folder: str, last: str, first: str) -> str | None:
    """
    Zeigt (falls nötig) ein Dialog-Fenster zur Auswahl der GPX-Datei (nach Datum).
    Gibt das Datum (YYYY-MM-DD) zurück – oder None, wenn abgebrochen.
    """
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

    dlg = tk.Toplevel(master)
    dlg.title("GPX-Datei auswählen")
    dlg.resizable(False, False)
    dlg.transient(master)
    dlg.grab_set()

    tk.Label(dlg, text="Bitte Datum wählen:", font=("Arial", 12)).pack(pady=10)

    sel: dict[str | None] = {"date": None}

    def choose(d: str) -> None:
        sel["date"] = d
        dlg.destroy()

    for d in sorted(date_map):
        tk.Button(dlg, text=d, width=22, command=lambda d=d: choose(d)).pack(pady=2)

    dlg.update_idletasks()
    w, h = dlg.winfo_width() + 40, dlg.winfo_height() + 20  # etwas größer
    x = (dlg.winfo_screenwidth() - w) // 2
    y = (dlg.winfo_screenheight() - h) // 2
    dlg.geometry(f"{w}x{h}+{x}+{y}")

    dlg.wait_window()
    return sel["date"]

# --------------------------------------------------------------------------- #
# Hauptfunktion: Aufenthalts-Orte bestimmen
# --------------------------------------------------------------------------- #
BERLIN = ZoneInfo("Europe/Berlin")   # gewünschte Orts-Zeitzone für Ausgabe

def analyze_gpx(
    gpx_folder: str,
    last: str,
    first: str,
    date: str,
    dist_m: int = DIST_THRESHOLD_M,
    min_stop_sec: int = MIN_STOP_DURATION_SEC,
) -> List[dict]:
    """
    Liefert eine Liste von Dicts.  Jedes Dict enthält:

        lat, lon, start_dt, end_dt, name, road, house_number, postcode, city
    """
    filename = f"{last}_{first}_{date}.gpx"
    path     = os.path.join(gpx_folder, filename)
    if not os.path.exists(path):
        return []

    # ---------------- GPX-Datei einlesen ------------------- #
    with open(path, encoding="utf-8") as f:
        gpx = gpxpy.parse(f)

    pts: list[tuple[datetime, float, float]] = [
        (pt.time.replace(tzinfo=timezone.utc), pt.latitude, pt.longitude)
        for trk in gpx.tracks
        for seg in trk.segments
        for pt  in seg.points
        if pt.time
    ]
    if not pts:
        return []

    pts.sort(key=lambda x: x[0])  # nach Zeit

    # ---------------- Aufenthalts-Cluster ------------------ #
    clusters: list[tuple[float, float, datetime, datetime]] = []
    i, n = 0, len(pts)
    while i < n:
        j = i + 1
        while j < n and haversine(pts[i][1], pts[i][2],
                                  pts[j][1], pts[j][2]) <= dist_m:
            j += 1

        duration = (pts[j - 1][0] - pts[i][0]).total_seconds()
        if duration >= min_stop_sec:
            # Mittelwert der Koordinaten
            lat = sum(p[1] for p in pts[i:j]) / (j - i)
            lon = sum(p[2] for p in pts[i:j]) / (j - i)
            start_dt, end_dt = pts[i][0], pts[j - 1][0]
            clusters.append((lat, lon, start_dt, end_dt))
            i = j
        else:
            i += 1

    # ---------------- Start-/Endpunkt ergänzen ------------- #
    coords: list[tuple[float, float, datetime, datetime]] = [
        (pts[0][1],  pts[0][2],  pts[0][0],  pts[0][0]),   # Start
        *clusters,
        (pts[-1][1], pts[-1][2], pts[-1][0], pts[-1][0]),  # Ende
    ]

    # ---------------- Reverse-Geocoding -------------------- #
    result: List[dict] = []
    for lat, lon, start_dt, end_dt in coords:
        addr = reverse_geocode(lat, lon)
        addr.update(
            {
                "lat":      lat,
                "lon":      lon,
                "start_dt": start_dt.astimezone(BERLIN),
                "end_dt":   end_dt.astimezone(BERLIN),
            }
        )
        result.append(addr)

    return result