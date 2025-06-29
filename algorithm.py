# algorithm.py
from __future__ import annotations
import os
import time
from datetime import datetime, timezone
from functools import lru_cache
from math import radians, cos, sin, asin, sqrt
from typing import Dict, List, Tuple, Any

import gpxpy
import requests

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from datetime import timezone as ZoneInfo  # type: ignore
    ZoneInfo = lambda tz: timezone.utc         # type: ignore

BERLIN = ZoneInfo("Europe/Berlin")

# Konfiguration
OSRM_URL = os.getenv("OSRM_URL", "http://localhost:5000")
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
USER_AGENT = "WegeRadar/1.0 (kontakt@example.com)"

# Caches
_WAY_TAG_CACHE: Dict[int, Dict[str, str]] = {}

# Geschwindigkeit/Bandbreiten
_SPEED_BANDS = {
    "Zu Fuß":       (0,  7),
    "Fahrrad":      (7,  30),
    "Auto":         (24, 300),
    "Bus":          (15, 90),
    "Straßenbahn":  (15, 90),
    "Zug":          (40, 250),
}
_MARGIN_KMH = 1.0

# OSM Tag-Filter
_TAG_FILTERS = {
    "Bus":         {"highway": ["busway", "bus_guideway"]},
    "Straßenbahn": {"railway": ["tram"]},
    "Zug":         {"railway": ["rail", "light_rail", "subway"]},
}

# Hilfsfunktionen

def _speed_score(speed_kmh: float, mode: str) -> float:
    lo, hi = _SPEED_BANDS[mode]
    if speed_kmh <= lo - _MARGIN_KMH or speed_kmh >= hi + _MARGIN_KMH:
        return 0.0
    if lo <= speed_kmh <= hi:
        return 1.0
    if lo - _MARGIN_KMH < speed_kmh < lo:
        return (speed_kmh - (lo - _MARGIN_KMH)) / _MARGIN_KMH
    return ((hi + _MARGIN_KMH) - speed_kmh) / _MARGIN_KMH


def _foot_distance_factor(dist_km: float) -> float:
    if dist_km <= 1.0:
        return 1.0
    if dist_km >= 4.0:
        return 0.0
    return (4.0 - dist_km) / 3.0


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    return 6_371_000 * 2 * asin(sqrt(a))

# Map-Matching via OSRM

# Vorverarbeitung-Dialog
import tkinter as _tk
import tkinter.simpledialog as _sd

def show_date_dialog(master, gpx_path: str, last: str, first: str) -> str:
    """
    Öffnet einen einfachen Eingabe-Dialog, um das Datum für die GPX-Analyse auszuwählen.
    master: TK-Root-Fenster;
    gpx_path: Pfad zum GPX-Ordner;
    last, first: mögliche Datumswerte als Strings.
    Gibt das eingegebene Datum als String zurück.
    """
    prompt = f"Wähle ein Datum zwischen {first} und {last}:"
    return _sd.askstring("Datum auswählen", prompt, parent=master)  

# analyze_gpx: Aufruf unverändert, nutzt classify_main_mode für jedes Segment, nutzt classify_main_mode für jedes Segment
# app.py und benutzeroberfläche.py bleiben unverändert
