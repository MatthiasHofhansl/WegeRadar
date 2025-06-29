# benutzeroberfläche.py
from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import importlib

import algorithm

APP_NAME = "WegeRadar"


class WegeRadar:
    def __init__(self, master: tk.Tk) -> None:
        self.master = master
        master.title(APP_NAME)

        win_w, win_h = 500, 330
        sw, sh = master.winfo_screenwidth(), master.winfo_screenheight()
        master.geometry(f"{win_w}x{win_h}+{(sw - win_w) // 2}+{(sh - win_h) // 2}")
        master.resizable(True, True)

        # Pfad zum GPX-Ordner
        self.gpx_path: str | None = None

        # Hier speichern wir die 6 ausgewählten GeoJSON-Dateien eindeutig:
        # { "Auto": <Pfad>, "Zu Fuß": <Pfad>, "Fahrrad": <Pfad>, "Bus": <Pfad>, "Straßenbahn": <Pfad>, "Zug": <Pfad> }
        self.osm_selections: dict[str, str | None] = {
            "Auto": None,
            "Zu Fuß": None,
            "Fahrrad": None,
            "Bus": None,
            "Straßenbahn": None,
            "Zug": None,
        }

        self.static_frame: tk.Frame | None = None
        self.list_canvas: tk.Canvas | None = None
        self.list_inner: tk.Frame | None = None
        self.list_scrollbar: tk.Scrollbar | None = None

        self.setup_ui()

    def setup_ui(self) -> None:
        tk.Label(
            self.master, text="Herzlich Willkommen!", font=("Arial", 24, "bold")
        ).pack(pady=(10, 3))

        # GPX-Ordner auswählen
        gpx_frame = tk.Frame(self.master)
        gpx_frame.pack(fill="x", padx=20, pady=(5, 0), anchor="w")

        tk.Label(
            gpx_frame,
            text="Bitte lade hier den Ordner mit den GPX-Dateien hoch:",
            font=("Arial", 12),
        ).grid(row=0, column=0, sticky="w")

        row = tk.Frame(gpx_frame)
        row.grid(row=1, column=0, sticky="ew", pady=2)
        row.grid_columnconfigure(1, weight=1)

        tk.Button(row, text="Auswählen", width=12, command=self.select_gpx).grid(
            row=0, column=0, sticky="w"
        )

        self.gpx_label = tk.Label(
            row,
            text="Keinen Ordner ausgewählt.",
            font=("Arial", 12),
            anchor="center"
        )
        self.gpx_label.grid(row=0, column=1, sticky="ew")

        # Für GeoJSON-Dateien ist jetzt ein eigener Button, der ein neues Fenster öffnet
        osm_frame = tk.Frame(self.master)
        osm_frame.pack(fill="x", padx=20, pady=(20, 0), anchor="center")

        tk.Button(
            osm_frame,
            text="GeoJSON-Dateien auswählen",
            width=25,
            command=self.select_osm_dialog
        ).pack(pady=(2, 0))

        self.osm_label = tk.Label(
            osm_frame,
            text="Keine GeoJSON-Dateien ausgewählt.",
            font=("Arial", 12),
            anchor="center"
        )
        self.osm_label.pack()

        # "Start"-Button
        tk.Button(
            self.master,
            text="Start",
            command=self.start_action,
            font=("Arial", 24, "bold"),
            height=2,
        ).pack(side="bottom", fill="x", pady=(2, 0))

    def select_gpx(self) -> None:
        """Wählt einen Ordner mit GPX-Dateien aus."""
        p = filedialog.askdirectory(title="Ordner mit den GPX-Dateien auswählen")
        if p:
            self.gpx_path = p
            self.gpx_label.config(text=os.path.basename(p))

    def select_osm_dialog(self) -> None:
        """
        Öffnet ein neues Fenster, in dem für jedes Verkehrsmittel (Auto, Zu Fuß usw.)
        einzeln eine GeoJSON-Datei ausgewählt wird.
        
        Dabei wird die Höhe des Fensters nachträglich so vergrößert, dass alle Buttons
        plus der OK-Button sichtbar werden. Die Breite und die zentrierte Position
        auf dem Bildschirm bleiben erhalten.
        """

        # Erstellt ein Toplevel:
        dlg = tk.Toplevel(self.master)
        dlg.title("GeoJSON-Auswahl")
        dlg.resizable(False, False)
        dlg.transient(self.master)
        dlg.grab_set()

        # Der folgende Block sorgt in deinem Original-Code dafür, dass das Dialog-Fenster
        # exakt die gleiche Größe und Position wie das Hauptfenster einnimmt.
        # Wir übernehmen hier dieselbe Breite (w) und zentrieren wieder am Bildschirm,
        # ändern aber die Höhe so, dass genügend Platz für Buttons und OK-Button ist.

        self.master.update_idletasks()
        # Größe des Hauptfensters
        w = self.master.winfo_width()

        # Temporär setzen wir eine erste Geometrie, damit dlg seine Inhalte berechnen kann
        # (z.B. winfo_reqheight).
        # Wir setzen hier erstmal eine Höhe = Höhe des Hauptfensters, nur als Start-Wert.
        h_temp = self.master.winfo_height()

        # Bildschirmbreite und -höhe
        sw = self.master.winfo_screenwidth()
        sh = self.master.winfo_screenheight()

        # Toplevel zunächst vorläufig zentrieren
        x = (sw - w) // 2
        y = (sh - h_temp) // 2
        dlg.geometry(f"{w}x{h_temp}+{x}+{y}")

        # Überschrift
        label_top = tk.Label(
            dlg,
            text="Bitte wähle hier die GeoJSON-Dateien aus deinem Gebiet aus!",
            font=("Arial", 10, "bold")
        )
        label_top.pack(pady=(15, 10))

        # Frame für die Verkehrsmittel
        modes_frame = tk.Frame(dlg)
        modes_frame.pack(expand=True, fill="both")

        # Für jeden Modus eine Zeile anlegen
        self.osm_entry_labels = {}
        for mode in self.osm_selections:
            row_frame = tk.Frame(modes_frame)
            row_frame.pack(fill="x", pady=5)

            label_mode = tk.Label(row_frame, text=f"{mode}:", font=("Arial", 12))
            label_mode.pack(side="left", padx=20)

            # Label, das den gewählten Pfad anzeigt
            lbl_path = tk.Label(
                row_frame,
                text="Keine Datei ausgewählt",
                font=("Arial", 12),
                anchor="w"
            )
            lbl_path.pack(side="left", padx=10)
            self.osm_entry_labels[mode] = lbl_path

            # Auswählen-Button
            def make_handler(m=mode):
                return lambda: self._choose_osm_file(m)
            btn = tk.Button(row_frame, text="Auswählen", font=("Arial", 12), command=make_handler(mode))
            btn.pack(side="right", padx=20)

        # OK-Button unten zentriert
        btn_ok = tk.Button(
            dlg, text="OK", font=("Arial", 14), width=10,
            command=lambda: self._osm_ok(dlg)
        )
        btn_ok.pack(pady=20)

        # Jetzt schauen wir, wie groß das dlg *wirklich* sein muss,
        # damit alle Buttons und der OK-Button Platz haben.
        dlg.update_idletasks()
        needed_h = dlg.winfo_reqheight()

        # Breite (w) bleibt wie oben ermittelt, wir ändern nur die Höhe, falls nötig:
        final_h = max(h_temp, needed_h)  # so gehen wir sicher, dass es nicht kleiner wird als vorher

        # Jetzt zentrieren wir das Fenster erneut am Bildschirm:
        new_x = (sw - w) // 2
        new_y = (sh - final_h) // 2
        dlg.geometry(f"{w}x{final_h}+{new_x}+{new_y}")

    def _choose_osm_file(self, mode: str) -> None:
        """Öffnet einen Dateidialog, um eine einzelne *.geojson-Datei zu wählen."""
        path = filedialog.askopenfilename(
            title=f"Datei für {mode} auswählen",
            filetypes=[("GeoJSON", "*.geojson"), ("Alle Dateien", "*.*")]
        )
        if path:
            # Pfad merken und Anzeige aktualisieren
            self.osm_selections[mode] = path
            if mode in self.osm_entry_labels:
                basename = os.path.basename(path)
                self.osm_entry_labels[mode].config(text=basename)

    def _osm_ok(self, dlg: tk.Toplevel) -> None:
        """
        Wird aufgerufen, wenn man im OSM-Auswahl-Fenster "OK" drückt.
        Prüft, ob alle 6 Dateien gewählt wurden. Wenn ja, schließt das Fenster.
        """
        missing = [m for m, path in self.osm_selections.items() if not path]
        if missing:
            msg = (
                "Bitte wähle für alle Verkehrsmittel eine GeoJSON-Datei.\n"
                f"Fehlend: {', '.join(missing)}"
            )
            messagebox.showwarning(APP_NAME, msg, parent=dlg)
            return

        # Jetzt ist alles da, Fenster schließen
        dlg.destroy()

        # Aktualisiere Anzeige im Hauptfenster
        texts = []
        for m in self.osm_selections:
            texts.append(f"{m}: {os.path.basename(self.osm_selections[m])}")
        self.osm_label.config(text="\n".join(texts))

    def start_action(self) -> None:
        """
        Wird aufgerufen, wenn man auf "Start" klickt.
        Prüft, ob GPX-Ordner und alle 6 OSM-Dateien gewählt wurden.
        """
        if not self.gpx_path:
            messagebox.showwarning(
                APP_NAME,
                "Bitte wähle einen Ordner mit den GPX-Dateien aus.",
                parent=self.master,
            )
            return

        # Prüfen, ob alle 6 GeoJSON-Files gesetzt sind
        if not all(self.osm_selections.values()):
            messagebox.showwarning(
                APP_NAME,
                "Bitte gib für alle 6 Verkehrsmittel je eine GeoJSON-Datei an.",
                parent=self.master,
            )
            return

        # UI leeren und Hauptansicht aufbauen
        for w in self.master.winfo_children():
            w.destroy()
        self.master.configure(bg="white")
        try:
            self.master.state("zoomed")
        except tk.TclError:
            self.master.attributes("-zoomed", True)

        # Linke Teilnehmerliste
        container = tk.Frame(self.master, bg="white", width=200)
        container.pack(side="left", fill="y")
        canvas_left = tk.Canvas(container, bg="white", width=200, highlightthickness=0)
        scrollbar_left = tk.Scrollbar(
            container, orient="vertical", command=canvas_left.yview
        )
        left_inner = tk.Frame(canvas_left, bg="white")
        left_inner.bind(
            "<Configure>",
            lambda e: canvas_left.configure(scrollregion=canvas_left.bbox("all")),
        )
        canvas_left.create_window((0, 0), window=left_inner, anchor="nw")
        canvas_left.configure(yscrollcommand=scrollbar_left.set)
        canvas_left.pack(side="left", fill="y", expand=True)
        scrollbar_left.pack(side="right", fill="y")
        tk.Frame(self.master, bg="black", width=2).pack(side="left", fill="y")

        # Rechte statische Kopfzeile + scrollbare Liste
        right_frame = tk.Frame(self.master, bg="white")
        right_frame.pack(side="left", fill="both", expand=True)

        self.static_frame = tk.Frame(right_frame, bg="white")
        self.static_frame.pack(side="top", fill="x")

        list_container = tk.Frame(right_frame, bg="white")
        list_container.pack(side="top", fill="both", expand=True)

        self.list_canvas = tk.Canvas(list_container, bg="white", highlightthickness=0)
        self.list_scrollbar = tk.Scrollbar(
            list_container, orient="vertical", command=self.list_canvas.yview
        )
        self.list_inner = tk.Frame(self.list_canvas, bg="white")
        self.list_inner.bind(
            "<Configure>",
            lambda e: self.list_canvas.configure(scrollregion=self.list_canvas.bbox("all")),
        )
        self.list_canvas.create_window((0, 0), window=self.list_inner, anchor="nw")
        self.list_canvas.configure(yscrollcommand=self.list_scrollbar.set)
        self.list_canvas.pack(side="left", fill="both", expand=True)
        self.list_scrollbar.pack(side="right", fill="y")

        tk.Label(
            left_inner,
            text="Teilnehmerinnen\nund Teilnehmer",
            font=("Arial", 14, "bold"),
            bg="white",
            justify="center",
        ).pack(pady=(10, 5))

        files = [f for f in os.listdir(self.gpx_path) if f.lower().endswith(".gpx")]
        # Grob: "<Nachname>_<Vorname>_<Datum>.gpx"
        names = sorted(
            {
                (f.split("_")[0], f.split("_")[1])
                for f in files
                if len(f.split("_")) >= 3
            },
            key=lambda x: x[0],
        )

        for last, first in names:
            disp = f"{last}, {first}"
            short = disp if len(disp) <= 20 else disp[:17] + "…"
            lbl = tk.Label(
                left_inner,
                text=short,
                font=("Arial", 12),
                bg="white",
                anchor="w",
                width=20,
            )
            lbl.pack(fill="x", padx=10, pady=2)
            lbl.bind("<Enter>", lambda e, l=lbl: l.config(bg="#e0e0e0"))
            lbl.bind("<Leave>", lambda e, l=lbl: l.config(bg="white"))
            lbl.bind("<Button-1>", lambda e, l=last, f=first: self.on_name_click(l, f))

    def on_name_click(self, last: str, first: str) -> None:
        """Wird aufgerufen, wenn man auf einen Namen in der Teilnehmerliste klickt und die Analyse startet."""
        for w in self.static_frame.winfo_children():
            w.destroy()
        for w in self.list_inner.winfo_children():
            w.destroy()

        head = tk.Frame(self.static_frame, bg="white")
        head.pack(fill="x")
        tk.Label(
            head,
            text=f"Teilnehmer(in): {last}, {first}",
            font=("Arial", 14, "bold"),
            bg="white",
            anchor="w",
        ).pack(side="left", padx=10, pady=5)

        tk.Button(
            head,
            text="✖",
            font=("Arial", 12, "bold"),
            fg="red",
            bg="white",
            bd=0,
            command=lambda: [
                child.destroy()
                for frame in (self.static_frame, self.list_inner)
                for child in frame.winfo_children()
            ],
        ).pack(side="right", padx=10, pady=5)

        # Algorithmus neu laden
        importlib.reload(algorithm)

        # OSM-Daten laden
        algorithm.load_osm_data(self.osm_selections)

        # Dialog zum Datum
        date = algorithm.show_date_dialog(self.master, self.gpx_path, last, first)
        if not date:
            return

        # Loader-Fenster
        loader = tk.Toplevel(self.master)
        loader.title("Bitte warten…")
        loader.resizable(False, False)
        w, h = 300, 80
        self.master.update_idletasks()
        mx, my = self.master.winfo_rootx(), self.master.winfo_rooty()
        mw, mh = self.master.winfo_width(), self.master.winfo_height()
        loader.geometry(f"{w}x{h}+{mx + (mw - w) // 2}+{my + (mh - h) // 2}")
        loader.transient(self.master)
        loader.grab_set()

        tk.Label(loader, text="Daten werden geladen…", font=("Arial", 12)).pack(pady=10)
        prog = ttk.Progressbar(loader, mode="indeterminate")
        prog.pack(fill="x", padx=20, pady=(0, 10))
        prog.start()

        def run() -> None:
            places = algorithm.analyze_gpx(self.gpx_path, last, first, date)
            self.master.after(0, lambda: self.show_stops(loader, prog, date, places))

        threading.Thread(target=run, daemon=True).start()

    def show_stops(
        self,
        loader: tk.Toplevel,
        prog: ttk.Progressbar,
        date: str,
        places: list[dict],
    ) -> None:
        """Zeigt die ermittelten Orte/Wegabschnitte der gewählten Person + Datum an."""
        prog.stop()
        loader.destroy()

        tk.Label(
            self.static_frame,
            text=f"Datum der GPX-Datei: {date}",
            font=("Arial", 14, "bold"),
            bg="white",
            anchor="w",
        ).pack(fill="x", padx=10, pady=(2, 1))

        tk.Frame(self.static_frame, bg="black", height=2).pack(fill="x", pady=(0, 10))

        if not places:
            tk.Label(
                self.list_inner,
                text="Keine Orte gefunden.",
                font=("Arial", 12),
                bg="white",
                anchor="w",
            ).pack(fill="x", padx=20, pady=5)
            return

        from math import radians, cos, sin, asin, sqrt

        def _haversine_km(lat1, lon1, lat2, lon2):
            lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
            dlat, dlon = lat2 - lat1, lon2 - lon1
            a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
            return 6371.0 * 2 * asin(sqrt(a))

        for idx, p in enumerate(places, 1):
            start = p["start_dt"].strftime("%H:%M")
            end = p["end_dt"].strftime("%H:%M")
            time_span = f"{start} Uhr – {end} Uhr"

            name = p.get("name", "").strip()
            road = p.get("road", "").strip()
            house = p.get("house_number", "").strip()
            street = " ".join(x for x in (road, house) if x)

            pc = p.get("postcode", "").strip()
            city = p.get("city", "").strip()
            pc_city = ", ".join(x for x in (pc, city) if x)

            parts: list[str] = [time_span]
            if name:
                parts.append(name)
            addr_line = ", ".join(x for x in (street, pc_city) if x)
            if addr_line:
                parts.append(addr_line)

            ort_text = f"Ort {idx} │ " + " │ ".join(parts)
            tk.Label(
                self.list_inner,
                text=ort_text,
                font=("Arial", 12),
                bg="white",
                anchor="w",
                wraplength=1000,
            ).pack(fill="x", padx=20, pady=5)

            if idx < len(places):
                nxt = places[idx]
                dist_km = p.get("next_dist_km_real")
                speed_kmh = p.get("next_speed_kmh_real")

                if dist_km is None:
                    dist_km = _haversine_km(p["lat"], p["lon"], nxt["lat"], nxt["lon"])
                duration_sec = (nxt["start_dt"] - p["end_dt"]).total_seconds()
                d_h = int(duration_sec // 3600)
                d_m = int((duration_sec % 3600) // 60)
                duration_str = f"{d_h}:{d_m:02d} h"

                if speed_kmh is None:
                    hours = duration_sec / 3600
                    speed_kmh = dist_km / hours if hours > 0 else 0.0

                prefix = f"Weg {idx} │ "
                line1 = (
                    f"{prefix}Dauer: {duration_str}; "
                    f"Distanz: {dist_km:.2f} km; "
                    f"Durchschnittliche Geschwindigkeit: {speed_kmh:.2f} km/h"
                )

                tk.Label(
                    self.list_inner,
                    text=line1,
                    font=("Arial", 11, "italic"),
                    bg="white",
                    anchor="w",
                ).pack(fill="x", padx=40, pady=(0, 1))

                mode_rank = p.get("next_mode_rank")
                if mode_rank:
                    rank_items = sorted(
                        [(m, mode_rank[m]) for m in mode_rank if m != "best"],
                        key=lambda x: x[1],
                        reverse=True,
                    )
                    rank_str = " │ ".join(f"{m} {s*100:.0f} %" for m, s in rank_items)
                    line2 = f"Verkehrsmittel: {rank_str}"

                    tk.Label(
                        self.list_inner,
                        text=line2,
                        font=("Arial", 11, "italic"),
                        bg="white",
                        anchor="w",
                    ).pack(fill="x", padx=40, pady=(0, 5))