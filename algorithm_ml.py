from __future__ import annotations
"""algorithm_ml.py
====================

Offline‑fähige Verkehrsmittel‑Klassifikation in zwei Stufen
----------------------------------------------------------
1. **Feature‑Extraktion** aus einer GPX‑Seg­ment­spur (keine OSM‑Daten nötig)
2. **Entscheidung**
   • Falls ein trainiertes Modell (``joblib``‑Dump) vorhanden ist, werden dessen
     Wahrscheinlichkeiten verwendet.
   • Fallback ist ein regelbasierter Score, der bereits deutlich präziser ist
     als der bisherige Geschwindigkeits‑Heuristik.

Die zentrale API‑Funktion ist

    classify_transport(times, lats, lons) -> dict[str, float]

Sie liefert z. B. ``{"Zu Fuß": 0.02, "Fahrrad": 0.83, "Bus": 0.1,
"Auto": 0.03, "Straßenbahn": 0.02, "Zug": 0.0, "best": "Fahrrad"}``

Abhängigkeiten::

    numpy>=1.24
    joblib>=1.4   # nur falls ML‑Modell genutzt wird

"""

from datetime import datetime
from math import atan2, cos, radians, sin
from typing import Dict, List

import numpy as np

try:
    import joblib  # optional
except ImportError:  # pragma: no cover – Model‑Path bleibt dann einfach None
    joblib = None  # type: ignore

# ---------------------------------------------------------------------------
# Geo‑Hilfsfunktionen
# ---------------------------------------------------------------------------
_EARTH_R = 6_371_000  # m


def _haversine_vec(lat1: np.ndarray, lon1: np.ndarray,
                   lat2: np.ndarray, lon2: np.ndarray) -> np.ndarray:
    """Vektorisierte Haversine‑Distanz (m) für gleich lange Arrays."""
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    return 2 * _EARTH_R * np.arcsin(np.sqrt(a))


# ---------------------------------------------------------------------------
# Feature Engineering
# ---------------------------------------------------------------------------

def _segment_features(times: List[datetime],
                      lats: List[float],
                      lons: List[float]) -> np.ndarray:
    """Extrahiert 9 robuste Motion‑Features aus einem Segment."""
    if len(times) < 3:  # zu kurz, Dummy‑Features zurückgeben
        return np.zeros(9)

    t = np.asarray([ts.timestamp() for ts in times], dtype=float)
    lat = np.radians(np.asarray(lats, dtype=float))
    lon = np.radians(np.asarray(lons, dtype=float))

    # Distanz & Tempo ‑‑----------------------------------------
    dist = _haversine_vec(lat[:-1], lon[:-1], lat[1:], lon[1:])  # m
    dt = np.diff(t)
    dt[dt == 0] = 1e-3  # falls GPS denselben Zeitstempel liefert
    speed = dist / dt  # m/s
    speed_kmh = speed * 3.6

    # Beschleunigung & Jerk -----------------------------------
    accel = np.diff(speed) / dt[1:]
    jerk = np.diff(accel) / dt[2:] if len(dt) > 2 else np.zeros(1)

    # Richtungsänderung ---------------------------------------
    y = np.sin(lon[1:] - lon[:-1]) * np.cos(lat[1:])
    x = (np.cos(lat[:-1]) * np.sin(lat[1:]) -
         np.sin(lat[:-1]) * np.cos(lat[1:]) * np.cos(lon[1:] - lon[:-1]))
    bearing = (np.degrees(np.arctan2(y, x)) + 360) % 360
    hdg_change = np.minimum(np.abs(np.diff(bearing)), 360 - np.abs(np.diff(bearing)))

    # Aggregation in 9 Kennzahlen ------------------------------
    def _p(arr: np.ndarray, q: float) -> float:
        return float(np.percentile(arr, q)) if arr.size else 0.0

    feat = np.array([
        float(speed_kmh.mean()),          # 0 Mitteltempo
        _p(speed_kmh, 95),               # 1 95‑Perzentil Geschwindigkeit
        float(speed_kmh.std()),          # 2 Std‑Abw Tempo
        float(accel.mean() if accel.size else 0.0),   # 3 mittl. Beschl.
        float(accel.std() if accel.size else 0.0),    # 4 Std‑Abw Beschl.
        float(np.sqrt((jerk**2).mean()) if jerk.size else 0.0),  # 5 jerk RMS
        float(hdg_change.mean() if hdg_change.size else 0.0),    # 6 mittl ΔHeading
        float(hdg_change.std() if hdg_change.size else 0.0),     # 7 Std ΔHeading
        float(((speed_kmh < 1).sum()) / (dist.sum() / 1_000 + 1e-6)),  # 8 Stop‑Freq/km
    ])
    return feat


# ---------------------------------------------------------------------------
# Regel‑Fallback (wenn kein ML‑Modell vorliegt)
# ---------------------------------------------------------------------------

_MODES = ("Zu Fuß", "Fahrrad", "Bus", "Auto", "Straßenbahn", "Zug")


def _rule_scores(feat: np.ndarray) -> Dict[str, float]:
    v_mean, v95, v_std, a_mean, a_std, jerk_rms, hdg_mean, hdg_std, stop_freq = feat
    s: Dict[str, float] = {m: 0.0 for m in _MODES}

    # grobe Heuristik mit mehrdimensionalen Schwellwerten
    if v95 < 7:
        s["Zu Fuß"] = 0.9
        s["Fahrrad"] = 0.1

    elif v95 < 25:
        s["Fahrrad"] = 0.8
        s["Auto"] = 0.1
        s["Zu Fuß"] = 0.1

    elif hdg_std < 5 and v_mean > 40:  # quasi geradeaus, schnell
        if v_mean > 60:
            s["Zug"] = 0.8
            s["Straßenbahn"] = 0.15
        else:
            s["Straßenbahn"] = 0.6
            s["Zug"] = 0.25
        s["Auto"] = 0.05

    elif jerk_rms > 1.5 and stop_freq > 1.5:  # ruckig + viele Halte
        s["Bus"] = 0.7
        s["Auto"] = 0.2
        s["Straßenbahn"] = 0.1

    else:  # default: motorisiert, Few Halte → Auto
        s["Auto"] = 0.8
        s["Bus"] = 0.15
        s["Fahrrad"] = 0.05

    # Normalisieren -------------------------------------------
    tot = sum(s.values()) or 1.0
    for k in s:
        s[k] /= tot
    return s


# ---------------------------------------------------------------------------
# Klassen‑Interface
# ---------------------------------------------------------------------------

class _ModeClassifier:
    """Singleton‑Klassifikator (lädt optional ein joblib‑Modell)."""

    def __init__(self, model_path: str | None = None):
        self._clf = None
        if model_path and joblib:
            try:
                self._clf = joblib.load(model_path)
            except Exception:
                self._clf = None

    def classify(self, times: List[datetime], lats: List[float], lons: List[float]) -> Dict[str, float]:
        feat = _segment_features(times, lats, lons)
        if self._clf is not None:
            proba = self._clf.predict_proba(feat.reshape(1, -1))[0]
            classes = self._clf.classes_
            scores = {m: float(p) for m, p in zip(classes, proba)}
        else:
            scores = _rule_scores(feat)
        scores["best"] = max(scores, key=scores.get)
        return scores


# Modul‑weite Instanz -----------------------------------------
_default = _ModeClassifier()


def classify_transport(times: List[datetime],
                       lats: List[float],
                       lons: List[float]) -> Dict[str, float]:
    """Öffentliche API‑Funktion – siehe Modul‑Docstring."""
    return _default.classify(times, lats, lons)