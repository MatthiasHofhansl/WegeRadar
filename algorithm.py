# algorithm.py
import os
import tkinter as tk
from tkinter import messagebox
import gpxpy
import gpxpy.gpx
import datetime
import requests
from math import radians, cos, sin, asin, sqrt

# Für Reverse-Geocoding und POI-Lookup:
NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "WegeRadarApp/1.0 (your_email@example.com)"


def show_date_dialog(master, gpx_folder, last, first):
    """
    Öffnet einen Dialog mit allen verfügbaren GPX-Dateien für
    last_first_<Datum>.gpx im Ordner und lässt den Nutzer ein Datum wählen.
    Gibt das ausgewählte Datum zurück.
    """
    prefix = f"{last}_{first}_"
    files = [
        f for f in os.listdir(gpx_folder)
        if f.startswith(prefix) and f.lower().endswith('.gpx')
    ]

    if not files:
        messagebox.showinfo(
            "WegeRadar",
            f"Keine GPX-Dateien für {last}, {first} gefunden.",
            parent=master
        )
        return None

    # Datum → Dateiname mappen
    date_map = {}
    for f in files:
        base = os.path.splitext(f)[0]
        parts = base.split('_')
        date = parts[2] if len(parts) >= 3 else "Unbekannt"
        date_map[date] = f

    # Wenn nur eine Datei vorhanden ist, direkt zurückgeben
    if len(date_map) == 1:
        return next(iter(date_map))

    # Mehrere Dateien → Auswahl-Dialog
    dates = sorted(date_map.keys())
    selected = {"date": None}

    dialog = tk.Toplevel(master)
    dialog.title("GPX-Datei Auswahl")
    dialog.transient(master)
    dialog.grab_set()

    tk.Label(
        dialog,
        text=(
            "Für diese(n) Teilnehmer(in) stehen mehrere GPX-Dateien zur Verfügung.\n"
            "An welchem Tag soll die auszuwählende GPX-Datei aufgezeichnet worden sein?"
        ),
        font=("Arial", 12),
        justify="center",
        wraplength=300
    ).pack(pady=(10, 10), padx=10)

    def select(d):
        selected["date"] = d
        dialog.destroy()

    for d in dates:
        tk.Button(dialog, text=d, width=20, command=lambda d=d: select(d)).pack(pady=2, padx=20)

    # Dialog zentrieren
    dialog.update_idletasks()
    w = dialog.winfo_width()
    h = dialog.winfo_height()
    sw = dialog.winfo_screenwidth()
    sh = dialog.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    dialog.geometry(f"{w}x{h}+{x}+{y}")

    master.wait_window(dialog)
    return selected["date"]


def haversine(lat1, lon1, lat2, lon2):
    """
    Berechnet die Distanz in Metern zwischen zwei GPS-Punkten.
    """
    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    # haversine
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    r = 6371000  # Radius der Erde in Metern
    return c * r


def reverse_geocode(lat, lon):
    """
    Holt eine menschenlesbare Adresse via Nominatim.
    """
    params = {
        "format": "jsonv2",
        "lat": lat,
        "lon": lon,
        "zoom": 18,
        "addressdetails": 1
    }
    headers = {"User-Agent": USER_AGENT}
    r = requests.get(NOMINATIM_URL, params=params, headers=headers, timeout=10)
    r.raise_for_status()
    data = r.json()
    return data.get("display_name")


def lookup_pois(lat, lon, radius=15):
    """
    Findet benannte POIs (amenity) im Umkreis via Overpass.
    """
    query = f"""
    [out:json];
    (
      node(around:{radius},{lat},{lon})[amenity][name];
      way(around:{radius},{lat},{lon})[amenity][name];
    );
    out center;
    """
    r = requests.post(OVERPASS_URL, data={"data": query}, headers={"User-Agent": USER_AGENT}, timeout=15)
    r.raise_for_status()
    elements = r.json().get("elements", [])
    names = set()
    for el in elements:
        tags = el.get("tags", {})
        name = tags.get("name")
        if name:
            names.add(name)
    return list(names)


def analyze_gpx(gpx_folder, last, first, date, radius=15, min_duration_sec=300):
    """
    Lädt die GPX-Datei, erkennt Stopps ≥ min_duration_sec im radius (m),
    führt Reverse-Geocoding und POI-Suche durch und gibt eine Liste zurück.
    """
    filename = f"{last}_{first}_{date}.gpx"
    path = os.path.join(gpx_folder, filename)
    if not os.path.exists(path):
        return []

    # Parse GPX
    with open(path, "r", encoding="utf-8") as f:
        gpx = gpxpy.parse(f)

    # Alle Trackpoints sammeln
    points = []
    for track in gpx.tracks:
        for segment in track.segments:
            for pt in segment.points:
                if pt.time:
                    points.append((pt.latitude, pt.longitude, pt.time))
    if not points:
        return []

    # Sortiere nach Zeit
    points.sort(key=lambda x: x[2])

    stops = []
    i = 0
    n = len(points)
    while i < n:
        lat0, lon0, t0 = points[i]
        j = i + 1
        while j < n:
            lat1, lon1, t1 = points[j]
            if haversine(lat0, lon0, lat1, lon1) <= radius:
                j += 1
            else:
                break
        # Dauer berechnen
        dur = (points[j-1][2] - t0).total_seconds()
        if dur >= min_duration_sec:
            # Mittelpunkt für Geocoding
            lats = [p[0] for p in points[i:j]]
            lons = [p[1] for p in points[i:j]]
            mid_lat = sum(lats)/len(lats)
            mid_lon = sum(lons)/len(lons)
            # Reverse-Geocode + POIs
            try:
                addr = reverse_geocode(mid_lat, mid_lon)
            except Exception:
                addr = "Adresse nicht verfügbar"
            try:
                pois = lookup_pois(mid_lat, mid_lon, radius)
            except Exception:
                pois = []
            stops.append({
                "start_time": t0,
                "end_time": points[j-1][2],
                "duration_seconds": dur,
                "latitude": mid_lat,
                "longitude": mid_lon,
                "address": addr,
                "pois": pois
            })
            i = j  # überspringe bis hier
        else:
            i += 1

    return stops