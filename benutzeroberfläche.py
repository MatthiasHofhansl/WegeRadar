"""
benutzeroberfläche.py
=====================

Tk-Oberfläche für WegeRadar.

* Orts-/Weg-Liste scrollt separat.
* Schwarze Linie bis ganz rechts.
* Datum-Label bündig zu „Teilnehmer(in):“.
* Pro Weg zwei Zeilen:
    Zeile 1: Weg … │ Dauer …; Distanz …; Durchschnittliche Geschwindigkeit …
    Zeile 2: Verkehrsmittel: <Ranking>
"""

from __future__ import annotations

import os, threading, tkinter as tk
from tkinter import filedialog, messagebox, ttk
from math import radians, cos, sin, asin, sqrt
import importlib, algorithm

APP_NAME = "WegeRadar"


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    lat1, lon1, lat2, lon2 = map(radians, (lat1, lon1, lat2, lon2))
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return 6371.0 * 2 * asin(sqrt(a))


class WegeRadar:
    # ------------------------------------------------------------------- #
    def __init__(self, master: tk.Tk) -> None:
        self.master = master
        master.title(APP_NAME)

        win_w, win_h = 500, 330
        sw, sh = master.winfo_screenwidth(), master.winfo_screenheight()
        master.geometry(f"{win_w}x{win_h}+{(sw - win_w) // 2}+{(sh - win_h) // 2}")
        master.resizable(True, True)

        self.window_width: int = win_w
        self.gpx_path: str | None = None

        self.static_frame: tk.Frame | None = None
        self.list_canvas: tk.Canvas | None = None
        self.list_inner: tk.Frame | None = None
        self.list_scrollbar: tk.Scrollbar | None = None

        self.setup_ui()

    # ---------------- Start-UI ---------------- #
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

    # ---------------- Ordnerauswahl ---------- #
    def select_gpx(self) -> None:
        p = filedialog.askdirectory(title="Ordner mit den GPX-Dateien auswählen")
        if p:
            self.gpx_path = p
            self.gpx_label.config(text=os.path.basename(p))

    # ---------------- Hauptansicht ----------- #
    def start_action(self) -> None:
        if not self.gpx_path:
            messagebox.showwarning(
                APP_NAME,
                "Bitte wähle einen Ordner mit den GPX-Dateien aus.",
                parent=self.master,
            )
            return

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
            text="Teilnehmerinnen
und Teilnehmer",
            font=("Arial", 14, "bold"),
            bg="white",
            justify="center",
        ).pack(pady=(10, 5))

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

    # ---------------- Analyse starten ------- #
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
                for frame in (self.static
