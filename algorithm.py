# algorithm.py
import os
import tkinter as tk
from tkinter import messagebox
import gpxpy
from mapbox import Geocoder, Tilequery
from math import radians, cos, sin, asin, sqrt

# Deinen Mapbox-Token hier einfügen
MAPBOX_TOKEN = "pk.eyJ1IjoibWF0dGhpYXNoZmwiLCJhIjoiY21jZjVsbnp5MDVidzJscXYyNGlvYWx2NiJ9.x5gxjRDS5FwuJK09SYna7A"

# Mapbox-Clients
_geocoder  = Geocoder(access_token=MAPBOX_TOKEN)
_tilequery = Tilequery(access_token=MAPBOX_TOKEN)

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
    dialog = tk.Toplevel(master)
    dialog.title("GPX-Datei Auswahl")
    dialog.transient(master)
    dialog.grab_set()
    tk.Label(
        dialog,
        text="Mehrere GPX-Dateien gefunden. Wähle bitte ein Datum:",
        font=("Arial", 12),
        justify="center",
        wraplength=300
    ).pack(pady=10)

    def choose(d):
        selected["date"] = d
        dialog.destroy()

    for d in sorted(date_map):
        tk.Button(dialog, text=d, width=20, command=lambda d=d: choose(d)).pack(pady=2)

    dialog.update_idletasks()
    w, h = dialog.winfo_width(), dialog.winfo_height()
    x = (dialog.winfo_screenwidth() - w) // 2
    y = (dialog.winfo_screenheight() - h) // 2
    dialog.geometry(f"{w}x{h}+{x}+{y}")
    master.wait_window(dialog)
    return selected["date"]

def haversine(lat1, lon1, lat2, lon2):
    """Distanz in Metern zwischen zwei GPS-Koordinaten."""
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return 6371000 * c

def reverse_geocode(lat, lon):
    """
    Nutzt Mapbox Geocoding API, um eine Adresse zu erhalten.
    """
    resp = _geocoder.reverse(lon=lon, lat=lat, types=['address'], limit=1)
    resp.raise_for_status()
    features = resp.json().get("features", [])
    if not features:
        return "Adresse nicht verfügbar"
    return features[0]["place_name"]

def lookup_pois(lat, lon, radius=15, limit=10):
    """
    Nutzt Mapbox Tilequery API, um POIs in der Umgebung zu finden.
    """
    resp = _tilequery.query(
        lon, lat,
        radius=radius,
        limit=limit,
        layers=['poi_label']
    )
    resp.raise_for_status()
    features = resp.json().get("features", [])
    pois = [
        feat["properties"].get("name")
        for feat in features
        if feat["properties"].get("name")
    ]
    return pois

def analyze_gpx(gpx_folder, last, first, date, radius=15, min_duration_sec=300):
    """
    Parst die GPX-Datei, findet Stopps ≥ min_duration_sec,
    reverse-geocodet und holt POIs per Mapbox.
    """
    filename = f"{last}_{first}_{date}.gpx"
    path = os.path.join(gpx_folder, filename)
    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        gpx = gpxpy.parse(f)

    points = [
        (pt.latitude, pt.longitude, pt.time)
        for tr in gpx.tracks
        for seg in tr.segments
        for pt in seg.points
        if pt.time
    ]
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