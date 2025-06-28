"""
benutzeroberfläche.py
=====================

Tk-Oberfläche für WegeRadar.

Neu:
* “Weg n”-Zeile zwischen zwei Orten (Distanz in km).
* Rechte Ergebnis-Spalte hat jetzt eigene Scrollbar.
* Ausgabe-Format: Ort n | Aufenthaltszeit | Name (falls vorhanden) | Adresse
"""

from __future__ import annotations

import os, threading, tkinter as tk
from tkinter import filedialog, messagebox, ttk
from math import radians, cos, sin, asin, sqrt
import importlib, algorithm

APP_NAME = "WegeRadar"

def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Großkreis-Distanz in Kilometern (für Weg-Distanz)."""
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat/2)**2 + cos(lat1)*cos(lat2)*sin(dlon/2)**2
    return 6371.0 * 2 * asin(sqrt(a))

class WegeRadar:
    # ------------------------------------------------------------------- #
    def __init__(self, master: tk.Tk) -> None:
        self.master = master
        master.title(APP_NAME)

        win_w, win_h = 500, 330
        sw, sh = master.winfo_screenwidth(), master.winfo_screenheight()
        master.geometry(f"{win_w}x{win_h}+{(sw-win_w)//2}+{(sh-win_h)//2}")
        master.resizable(True, True)

        self.window_width: int = win_w
        self.gpx_path: str | None = None

        # Rahmen für rechte Scroll-Fläche erzeugen (beim Start leer)
        self.content_frame: tk.Frame | None = None
        self.right_canvas: tk.Canvas | None = None
        self.right_scrollbar: tk.Scrollbar | None = None
        self.right_inner: tk.Frame | None = None

        self.setup_ui()

    # ---------------- Start-UI ---------------- #
    def setup_ui(self) -> None:
        tk.Label(self.master, text="Herzlich Willkommen!",
                 font=("Arial", 24, "bold")).pack(pady=(10, 3))

        gpx_frame = tk.Frame(self.master)
        gpx_frame.pack(fill="x", padx=20, pady=(5, 0), anchor="w")

        tk.Label(gpx_frame,
                 text="Bitte lade hier den Ordner mit den GPX-Dateien hoch:",
                 font=("Arial", 12)).grid(row=0, column=0, sticky="w")

        row = tk.Frame(gpx_frame)
        row.grid(row=1, column=0, sticky="ew", pady=2)
        row.grid_columnconfigure(1, weight=1)

        tk.Button(row, text="Auswählen", width=12,
                  command=self.select_gpx).grid(row=0, column=0, sticky="w")

        self.gpx_label = tk.Label(row, text="Keinen Ordner ausgewählt.",
                                  font=("Arial", 12), anchor="center")
        self.gpx_label.grid(row=0, column=1, sticky="ew")

        tk.Button(self.master, text="Start", command=self.start_action,
                  font=("Arial", 24, "bold"), height=2)\
            .pack(side="bottom", fill="x", pady=(2, 0))

    # ---------------- Ordnerauswahl ---------- #
    def select_gpx(self) -> None:
        p = filedialog.askdirectory(title="Ordner mit den GPX-Dateien auswählen")
        if p:
            self.gpx_path = p
            self.gpx_label.config(text=os.path.basename(p))

    # ---------------- Hauptansicht ----------- #
    def start_action(self) -> None:
        if not self.gpx_path:
            messagebox.showwarning(APP_NAME,
                                   "Bitte wähle einen Ordner mit den GPX-Dateien aus.",
                                   parent=self.master)
            return

        for w in self.master.winfo_children(): w.destroy()
        self.master.configure(bg="white")
        try: self.master.state("zoomed")
        except tk.TclError: self.master.attributes("-zoomed", True)

        # Linke Liste
        container = tk.Frame(self.master, bg="white", width=200)
        container.pack(side="left", fill="y")

        canvas = tk.Canvas(container, bg="white", width=200, highlightthickness=0)
        scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg="white")
        scroll_frame.bind("<Configure>",
                          lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="y", expand=True)
        scrollbar.pack(side="right", fill="y")
        tk.Frame(self.master, bg="black", width=2).pack(side="left", fill="y")

        # Rechte Scroll-Fläche (neu mit eigener Scrollbar)
        self.content_frame = tk.Frame(self.master, bg="white")
        self.content_frame.pack(side="left", fill="both", expand=True)

        self.right_canvas = tk.Canvas(self.content_frame, bg="white", highlightthickness=0)
        self.right_scrollbar = tk.Scrollbar(self.content_frame, orient="vertical",
                                            command=self.right_canvas.yview)
        self.right_inner = tk.Frame(self.right_canvas, bg="white")
        self.right_inner.bind("<Configure>",
                              lambda e: self.right_canvas.configure(scrollregion=self.right_canvas.bbox("all")))
        self.right_canvas.create_window((0, 0), window=self.right_inner, anchor="nw")
        self.right_canvas.configure(yscrollcommand=self.right_scrollbar.set)
        self.right_canvas.pack(side="left", fill="both", expand=True)
        self.right_scrollbar.pack(side="right", fill="y")

        tk.Label(scroll_frame,
                 text="Teilnehmerinnen\nund Teilnehmer",
                 font=("Arial", 14, "bold"),
                 bg="white", justify="center").pack(pady=(10, 5))

        files = [f for f in os.listdir(self.gpx_path) if f.lower().endswith(".gpx")]
        names = sorted({(f.split("_")[0], f.split("_")[1])
                        for f in files if len(f.split("_")) >= 3},
                       key=lambda x: x[0])

        for last, first in names:
            disp = f"{last}, {first}"
            short = disp if len(disp) <= 20 else disp[:17] + "…"
            lbl = tk.Label(scroll_frame, text=short, font=("Arial", 12),
                           bg="white", anchor="w", width=20)
            lbl.pack(fill="x", padx=10, pady=2)
            lbl.bind("<Enter>", lambda e, l=lbl: l.config(bg="#e0e0e0"))
            lbl.bind("<Leave>", lambda e, l=lbl: l.config(bg="white"))
            lbl.bind("<Button-1>",
                     lambda e, l=last, f=first: self.on_name_click(l, f))

    # ---------------- Analyse starten ------- #
    def on_name_click(self, last: str, first: str) -> None:
        # Rechte Fläche leeren
        for w in self.right_inner.winfo_children():
            w.destroy()

        heading = tk.Frame(self.right_inner, bg="white")
        heading.pack(fill="x")
        tk.Label(heading,
                 text=f"Teilnehmer(in): {last}, {first}",
                 font=("Arial", 14, "bold"),
                 bg="white", anchor="w").pack(side="left", padx=10, pady=10)
        tk.Button(heading, text="✖", font=("Arial", 12, "bold"),
                  fg="red", bg="white", bd=0,
                  command=lambda: [w.destroy() for w in self.right_inner.winfo_children()])\
            .pack(side="right", padx=10, pady=10)

        importlib.reload(algorithm)
        date = algorithm.show_date_dialog(self.master, self.gpx_path, last, first)
        if not date: return

        loader = tk.Toplevel(self.master); loader.title("Bitte warten…")
        loader.resizable(False, False)
        w, h = 300, 80
        self.master.update_idletasks()
        mx, my = self.master.winfo_rootx(), self.master.winfo_rooty()
        mw, mh = self.master.winfo_width(), self.master.winfo_height()
        loader.geometry(f"{w}x{h}+{mx+(mw-w)//2}+{my+(mh-h)//2}")
        loader.transient(self.master); loader.grab_set()

        tk.Label(loader, text="Daten werden geladen…", font=("Arial", 12)).pack(pady=10)
        prog = ttk.Progressbar(loader, mode="indeterminate")
        prog.pack(fill="x", padx=20, pady=(0, 10)); prog.start()

        def run() -> None:
            places = algorithm.analyze_gpx(self.gpx_path, last, first, date)
            self.master.after(0, lambda: self.show_stops(loader, prog, date, places))
        threading.Thread(target=run, daemon=True).start()

    # ---------------- Orte + Wege anzeigen -- #
    def show_stops(self, loader: tk.Toplevel, prog: ttk.Progressbar,
                   date: str, places: list[dict]) -> None:
        prog.stop(); loader.destroy()

        tk.Label(self.right_inner, text=f"Datum der GPX-Datei: {date}",
                 font=("Arial", 14, "bold"), bg="white", anchor="w")\
            .pack(fill="x", padx=20, pady=(5, 2))
        tk.Frame(self.right_inner, bg="black", height=2)\
            .pack(fill="x", pady=(0, 10))

        if not places:
            tk.Label(self.right_inner, text="Keine Orte gefunden.",
                     font=("Arial", 12), bg="white", anchor="w")\
                .pack(fill="x", padx=20, pady=5)
            return

        for idx, p in enumerate(places, 1):
            start = p["start_dt"].strftime("%H:%M")
            end   = p["end_dt"].strftime("%H:%M")
            time_span = f"{start} Uhr - {end} Uhr"

            name  = p.get("name", "").strip()
            road  = p.get("road", "").strip()
            house = p.get("house_number", "").strip()
            street = " ".join(x for x in (road, house) if x)

            pc   = p.get("postcode", "").strip()
            city = p.get("city", "").strip()
            pc_city = ", ".join(x for x in (pc, city) if x)

            parts: list[str] = [time_span]
            if name:
                parts.append(name)
            addr_line = ", ".join(x for x in (street, pc_city) if x)
            if addr_line:
                parts.append(addr_line)

            ort_text = f"Ort {idx} | " + " | ".join(parts)

            tk.Label(self.right_inner, text=ort_text, font=("Arial", 12),
                     bg="white", anchor="w",
                     wraplength=self.window_width * 2)\
                .pack(fill="x", padx=20, pady=5)

            # Weg n (wenn nicht letzter Ort)
            if idx < len(places):
                nxt = places[idx]
                dist_km = _haversine_km(p["lat"], p["lon"], nxt["lat"], nxt["lon"])
                weg_text = f"Weg {idx}: Distanz {dist_km:.2f} km"
                tk.Label(self.right_inner, text=weg_text,
                         font=("Arial", 11, "italic"),
                         bg="white", anchor="w")\
                    .pack(fill="x", padx=40, pady=(0, 5))

# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    root = tk.Tk()
    WegeRadar(root)
    root.mainloop()