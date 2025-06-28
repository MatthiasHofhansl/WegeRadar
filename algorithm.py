# algorithm.py
import os
import gpxpy
from math import radians, cos, sin, asin, sqrt
from datetime import timezone

# Schwellenwerte – kannst du jederzeit anpassen
DIST_THRESHOLD_M      = 50      # Radius, um Punkte demselben Ort zuzuordnen
MIN_STOP_DURATION_SEC = 180     # Mindestaufenthalt: 3 Minuten (3 * 60 s)

# --------------------------------------------------------------------------- #
# Hilfsfunktionen
# --------------------------------------------------------------------------- #
def haversine(lat1, lon1, lat2, lon2):
    """Entfernung zweier Lat/Lon-Paare in Metern (Großkreis, Haversine)."""
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371000 * 2 * asin(sqrt(a))

def show_date_dialog(master, gpx_folder, last, first):
    """
    Kleiner Dateiauswahldialog: zeigt alle GPX-Dateien des Teilnehmers
    an und lässt den Nutzer ein Datum auswählen.
    """
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
        return next(iter(date_map))              # nur ein Datum vorhanden

    import tkinter as tk
    dlg = tk.Toplevel(master)
    dlg.title("GPX-Datei auswählen")
    dlg.resizable(False, False)
    dlg.transient(master)
    dlg.grab_set()

    tk.Label(dlg, text="Bitte Datum wählen:", font=("Arial", 12))\
        .pack(pady=10)

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
# Kernfunktion: Stay-Point-Analyse
# --------------------------------------------------------------------------- #
def analyze_gpx(gpx_folder, last, first, date,
                dist_m=DIST_THRESHOLD_M,
                min_stop_sec=MIN_STOP_DURATION_SEC):
    """
    Liest eine GPX-Datei ein und liefert eine Liste von Koordinatenpaaren
    (lat, lon), an denen sich die Person mindestens `min_stop_sec` lang
    innerhalb eines Radius von `dist_m` aufgehalten hat.

    Rückgabeformat: List[Tuple[float, float]]
    """
    filename = f"{last}_{first}_{date}.gpx"
    path = os.path.join(gpx_folder, filename)
    if not os.path.exists(path):
        return []

    # ---------------- GPX einlesen ---------------- #
    with open(path, encoding="utf-8") as f:
        gpx = gpxpy.parse(f)

    # (UTC-Zeit, lat, lon) sammeln
    pts = [(pt.time.replace(tzinfo=timezone.utc), pt.latitude, pt.longitude)
           for trk in gpx.tracks
           for seg in trk.segments
           for pt in seg.points
           if pt.time]

    if not pts:
        return []

    # chrono sortieren (sicherstellen)
    pts.sort(key=lambda x: x[0])

    # ---------------- Stay-Point-Detection -------- #
    stay_points = []
    i, n = 0, len(pts)

    while i < n:
        j = i + 1
        # suche das erste j, das weiter als dist_m entfernt ist
        while j < n and haversine(pts[i][1], pts[i][2],
                                  pts[j][1], pts[j][2]) <= dist_m:
            j += 1

        # Verweildauer zwischen i und j-1
        duration = (pts[j - 1][0] - pts[i][0]).total_seconds()

        if duration >= min_stop_sec:
            # Schwerpunkt der Punkte i … j-1
            lats = [p[1] for p in pts[i:j]]
            lons = [p[2] for p in pts[i:j]]
            stay_points.append((sum(lats) / len(lats),
                                sum(lons) / len(lons)))
            i = j       # springe hinter das Cluster
        else:
            i += 1      # gehe zum nächsten Punkt weiter

    return stay_points