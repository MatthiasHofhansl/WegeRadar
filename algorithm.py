# algorithm.py
import os
import tkinter as tk
from tkinter import messagebox
import gpxpy
import requests
from math import radians, cos, sin, asin, sqrt

# Photon-API-Endpunkte
PHOTON_REVERSE_URL = "https://photon.komoot.io/reverse"
PHOTON_SEARCH_URL  = "https://photon.komoot.io/api/"

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
    """Entfernung in Metern zwischen zwei GPS-Punkten."""
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlon, dlat = lon2 - lon1, lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    return 6371000 * c

def reverse_geocode(lat, lon):
    """
    Nutzt Photon für Reverse-Geocoding.
    Gibt eine lesbare Adresse zurück.
    """
    params = {"lat": lat, "lon": lon}
    r = requests.get(PHOTON_REVERSE_URL, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    feats = data.get("features", [])
    if not feats:
        return "Adresse nicht verfügbar"
    props = feats[0].get("properties", {})
    # Baue eine Adresse aus Namen und Straßendaten zusammen
    parts = []
    if props.get("name"):
        parts.append(props["name"])
    if props.get("street"):
        parts.append(props["street"])
    if props.get("city"):
        parts.append(props["city"])
    if props.get("country"):
        parts.append(props["country"])
    return ", ".join(parts) if parts else "Adresse nicht verfügbar"

def lookup_pois(lat, lon, radius=15, limit=50):
    """
    Nutzt Photon, um POIs (amenity) in der Umgebung zu finden.
    Filtert clientseitig nach dem Radius.
    """
    params = {
        "lat": lat,
        "lon": lon,
        "limit": limit,
        "osm_tag": "amenity"
    }
    r = requests.get(PHOTON_SEARCH_URL, params=params, timeout=10)
    r.raise_for_status()
    data = r.json()
    feats = data.get("features", [])
    pois = []
    for feat in feats:
        coords = feat["geometry"]["coordinates"]  # [lon, lat]
        dist = haversine(lat, lon, coords[1], coords[0])
        if dist <= radius:
            props = feat.get("properties", {})
            name = props.get("name") or props.get("osm_value")
            if name:
                pois.append(name)
    # Duplikate entfernen
    return list(dict.fromkeys(pois))

def analyze_gpx(gpx_folder, last, first, date, radius=15, min_duration_sec=300):
    """
    Parst die GPX-Datei, findet Stopps ≥ min_duration_sec,
    führt Reverse-Geocoding und POI-Suche mit Photon durch.
    """
    filename = f"{last}_{first}_{date}.gpx"
    path = os.path.join(gpx_folder, filename)
    if not os.path.exists(path):
        return []

    with open(path, "r", encoding="utf-8") as f:
        gpx = gpxpy.parse(f)

    points = [
        (pt.latitude, pt.longitude, pt.time)
        for tr in gpx.tracks for seg in tr.segments for pt in seg.points if pt.time
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