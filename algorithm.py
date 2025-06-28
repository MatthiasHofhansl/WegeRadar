"""
algorithm.py
============

Erkennt Aufenthalts-Orte und liefert zu jedem Ort:

    • Koordinaten (lat, lon)
    • start_dt, end_dt   (Europe/Berlin)
    • Name, Straße, Hausnr., PLZ, Stadt

Regeln zum Zusammenfassen:
1. Ort-Übergang in derselben Minute → verschmelzen (Endzeit wird erweitert).
2. Direkt aufeinanderfolgende Orte mit IDENTISCHER Adresse und
   Zeitlücke ≤ 10 Minuten → verschmelzen (Endzeit wird erweitert).
"""

from __future__ import annotations

import os, time, requests, gpxpy
from math import radians, cos, sin, asin, sqrt
from datetime import timezone, datetime, timedelta
from typing import Dict, List, Tuple

try:
    from zoneinfo import ZoneInfo
except ImportError:                                # Python < 3.9
    from datetime import timezone as ZoneInfo      # type: ignore
    ZoneInfo = lambda tz: timezone.utc             # type: ignore

# --------------------------------------------------------------------------- #
# Parameter
# --------------------------------------------------------------------------- #
DIST_THRESHOLD_M      = 50
MIN_STOP_DURATION_SEC = 180
NOMINATIM_SLEEP_SEC   = 1
MAX_GAP_SEC_SAME_ADDR = 10 * 60        # 10 Minuten

# --------------------------------------------------------------------------- #
# Hilfsfunktionen
# --------------------------------------------------------------------------- #
def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Meter-Distanz (Großkreis) zwischen zwei Koordinaten."""
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    return 6371000 * 2 * asin(sqrt(a))

_GEOCACHE: Dict[Tuple[float, float], Dict[str, str]] = {}
_NOMINATIM = "https://nominatim.openstreetmap.org/reverse"
_HDRS      = {"User-Agent": "WegeRadar/1.0 (kontakt@example.com)"}

def _extract_name(js: dict) -> str:
    if js.get("name"):
        return js["name"]
    addr = js.get("address", {})
    for k in ("amenity", "attraction", "leisure", "shop", "tourism"):
        if addr.get(k):
            return addr[k]
    return ""

def reverse_geocode(lat: float, lon: float) -> Dict[str, str]:
    """Liefert Address-Dict (mit Cache & Rate-Limit)."""
    key = (round(lat, 5), round(lon, 5))
    if key in _GEOCACHE:
        return _GEOCACHE[key]

    res = {k: "" for k in ("name", "road", "house_number", "postcode", "city")}
    try:
        r = requests.get(
            _NOMINATIM,
            params={"format":"jsonv2","lat":lat,"lon":lon,
                    "zoom":18,"addressdetails":1},
            headers=_HDRS, timeout=5
        )
        if r.status_code == 200:
            js   = r.json()
            addr = js.get("address", {})
            res.update({
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

    _GEOCACHE[key] = res
    time.sleep(NOMINATIM_SLEEP_SEC)
    return res

# --------------------------------------------------------------------------- #
# Dialog zur Datumsauswahl
# --------------------------------------------------------------------------- #
def show_date_dialog(master, gpx_folder: str, last: str, first: str) -> str | None:
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
    dlg = tk.Toplevel(master); dlg.title("GPX-Datei auswählen")
    dlg.resizable(False, False); dlg.transient(master); dlg.grab_set()

    tk.Label(dlg, text="Bitte Datum wählen:", font=("Arial", 12)).pack(pady=10)
    sel: dict[str | None] = {"d": None}
    def choose(d: str): sel["d"] = d; dlg.destroy()
    for d in sorted(date_map):
        tk.Button(dlg, text=d, width=22, command=lambda d=d: choose(d)).pack(pady=2)

    dlg.update_idletasks()
    w, h = dlg.winfo_width()+40, dlg.winfo_height()+20
    x = (dlg.winfo_screenwidth()-w)//2
    y = (dlg.winfo_screenheight()-h)//2
    dlg.geometry(f"{w}x{h}+{x}+{y}")
    dlg.wait_window()
    return sel["d"]

# --------------------------------------------------------------------------- #
# Hauptfunktion
# --------------------------------------------------------------------------- #
BERLIN = ZoneInfo("Europe/Berlin")

def _same_address(a: dict, b: dict) -> bool:
    """Vergleicht Adresse exakt über alle Felder."""
    for fld in ("name", "road", "house_number", "postcode", "city"):
        if a.get(fld, "") != b.get(fld, ""):
            return False
    return True


def analyze_gpx(
    gpx_folder: str,
    last: str,
    first: str,
    date: str,
    dist_m: int = DIST_THRESHOLD_M,
    min_stop_sec: int = MIN_STOP_DURATION_SEC,
) -> List[dict]:
    """
    Analysiert GPX, verschmilzt Orte nach beiden Regeln und
    ergänzt pro Aufenthalt die reale Distanz zum nächsten Ort
    anhand der GPX-Spur (Option 1 aus der Diskussion).
    """
    path = os.path.join(gpx_folder, f"{last}_{first}_{date}.gpx")
    if not os.path.exists(path):
        return []

    # ---- GPX einlesen ---------------------------------------------------- #
    with open(path, encoding="utf-8") as f:
        gpx = gpxpy.parse(f)

    pts = [
        (pt.time.replace(tzinfo=timezone.utc), pt.latitude, pt.longitude)
        for trk in gpx.tracks
        for seg in trk.segments
        for pt  in seg.points
        if pt.time
    ]
    if not pts:
        return []

    pts.sort(key=lambda x: x[0])

    # ---- Cluster bilden -------------------------------------------------- #
    clusters: List[Tuple[float, float, datetime, datetime]] = []
    i, n = 0, len(pts)
    while i < n:
        j = i + 1
        while j < n and haversine(pts[i][1], pts[i][2],
                                  pts[j][1], pts[j][2]) <= dist_m:
            j += 1
        if (pts[j-1][0] - pts[i][0]).total_seconds() >= min_stop_sec:
            lat  = sum(p[1] for p in pts[i:j]) / (j - i)
            lon  = sum(p[2] for p in pts[i:j]) / (j - i)
            clusters.append((lat, lon, pts[i][0], pts[j-1][0]))
            i = j
        else:
            i += 1

    coords: List[Tuple[float, float, datetime, datetime]] = [
        (pts[0][1],  pts[0][2],  pts[0][0],  pts[0][0]),
        *clusters,
        (pts[-1][1], pts[-1][2], pts[-1][0], pts[-1][0])
    ]

    # ---- 1. Regel: Minute-Überlappung verschmelzen ----------------------- #
    tmp: List[Tuple[float, float, datetime, datetime]] = []
    for lat, lon, s_dt, e_dt in coords:
        if not tmp:
            tmp.append((lat, lon, s_dt, e_dt))
            continue
        p_lat, p_lon, p_s, p_e = tmp[-1]
        if p_e.strftime("%Y-%m-%d %H:%M") == s_dt.strftime("%Y-%m-%d %H:%M"):
            tmp[-1] = (p_lat, p_lon, p_s, e_dt)
        else:
            tmp.append((lat, lon, s_dt, e_dt))

    # ---- Reverse-Geocode jedes tmp-Elements ----------------------------- #
    enriched: List[dict] = []
    for lat, lon, s_dt, e_dt in tmp:
        addr = reverse_geocode(lat, lon)
        addr.update({
            "lat": lat, "lon": lon,
            "start_dt": s_dt.astimezone(BERLIN),
            "end_dt":   e_dt.astimezone(BERLIN)
        })
        enriched.append(addr)

    # ---- 2. Regel: Gleiche Adresse + ≤10 min Lücke verschmelzen ---------- #
    final: List[dict] = []
    for item in enriched:
        if not final:
            final.append(item)
            continue

        prev = final[-1]
        gap_sec = (item["start_dt"] - prev["end_dt"]).total_seconds()
        if gap_sec <= MAX_GAP_SEC_SAME_ADDR and _same_address(prev, item):
            prev["end_dt"] = item["end_dt"]          # Endzeit erweitern
        else:
            final.append(item)

    # --------------------------------------------------------------------- #
    # Reale Streckenlängen zwischen aufeinanderfolgenden Aufenthalten
    # --------------------------------------------------------------------- #
    # Vorbereiten: Zeitstempel in UTC für schnelle Vergleiche
    utc_start_end = [
        (
            s["end_dt"].astimezone(timezone.utc),
            n["start_dt"].astimezone(timezone.utc),
        )
        for s, n in zip(final[:-1], final[1:])
    ]

    # Für jede Weg-Etappe summieren wir die Haversine-Abstände der
    # *aufgezeichneten* Track-Punkte zwischen den Zeitfenstern.
    for seg_idx, (t_end_prev, t_start_next) in enumerate(utc_start_end):
        dist_m_real = 0.0
        acc = False
        for i in range(len(pts) - 1):
            t0, lat0, lon0 = pts[i]
            t1, lat1, lon1 = pts[i + 1]

            # Noch vor dem Segment?
            if t1 < t_end_prev:
                continue
            # Ab dem ersten Punkt nach t_end_prev sammeln
            if not acc and t0 >= t_end_prev:
                acc = True
            if acc:
                dist_m_real += haversine(lat0, lon0, lat1, lon1)
            # Segment fertig?
            if acc and t1 >= t_start_next:
                break

        # Kilometer mit 2 Nachkommastellen speichern
        final[seg_idx]["next_dist_km_real"] = round(dist_m_real / 1000.0, 2)

    return final