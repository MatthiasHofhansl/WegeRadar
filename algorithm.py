"""
algorithm.py
============

Erkennt Aufenthalts-Orte in einer GPX-Spur, verschmilzt benachbarte Stops
nach festen Regeln und reichert sie mit Adressdaten an.

Für jeden Aufenthalt speichert das Skript:
    • Koordinaten lat / lon
    • Start- und End-Zeit (Europe/Berlin)
    • Name, Straße, Haus-Nr., PLZ, Stadt (per Nominatim)

Für jede Weg-Etappe (Stop i  →  Stop i+1):
    • next_dist_km_real      (Distanz entlang der GPX-Punkte)
    • next_speed_kmh_real    (Durchschnittsgeschwindigkeit)
"""

from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from math import radians, cos, sin, asin, sqrt
from typing import Dict, List, Tuple

import gpxpy
import requests

# --------------------------------------------------------------------------- #
# Zeitzone
# --------------------------------------------------------------------------- #
try:
    from zoneinfo import ZoneInfo           # Py ≥ 3.9
except ImportError:                         # Py 3.8
    from datetime import timezone as ZoneInfo  # type: ignore
    ZoneInfo = lambda tz: timezone.utc         # type: ignore

BERLIN = ZoneInfo("Europe/Berlin")

# --------------------------------------------------------------------------- #
# Parameter
# --------------------------------------------------------------------------- #
DIST_THRESHOLD_M       = 50           # Radius für das erste Stop-Clustering
MIN_STOP_DURATION_SEC  = 180          # Mindest­aufenthaltsdauer (3 min)
NOMINATIM_SLEEP_SEC    = 1            # Wartezeit pro Geocode-Request
MAX_GAP_SEC_SAME_ADDR  = 10 * 60      # Max. Lücke zw. identischen Stops (10 min)

MERGE_DIST_M           = 150          # *** Neuer Radius für Punkt 6 ***


# --------------------------------------------------------------------------- #
# Hilfsfunktionen
# --------------------------------------------------------------------------- #
def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Großkreis-Distanz in Metern zwischen zwei Koordinaten."""
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371000 * 2 * asin(sqrt(a))


# --------------------------------------------------------------------------- #
# Reverse-Geocoding mit Cache
# --------------------------------------------------------------------------- #
_NOMINATIM    = "https://nominatim.openstreetmap.org/reverse"
_HDRS         = {"User-Agent": "WegeRadar/1.0 (kontakt@example.com)"}
_GEOCACHE: Dict[Tuple[float, float], Dict[str, str]] = {}


def _extract_name(js: dict) -> str:
    """Versuche, einen treffenden Ortsnamen aus dem Nominatim-JSON zu holen."""
    if js.get("name"):
        return js["name"]

    addr = js.get("address", {})
    for key in ("amenity", "attraction", "leisure", "shop", "tourism"):
        if addr.get(key):
            return addr[key]
    return ""


def reverse_geocode(lat: float, lon: float) -> Dict[str, str]:
    """
    Liefert ein kleines Adress-Dict für die Koordinate.
    Greift erst in den Cache, dann – geregelt – zu Nominatim.
    """
    key = (round(lat, 5), round(lon, 5))   # 1 m Genauigkeit ≈ 5 Decimales
    if key in _GEOCACHE:
        return _GEOCACHE[key]

    result = {k: "" for k in ("name", "road", "house_number", "postcode", "city")}
    try:
        r = requests.get(
            _NOMINATIM,
            params={
                "format": "jsonv2",
                "lat": lat,
                "lon": lon,
                "zoom": 18,
                "addressdetails": 1,
            },
            headers=_HDRS,
            timeout=5,
        )
        if r.status_code == 200:
            js = r.json()
            addr = js.get("address", {})
            result.update(
                {
                    "name": _extract_name(js),
                    "road": addr.get("road")
                    or addr.get("pedestrian")
                    or addr.get("footway")
                    or "",
                    "house_number": addr.get("house_number", ""),
                    "postcode": addr.get("postcode", ""),
                    "city": addr.get("city")
                    or addr.get("town")
                    or addr.get("village")
                    or addr.get("hamlet")
                    or "",
                }
            )
    except Exception:
        pass  # Netzwerkfehler ignorieren

    _GEOCACHE[key] = result
    time.sleep(NOMINATIM_SLEEP_SEC)
    return result


def _same_address(a: dict, b: dict) -> bool:
    """True, wenn alle Adressfelder exakt gleich sind."""
    for fld in ("name", "road", "house_number", "postcode", "city"):
        if a.get(fld, "") != b.get(fld, ""):
            return False
    return True


# --------------------------------------------------------------------------- #
# Dateiauswahl-Dialog (GUI-Hilfsfunktion)
# --------------------------------------------------------------------------- #
def show_date_dialog(master, gpx_folder: str, last: str, first: str) -> str | None:
    """
    Zeigt einen kleinen Dialog: Für die Person (Nachname, Vorname) existieren
    evtl. mehrere Dateien – der/die Nutzer*in wählt ein Datum.
    """
    prefix = f"{last}_{first}_"
    files = [
        f
        for f in os.listdir(gpx_folder)
        if f.startswith(prefix) and f.lower().endswith(".gpx")
    ]
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
    sel: dict[str | None] = {"d": None}

    def choose(d: str):
        sel["d"] = d
        dlg.destroy()

    for d in sorted(date_map):
        tk.Button(dlg, text=d, width=22, command=lambda d=d: choose(d)).pack(pady=2)

    dlg.update_idletasks()
    w, h = dlg.winfo_width() + 40, dlg.winfo_height() + 20
    x = (dlg.winfo_screenwidth() - w) // 2
    y = (dlg.winfo_screenheight() - h) // 2
    dlg.geometry(f"{w}x{h}+{x}+{y}")
    dlg.wait_window()
    return sel["d"]


# --------------------------------------------------------------------------- #
# Hauptfunktion – Analyse und Aufbereitung der Stops
# --------------------------------------------------------------------------- #
def analyze_gpx(
    gpx_folder: str,
    last: str,
    first: str,
    date: str,
    dist_m: int = DIST_THRESHOLD_M,
    min_stop_sec: int = MIN_STOP_DURATION_SEC,
) -> List[dict]:
    """
    Haupteinstieg: Liest die Datei <last>_<first>_<date>.gpx ein,
    erzeugt Aufenthaltsorte, verschmilzt sie und ergänzt
    Distanz / Geschwindigkeit zur jeweils folgenden Etappe.
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
        for pt in seg.points
        if pt.time
    ]
    if not pts:
        return []

    pts.sort(key=lambda x: x[0])

    # --------------------------------------------------------------------- #
    # 1. Stop-Cluster erkennen (Radius DIST_THRESHOLD_M, Dauer >= min_stop)
    # --------------------------------------------------------------------- #
    clusters: List[Tuple[float, float, datetime, datetime]] = []
    i, n = 0, len(pts)
    while i < n:
        j = i + 1
        # solange Punkte im Umkreis
        while j < n and haversine(
            pts[i][1], pts[i][2], pts[j][1], pts[j][2]
        ) <= dist_m:
            j += 1

        duration = (pts[j - 1][0] - pts[i][0]).total_seconds()
        if duration >= min_stop_sec:
            lat = sum(p[1] for p in pts[i:j]) / (j - i)
            lon = sum(p[2] for p in pts[i:j]) / (j - i)
            clusters.append((lat, lon, pts[i][0], pts[j - 1][0]))
            i = j
        else:
            i += 1

    # Immer Start- und End-Punkt mit aufnehmen
    coords: List[Tuple[float, float, datetime, datetime]] = [
        (pts[0][1], pts[0][2], pts[0][0], pts[0][0]),
        *clusters,
        (pts[-1][1], pts[-1][2], pts[-1][0], pts[-1][0]),
    ]

    # --------------------------------------------------------------------- #
    # 2. Stops, die in derselben Minute ineinander übergehen, verschmelzen
    # --------------------------------------------------------------------- #
    merged: List[Tuple[float, float, datetime, datetime]] = []
    for lat, lon, s_dt, e_dt in coords:
        if (
            merged
            and merged[-1][3].strftime("%Y-%m-%d %H:%M")
            == s_dt.strftime("%Y-%m-%d %H:%M")
        ):
            # End-Zeit des letzten Stops erweitern
            merged[-1] = (merged[-1][0], merged[-1][1], merged[-1][2], e_dt)
        else:
            merged.append((lat, lon, s_dt, e_dt))

    # --------------------------------------------------------------------- #
    # 3. Adressen holen
    # --------------------------------------------------------------------- #
    enriched: List[dict] = []
    for lat, lon, s_dt, e_dt in merged:
        addr = reverse_geocode(lat, lon)
        addr.update(
            {
                "lat": lat,
                "lon": lon,
                "start_dt": s_dt.astimezone(BERLIN),
                "end_dt": e_dt.astimezone(BERLIN),
            }
        )
        enriched.append(addr)

    # --------------------------------------------------------------------- #
    # 4. Adress-/Distanz-Merging nach Punkt 6 der Beschreibung
    # --------------------------------------------------------------------- #
    final: List[dict] = []
    for item in enriched:
        if not final:
            final.append(item)
            continue

        prev = final[-1]
        gap_sec = (item["start_dt"] - prev["end_dt"]).total_seconds()

        same_addr = _same_address(prev, item)
        close_enough = (
            haversine(prev["lat"], prev["lon"], item["lat"], item["lon"]) <= MERGE_DIST_M
        )

        if gap_sec <= MAX_GAP_SEC_SAME_ADDR and (same_addr or close_enough):
            # Zusammenlegen: End-Zeit verlängern
            prev["end_dt"] = item["end_dt"]
        else:
            final.append(item)

    # --------------------------------------------------------------------- #
    # 5. Distanz & Tempo zwischen je zwei Stops bestimmen
    # --------------------------------------------------------------------- #
    for idx in range(len(final) - 1):
        end_prev_utc   = final[idx]["end_dt"].astimezone(timezone.utc)
        start_next_utc = final[idx + 1]["start_dt"].astimezone(timezone.utc)

        # Distanz entlang der GPX-Spur akkumulieren
        dist_m_real = 0.0
        started = False
        for i in range(len(pts) - 1):
            t0, lat0, lon0 = pts[i]
            t1, lat1, lon1 = pts[i + 1]

            if t1 < end_prev_utc:
                continue
            if not started and t0 >= end_prev_utc:
                started = True
            if started:
                dist_m_real += haversine(lat0, lon0, lat1, lon1)
            if started and t1 >= start_next_utc:
                break

        dist_km = round(dist_m_real / 1000.0, 2)
        time_h = (start_next_utc - end_prev_utc).total_seconds() / 3600
        speed_kmh = round(dist_km / time_h, 2) if time_h > 0 else None

        final[idx]["next_dist_km_real"] = dist_km
        if speed_kmh is not None:
            final[idx]["next_speed_kmh_real"] = speed_kmh

    return final