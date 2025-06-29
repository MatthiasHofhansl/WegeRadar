WegeRadar ist ein Tool zur Analyse von GPX-Tracks und Visualisierung von Stopps und Wegabschnitten mithilfe von OpenStreetMap-Daten.

## Features

* GPX-Analyse: Erkennung von Stopps (Clusters) und Berechnung von Distanzen sowie Durchschnittsgeschwindigkeiten und Verkehrsmitteln zwischen den Stopps
* Reverse-Geocoding: Abfrage von Adressdaten über Nominatim (OSM) für jeden Stopppunkt
* Verkehrsmittel-Klassifizierung: Bestimmung des wahrscheinlichsten Verkehrsmittels basierend auf Geschwindigkeit und optionaler OSM-GeoJSON-Daten
* Interaktive GUI: Auswahl von GPX-Ordnern und GeoJSON-Dateien; Anzeige von Teilnehmern und detaillierten Analyseergebnissen 
* Plattformübergreifend: Rein in Python und Tkinter implementiert

## Installation

1. Repository klonen

2. Abhängigkeiten installieren:

   pip install gpxpy requests geopandas shapely

Hinweis: Tkinter ist in der Regel bei Python-Standardinstallationen enthalten. Für Windows ggf. das "tk-tools"-Paket nachinstallieren.

## Usage

1. GPX- und GeoJSON-Daten bereitstellen:

   * Lege alle GPX-Dateien im Format `Nachname_Vorname_Datum.gpx` in einen Ordner.
   * Sammle für jedes Verkehrsmittel (Auto, Fahrrad, Bus, etc.) GeoJSON-Dateien, die Straßennetze deines Gebiets abbilden.

2. App starten:

   ```bash
   python app.py
   ```

3. In der GUI:

   * Wähle den Ordner mit den GPX-Dateien aus.
   * Wähle für jedes Verkehrsmittel eine GeoJSON-Datei aus.
   * Klicke auf Start.
   * Wähle ggf. das Datum für die Analyse aus.
   * Klicke auf einen Teilnehmer-Namen, um Stopps und Wege anzuzeigen.

## Projektstruktur

```
├── algorithm.py            # Kernlogik zur Analyse und Klassifizierung fileciteturn0file0
├── benutzeroberfläche.py   # GUI-Definition und Interaktion    fileciteturn0file2
├── app.py                  # Einstiegspunkt der Anwendung      fileciteturn0file1
├── requirements.txt        # Python-Abhängigkeiten
└── README.md               # Dieses Dokument
```