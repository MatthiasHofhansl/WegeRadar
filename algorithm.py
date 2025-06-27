# algorithm.py
# (gleich geblieben, zuletzt bereits neu geschrieben)
import os
import tkinter as tk
from tkinter import messagebox
import gpxpy
from math import radians, cos, sin, asin, sqrt

# ------------------------------------------------------------- Parameter
SPEED_THRESHOLD_KMH   = 3       # „stehend“, wenn v ≤ 3 km/h
DIST_THRESHOLD_M      = 20      # oder wenn Punkte ≤ 20 m auseinander
MIN_STOP_DURATION_SEC = 180     # mind. 3 Minuten

# ------------------------------------------------------------- Hilfsfunktionen
def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    return 6371000 * 2 * asin(sqrt(a))

# ------------------------------------------------------------- UI‑Dialog
def show_date_dialog(master, gpx_folder, last, first):
    prefix = f"{last}_{first}_"
    files = [f for f in os.listdir(gpx_folder)
             if f.startswith(prefix) and f.lower().endswith('.gpx')]
    if not files:
        messagebox.showinfo("WegeRadar",
                            f"Keine GPX‑Dateien für {last}, {first} gefunden.",
                            parent=master)
        return None

    date_map = {os.path.splitext(f)[0].split('_')[2]: f for f in files}
    if len(date_map) == 1:
        return next(iter(date_map))

    dlg = tk.Toplevel(master)
    dlg.title("GPX‑Datei auswählen")
    dlg.resizable(False, False)
    dlg.transient(master)
    dlg.grab_set()
    tk.Label(dlg, text="Bitte Datum wählen:",
             font=("Arial", 12)).pack(pady=10)

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

# ------------------------------------------------------------- Kernfunktion
def analyze_gpx(gpx_folder, last, first, date,
                speed_kmh=SPEED_THRESHOLD_KMH,
                dist_m=DIST_THRESHOLD_M,
                min_stop_sec=MIN_STOP_DURATION_SEC):
    filename = f"{last}_{first}_{date}.gpx"
    path = os.path.join(gpx_folder, filename)
    if not os.path.exists(path):
        return [], []

    # Punkte einlesen
    with open(path, encoding="utf-8") as f:
        gpx = gpxpy.parse(f)

    pts = [(pt.latitude, pt.longitude, pt.time)
           for tr in gpx.tracks
           for seg in tr.segments
           for pt in seg.points
           if pt.time]
    if not pts:
        return [], []

    pts.sort(key=lambda x: x[2])

    # Stopps ermitteln
    stops_raw = []
    in_stop, stop_start_idx = False, None

    for i in range(1, len(pts)):
        lat1, lon1, t1 = pts[i-1]
        lat2, lon2, t2 = pts[i]

        dt = (t2 - t1).total_seconds() or 1.0
        dist = haversine(lat1, lon1, lat2, lon2)
        v_kmh = (dist / dt) * 3.6
        static = (v_kmh <= speed_kmh) or (dist <= dist_m)

        if static and not in_stop:
            in_stop, stop_start_idx = True, i-1
        if not static and in_stop:
            in_stop = False
            _append_if_long(pts, stop_start_idx, i-1,
                            stops_raw, min_stop_sec)

    if in_stop:  # Track endet im Stopp
        _append_if_long(pts, stop_start_idx, len(pts)-1,
                        stops_raw, min_stop_sec)

    if not stops_raw:
        return [], []

    # benachbarte Stops mergen
    merged = []
    for stop in stops_raw:
        if not merged:
            merged.append(stop)
            continue
        prev = merged[-1]
        if haversine(prev["latitude"], prev["longitude"],
                     stop["latitude"], stop["longitude"]) <= dist_m:
            prev["end_time"] = stop["end_time"]
            prev["duration_seconds"] += stop["duration_seconds"]
            prev["latitude"] = (prev["latitude"] + stop["latitude"]) / 2
            prev["longitude"] = (prev["longitude"] + stop["longitude"]) / 2
        else:
            merged.append(stop)

    for s in merged:
        s["address"] = f"{s['latitude']:.5f}, {s['longitude']:.5f}"
        s["pois"] = []

    return merged, []

# ------------------------------------------------------------- Helper
def _append_if_long(points, idx_s, idx_e, target, min_sec):
    t_s, t_e = points[idx_s][2], points[idx_e][2]
    dur = (t_e - t_s).total_seconds()
    if dur >= min_sec:
        lats = [p[0] for p in points[idx_s:idx_e+1]]
        lons = [p[1] for p in points[idx_s:idx_e+1]]
        target.append({
            "start_time": t_s,
            "end_time": t_e,
            "duration_seconds": dur,
            "latitude": sum(lats) / len(lats),
            "longitude": sum(lons) / len(lons)
        })