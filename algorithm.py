# algorithm.py

import os
import tkinter as tk
from tkinter import messagebox
import gpxpy
import requests
from math import radians, cos, sin, asin, sqrt
import time

# OpenStreetMap Nominatim für Reverse-Geocoding
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "WegeRadarApp/1.0 (your_email@example.com)"

# Liste öffentlicher Overpass-Server
OVERPASS_SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter"
]

# Session für Connection-Pooling und User-Agent
_session = requests.Session()
_session.headers.update({"User-Agent": USER_AGENT})

# Caches für Geocoding und POIs
_reverse_cache = {}
_pois_cache = {}
_fastest_overpass = None

def _choose_overpass_url():
    global _fastest_overpass
    if _fastest_overpass:
        return _fastest_overpass

    timings = {}
    test_q = "[out:json][timeout:1];node(0);out;"
    for url in OVERPASS_SERVERS:
        try:
            t0 = time.time()
            r = _session.get(url, params={"data": test_q}, timeout=5)
            r.raise_for_status()
            timings[url] = time.time() - t0
        except Exception:
            continue

    _fastest_overpass = min(timings, key=timings.get) if timings else OVERPASS_SERVERS[0]
    return _fastest_overpass

def show_date_dialog(master, gpx_folder, last, first):
    prefix = f"{last}_{first}_"
    files = [f for f in os.listdir(gpx_folder)
             if f.startswith(prefix) and f.lower().endswith('.gpx')]
    if not files:
        messagebox.showinfo(
            "WegeRadar",
            f"Keine GPX-Dateien für {last}, {first} gefunden.",
            parent=master
        )
        return None

    date_map = {os.path.splitext(f)[0].split('_')[2]: f for f in files}
    if len(date_map) == 1:
        return next(iter(date_map))

    selected = {"date": None}
    dlg = tk.Toplevel(master)
    dlg.title("GPX-Datei Auswahl")
    dlg.transient(master)
    dlg.grab_set()
    tk.Label(
        dlg,
        text="Mehrere GPX-Dateien gefunden. Wähle bitte ein Datum:",
        font=("Arial", 12),
        justify="center",
        wraplength=300
    ).pack(pady=10)

    def choose(d):
        selected["date"] = d
        dlg.destroy()

    for d in sorted(date_map):
        tk.Button(dlg, text=d, width=20, command=lambda d=d: choose(d)).pack(pady=2)

    dlg.update_idletasks()
    w, h = dlg.winfo_width(), dlg.winfo_height()
    x = (dlg.winfo_screenwidth() - w) // 2
    y = (dlg.winfo_screenheight() - h) // 2
    dlg.geometry(f"{w}x{h}+{x}+{y}")
    master.wait_window(dlg)
    return selected["date"]

def haversine(lat1, lon1, lat2, lon2):
    """Entfernung in Metern zwischen zwei GPS-Punkten."""
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    return 6371000 * 2 * asin(sqrt(a))

def reverse_geocode(lat, lon):
    """
    Nutzt Nominatim (OpenStreetMap) für Reverse-Geocoding mit Cache
    und honoriert die 1 Request/s-Regel durch sleep.
    """
    key = (round(lat, 5), round(lon, 5))
    if key in _reverse_cache:
        return _reverse_cache[key]

    params = {
        "lat": lat,
        "lon": lon,
        "format": "jsonv2",
        "zoom": 18,
        "addressdetails": 1
    }
    r = _session.get(NOMINATIM_URL, params=params, timeout=10)
    r.raise_for_status()
    addr = r.json().get("display_name", "Adresse nicht verfügbar")

    # Rate-Limit respektieren
    time.sleep(1)

    _reverse_cache[key] = addr
    return addr

def lookup_pois(lat, lon, radius=15):
    """
    Nutzt Overpass für POI-Suche mit Cache und sleep,
    um Warteschlangen zu vermeiden.
    """
    key = (round(lat, 5), round(lon, 5), radius)
    if key in _pois_cache:
        return _pois_cache[key]

    overpass_url = _choose_overpass_url()
    query = f"""
[out:json][timeout:25];
(
  node(around:{radius},{lat},{lon})[amenity];
  way(around:{radius},{lat},{lon})[amenity];
);
out center;
"""
    r = _session.post(overpass_url, data={"data": query}, timeout=30)
    r.raise_for_status()
    elements = r.json().get("elements", [])

    pois = []
    for el in elements:
        name = el.get("tags", {}).get("name")
        if name:
            pois.append(name)
    pois = list(dict.fromkeys(pois))

    # Rate-Limit respektieren
    time.sleep(1)

    _pois_cache[key] = pois
    return pois

def analyze_gpx(gpx_folder, last, first, date, radius=15, min_duration_sec=300):
    """
    Parst die GPX-Datei, findet Stopps ≥ min_duration_sec,
    erkennt zusätzlich pausenbedingte Lücken als Stopps,
    und ruft reverse_geocode & lookup_pois sequenziell auf.
    """
    filename = f"{last}_{first}_{date}.gpx"
    path = os.path.join(gpx_folder, filename)
    if not os.path.exists(path):
        return []

    with open(path, encoding="utf-8") as f:
        gpx = gpxpy.parse(f)

    points = [(pt.latitude, pt.longitude, pt.time)
              for tr in gpx.tracks
              for seg in tr.segments
              for pt in seg.points
              if pt.time]
    if not points:
        return []

    points.sort(key=lambda x: x[2])

    # 1.) Stops basierend auf räumlicher Nähe
    raw_stops = []
    i, n = 0, len(points)
    while i < n:
        lat0, lon0, t0 = points[i]
        j = i + 1
        while j < n and haversine(lat0, lon0, *points[j][:2]) <= radius:
            j += 1
        dur = (points[j-1][2] - t0).total_seconds()
        if dur >= min_duration_sec:
            seg = points[i:j]
            mid_lat = sum(p[0] for p in seg) / len(seg)
            mid_lon = sum(p[1] for p in seg) / len(seg)
            raw_stops.append({
                "start_time": t0,
                "end_time": points[j-1][2],
                "duration_seconds": dur,
                "latitude": mid_lat,
                "longitude": mid_lon
            })
            i = j
        else:
            i += 1

    # 2.) Pausen in Aufzeichnung als Stopps erkennen
    pause_stops = []
    for k in range(len(points) - 1):
        lat_k, lon_k, t_k = points[k]
        lat_n, lon_n, t_n = points[k+1]
        gap = (t_n - t_k).total_seconds()
        if gap >= min_duration_sec and haversine(lat_k, lon_k, lat_n, lon_n) <= radius:
            pause_stops.append({
                "start_time": t_k,
                "end_time": t_n,
                "duration_seconds": gap,
                "latitude": (lat_k + lat_n) / 2,
                "longitude": (lon_k + lon_n) / 2
            })

    # 3.) Vereinen und duplizieren entfernen
    combined = {}
    for stop in raw_stops + pause_stops:
        key = (stop["start_time"], stop["end_time"])
        combined[key] = stop
    unique_stops = sorted(combined.values(), key=lambda s: s["start_time"])

    # 4.) Reverse-Geocode und POIs sequenziell holen
    stops = []
    for entry in unique_stops:
        entry["address"] = reverse_geocode(entry["latitude"], entry["longitude"])
        entry["pois"]    = lookup_pois(entry["latitude"], entry["longitude"])
        stops.append(entry)

    return stops