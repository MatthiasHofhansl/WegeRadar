# algorithm.py
import os
import tkinter as tk
from tkinter import messagebox
import gpxpy
import gpxpy.gpx
import requests
from math import radians, cos, sin, asin, sqrt
import time

# OpenStreetMap Nominatim für Reverse-Geocoding
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "WegeRadarApp/1.0 (your_email@example.com)"

# Liste möglicher Overpass-API-Endpunkte
OVERPASS_SERVERS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.openstreetmap.fr/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter"
]

# Cache für den schnellsten Server
_fastest_overpass = None

def _choose_overpass_url():
    global _fastest_overpass
    if _fastest_overpass:
        return _fastest_overpass

    timings = {}
    test_query = "[out:json][timeout:1];node(0);out;"
    headers = {"User-Agent": USER_AGENT}
    for url in OVERPASS_SERVERS:
        try:
            start = time.time()
            resp = requests.get(url, params={"data": test_query}, headers=headers, timeout=5)
            resp.raise_for_status()
            timings[url] = time.time() - start
        except Exception:
            # Server nicht erreichbar oder Timeout => überspringen
            continue

    if not timings:
        # Fallback auf den ersten
        _fastest_overpass = OVERPASS_SERVERS[0]
    else:
        # Wähle URL mit minimaler Antwortzeit
        _fastest_overpass = min(timings, key=timings.get)

    return _fastest_overpass

def show_date_dialog(master, gpx_folder, last, first):
    prefix = f"{last}_{first}_"
    files = [f for f in os.listdir(gpx_folder)
             if f.startswith(prefix) and f.lower().endswith('.gpx')]
    if not files:
        messagebox.showinfo("WegeRadar", f"Keine GPX-Dateien für {last}, {first} gefunden.", parent=master)
        return None
    date_map = {}
    for f in files:
        date = os.path.splitext(f)[0].split('_')[2] if '_' in f else "Unbekannt"
        date_map[date] = f
    if len(date_map) == 1:
        return next(iter(date_map))
    selected = {"date": None}
    dialog = tk.Toplevel(master)
    dialog.title("GPX-Datei Auswahl")
    dialog.transient(master)
    dialog.grab_set()
    tk.Label(dialog,
             text="Mehrere GPX-Dateien gefunden. Wähle bitte ein Datum:",
             font=("Arial", 12), justify="center", wraplength=300).pack(pady=10)
    def select(d):
        selected["date"] = d
        dialog.destroy()
    for d in sorted(date_map.keys()):
        tk.Button(dialog, text=d, width=20, command=lambda d=d: select(d)).pack(pady=2)
    dialog.update_idletasks()
    w, h = dialog.winfo_width(), dialog.winfo_height()
    x = (dialog.winfo_screenwidth() - w) // 2
    y = (dialog.winfo_screenheight() - h) // 2
    dialog.geometry(f"{w}x{h}+{x}+{y}")
    master.wait_window(dialog)
    return selected["date"]

def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlon, dlat = lon2 - lon1, lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return 6371000 * c  # Meter

def reverse_geocode(lat, lon):
    params = {"format": "jsonv2", "lat": lat, "lon": lon, "zoom": 18, "addressdetails": 1}
    headers = {"User-Agent": USER_AGENT}
    r = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=10)
    r.raise_for_status()
    data = r.json()
    return data.get("display_name", "Adresse nicht verfügbar")

def lookup_pois(lat, lon, radius=15):
    """
    Holt POIs innerhalb des gegebenen Radius via Overpass.
    Wählt dabei dynamisch den schnellsten Server aus.
    """
    overpass_url = _choose_overpass_url()
    query = f"""
[out:json];
(
  node(around:{radius},{lat},{lon})[amenity][name];
  way(around:{radius},{lat},{lon})[amenity][name];
);
out center;
"""
    headers = {"User-Agent": USER_AGENT}
    r = requests.post(overpass_url, data={"data": query}, headers=headers, timeout=15)
    r.raise_for_status()
    elements = r.json().get("elements", [])
    return list({el.get("tags", {}).get("name") for el in elements if el.get("tags", {}).get("name")})

def analyze_gpx(gpx_folder, last, first, date, radius=15, min_duration_sec=300):
    filename = f"{last}_{first}_{date}.gpx"
    path = os.path.join(gpx_folder, filename)
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        gpx = gpxpy.parse(f)
    points = [(pt.latitude, pt.longitude, pt.time)
              for tr in gpx.tracks for seg in tr.segments for pt in seg.points if pt.time]
    if not points:
        return []
    points.sort(key=lambda x: x[2])
    stops, i, n = [], 0, len(points)
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
            addr = reverse_geocode(mid_lat, mid_lon)
            pois = lookup_pois(mid_lat, mid_lon, radius)
            stops.append({
                "start_time": t0,
                "end_time": points[j-1][2],
                "duration_seconds": dur,
                "latitude": mid_lat,
                "longitude": mid_lon,
                "address": addr,
                "pois": pois
            })
            i = j
        else:
            i += 1
    return stops