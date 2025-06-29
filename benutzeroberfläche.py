"""
benutzeroberfläche.py
=====================

Tk-Oberfläche für WegeRadar.

Neue Funktionen
---------------
• Beim ersten Klick auf „Start“ erscheint ein modales Dialogfenster:
    »Zur Verbesserung der Ladezeit müssen Teile des OpenStreetMap-Netzes
     heruntergeladen werden. Bitte wähle einen Dateispeicherort aus.«
  – Schaltfläche „Speichern unter …“  
  – Fortschritts­balken während des Downloads  
  – 50-km-Puffer um alle GPX-Punkte, um das Netz so klein wie möglich zu halten
• Das gewählte GeoPackage wird gespeichert / geladen und bei Bedarf
  nach Rückfrage überschrieben.
• Alle Über-Pass-Abfragen entfallen, sobald das Netz vorhanden ist.
• Einrückungen in den Weg-Zeilen sind zentral über PAD_INNER eingestellt.
"""

from __future__ import annotations

import os
import threading
import tkinter as tk
from datetime import timezone, datetime
from math import radians, cos, sin, asin, sqrt
from tkinter import filedialog, messagebox, ttk

import gpxpy
import importlib

import algorithm

APP_NAME = "WegeRadar"
OSM_DEFAULT_NAME = "osm_net.gpkg"
PAD_INNER = 40  # linker Einzug für Weg-Zeilen


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Großkreis-Distanz in km."""
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371.0 * 2 * asin(sqrt(a))


class WegeRadar:
    # --------------------------------------------------------------------- #
    def __init__(self, master: tk.Tk) -> None:
        self.master = master
        master.title(APP_NAME)

        win_w, win_h = 500, 330
        sw, sh = master.winfo_screenwidth(), master.winfo_screenheight()
        master.geometry(f"{win_w}x{win_h}+{(sw - win_w) // 2}+{(sh - win_h) // 2}")
        master.resizable(True, True)

        self.gpx_path: str | None = None
        self.osm_path: str | None = None

        self.static_frame: tk.Frame | None = None
        self.list_inner: tk.Frame | None = None

        self.setup_ui()

    # ------------------------------------------------------------------ UI
    def setup_ui(self) -> None:
        tk.Label(
            self.master, text="Herzlich Willkommen!", font=("Arial", 24, "bold")
        ).pack(pady=(10, 3))

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
            row, text="Keinen Ordner ausgewählt.", font=("Arial", 12), anchor="center"
        )
        self.gpx_label.grid(row=0, column=1, sticky="ew")

        tk.Button(
            self.master,
            text="Start",
            command=self.start_action,
            font=("Arial", 24, "bold"),
            height=2,
        ).pack(side="bottom", fill="x", pady=(2, 0))

    # ------------------------------------------------ Ordnerauswahl GPX
    def select_gpx(self) -> None:
        p = filedialog.askdirectory(title="Ordner mit den GPX-Dateien auswählen")
        if p:
            self.gpx_path = p
            self.gpx_label.config(text=os.path.basename(p))

    # ------------------------------------------------ Haupt-Action Start
    def start_action(self) -> None:
        if not self.gpx_path:
            messagebox.showwarning(APP_NAME, "Bitte Ordner wählen.", parent=self.master)
            return

        bbox = self._compute_gpx_bbox(self.gpx_path)
        if not bbox:
            messagebox.showerror(
                APP_NAME, "Keine gültigen GPX-Dateien gefunden.", parent=self.master
            )
            return

        self._show_osm_dialog(bbox)

    # ---------------------------------------------- BBox aus allen GPX
    def _compute_gpx_bbox(self, folder: str) -> tuple[float, float, float, float] | None:
        n, s, e, w = -90.0, 90.0, -180.0, 180.0
        found = False
        for fn in os.listdir(folder):
            if not fn.lower().endswith(".gpx"):
                continue
            try:
                with open(os.path.join(folder, fn), encoding="utf-8") as f:
                    g = gpxpy.parse(f)
                for trk in g.tracks:
                    for seg in trk.segments:
                        for pt in seg.points[::200]:  # nur jede 200. Koordinate
                            n = max(n, pt.latitude)
                            s = min(s, pt.latitude)
                            e = max(e, pt.longitude)
                            w = min(w, pt.longitude)
                            found = True
            except Exception:
                continue
        if not found:
            return None
        # 50-km-Puffer (Breite ≈ 0,45°, Länge ≈ 0,7° in Mitteleuropa)
        return (n + 0.45, s - 0.45, e + 0.7, w - 0.7)

    # ---------------------------------------------- OSM-Dialog & Download
    def _show_osm_dialog(self, bbox: tuple[float, float, float, float]) -> None:
        dlg = tk.Toplevel(self.master)
        dlg.title("OpenStreetMap-Netz herunterladen")
        dlg.transient(self.master)
        dlg.grab_set()
        dlg.resizable(False, False)

        tk.Label(
            dlg,
            text=(
                "Zur Verbesserung der Ladezeit müssen Teile des "
                "OpenStreetMap-Netzes heruntergeladen werden.\n"
                "Bitte wähle einen Dateispeicherort aus."
            ),
            font=("Arial", 12),
            justify="center",
        ).pack(pady=12, padx=10)

        path_var = tk.StringVar(value=os.path.join(self.gpx_path, OSM_DEFAULT_NAME))

        def choose_path() -> None:
            fn = filedialog.asksaveasfilename(
                parent=dlg,
                title="Speicherort wählen",
                defaultextension=".gpkg",
                initialfile=OSM_DEFAULT_NAME,
                filetypes=[("GeoPackage", "*.gpkg")],
            )
            if fn:
                path_var.set(fn)

        tk.Button(dlg, text="Speichern unter …", command=choose_path).pack(pady=4)
        tk.Entry(
            dlg, textvariable=path_var, width=52, state="readonly"
        ).pack(pady=(0, 10))

        prog = ttk.Progressbar(dlg, mode="indeterminate")
        prog.pack(fill="x", padx=20, pady=(0, 10))

        def start_download() -> None:
            prog.start()
            threading.Thread(
                target=self._ensure_osm_network,
                args=(path_var.get(), bbox, dlg, prog),
                daemon=True,
            ).start()

        tk.Button(dlg, text="Weiter", command=start_download).pack(pady=(0, 12))

        # Dialog mittig setzen
        dlg.update_idletasks()
        w, h = dlg.winfo_width(), dlg.winfo_height()
        x = self.master.winfo_rootx() + (self.master.winfo_width() - w) // 2
        y = self.master.winfo_rooty() + (self.master.winfo_height() - h) // 2
        dlg.geometry(f"{w}x{h}+{x}+{y}")
        dlg.wait_window()

    def _ask_overwrite(self) -> bool:
        return messagebox.askyesno(
            APP_NAME,
            "Der vorhandene OSM-Datensatz deckt das Gebiet nicht ab.\n"
            "Neues Netz herunterladen und vorhandenes überschreiben?",
            parent=self.master,
        )

    def _ensure_osm_network(
        self,
        path: str,
        bbox: tuple[float, float, float, float],
        dlg: tk.Toplevel,
        prog: ttk.Progressbar,
    ) -> None:
        ok = algorithm.ensure_osm_network(path, bbox, ask_overwrite_callback=self._ask_overwrite)
        prog.stop()
        dlg.destroy()
        if not ok:
            return  # Abgebrochen
        self.osm_path = path
        algorithm.set_osm_path(path)
        self._build_main_view()  # GUI aufbauen

    # ------------------------------------------------ GUI Hauptansicht
    def _build_main_view(self) -> None:
        for w in self.master.winfo_children():
            w.destroy()
        self.master.configure(bg="white")
        try:
            self.master.state("zoomed")
        except tk.TclError:
            self.master.attributes("-zoomed", True)

        # ---------- linke Teilnehmerliste ----------
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

        # ---------- rechte Seite ----------
        right_frame = tk.Frame(self.master, bg="white")
        right_frame.pack(side="left", fill="both", expand=True)

        self.static_frame = tk.Frame(right_frame, bg="white")
        self.static_frame.pack(side="top", fill="x")

        list_container = tk.Frame(right_frame, bg="white")
        list_container.pack(side="top", fill="both", expand=True)
        canvas = tk.Canvas(list_container, bg="white", highlightthickness=0)
        scrollbar = tk.Scrollbar(
            list_container, orient="vertical", command=canvas.yview
        )
        self.list_inner = tk.Frame(canvas, bg="white")
        self.list_inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.create_window((0, 0), window=self.list_inner, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        tk.Label(
            left_inner,
            text="Teilnehmerinnen\nund Teilnehmer",
            font=("Arial", 14, "bold"),
            bg="white",
            justify="center",
        ).pack(pady=(10, 5))

        # Namen einsammeln
        files = [f for f in os.listdir(self.gpx_path) if f.lower().endswith(".gpx")]
        names = sorted(
            {(f.split("_")[0], f.split("_")[1]) for f in files if len(f.split("_")) >= 3},
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

    # ------------------------------------------------ Analyse starten
    def on_name_click(self, last: str, first: str) -> None:
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

        importlib.reload(algorithm)
        date = algorithm.show_date_dialog(self.master, self.gpx_path, last, first)
        if not date:
            return

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
            self.master.after(
                0, lambda: self.show_stops(loader, prog, date, places)
            )

        threading.Thread(target=run, daemon=True).start()

    # ------------------------------------------------ Orte anzeigen
    def show_stops(
        self,
        loader: tk.Toplevel,
        prog: ttk.Progressbar,
        date: str,
        places: list[dict],
    ) -> None:
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
                wraplength=self.master.winfo_width() * 2,
            ).pack(fill="x", padx=20, pady=5)

            # ---------------- Weg-Infos ----------------
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
                ).pack(fill="x", padx=PAD_INNER, pady=(0, 1))

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
                    ).pack(fill="x", padx=PAD_INNER, pady=(0, 5))


# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    root = tk.Tk()
    WegeRadar(root)
    root.mainloop()