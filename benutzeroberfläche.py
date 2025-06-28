"""
benutzeroberfläche.py
=====================

Tk-Oberfläche für die WegeRadar-App
-----------------------------------

* Startfenster:
    – Begrüßung, Auswahl eines GPX-Ordners, Start-Button
* Hauptfenster:
    – Links: Liste der Teilnehmer(innen)
    – Rechts: Anzeige der Orte mit Zeitstempeln & Adressen

Alle Layout-Anpassungen und Funktionen wurden beibehalten.
"""

from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import importlib

import algorithm

APP_NAME = "WegeRadar"

class WegeRadar:
    # ------------------------------------------------------------------- #
    def __init__(self, master: tk.Tk) -> None:
        self.master = master
        master.title(APP_NAME)

        win_w, win_h = 500, 330
        screen_w, screen_h = master.winfo_screenwidth(), master.winfo_screenheight()
        master.geometry(f"{win_w}x{win_h}+{(screen_w-win_w)//2}+{(screen_h-win_h)//2}")
        master.resizable(True, True)

        self.window_width: int = win_w
        self.gpx_path: str | None = None
        self.content_frame: tk.Frame | None = None

        self.setup_ui()

    # ------------------------------------------------------------------- #
    # 1. Start-UI (Begrüßung, Ordnerauswahl, Start-Button)
    # ------------------------------------------------------------------- #
    def setup_ui(self) -> None:
        tk.Label(self.master, text="Herzlich Willkommen!",
                 font=("Arial", 24, "bold")).pack(pady=(10, 3))

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

        tk.Button(
            row, text="Auswählen", width=12, command=self.select_gpx
        ).grid(row=0, column=0, sticky="w")

        self.gpx_label = tk.Label(
            row, text="Keinen Ordner ausgewählt.", font=("Arial", 12), anchor="center"
        )
        self.gpx_label.grid(row=0, column=1, sticky="ew")

        tk.Button(
            self.master, text="Start", command=self.start_action,
            font=("Arial", 24, "bold"), height=2
        ).pack(side="bottom", fill="x", pady=(2, 0))

    # ------------------------------------------------------------------- #
    # 2. Ordnerauswahl                                                      #
    # ------------------------------------------------------------------- #
    def select_gpx(self) -> None:
        path = filedialog.askdirectory(title="Ordner mit den GPX-Dateien auswählen")
        if path:
            self.gpx_path = path
            self.gpx_label.config(text=os.path.basename(path))

    # ------------------------------------------------------------------- #
    # 3. Nach Klick auf „Start“                                            #
    # ------------------------------------------------------------------- #
    def start_action(self) -> None:
        if not self.gpx_path:
            messagebox.showwarning(
                APP_NAME,
                "Bitte wähle einen Ordner mit den GPX-Dateien aus.",
                parent=self.master,
            )
            return

        # Haupt-Ansicht vorbereiten
        for w in self.master.winfo_children():
            w.destroy()
        self.master.configure(bg="white")
        try:
            self.master.state("zoomed")
        except tk.TclError:
            self.master.attributes("-zoomed", True)

        # ---------------- Linke Teilnehmer-Liste ---------------- #
        container = tk.Frame(self.master, bg="white", width=200)
        container.pack(side="left", fill="y")

        canvas = tk.Canvas(container, bg="white", width=200, highlightthickness=0)
        scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)

        scroll_frame = tk.Frame(canvas, bg="white")
        scroll_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="y", expand=True)
        scrollbar.pack(side="right", fill="y")

        tk.Frame(self.master, bg="black", width=2).pack(side="left", fill="y")

        # ---------------- Rechte Inhalts-Fläche ---------------- #
        self.content_frame = tk.Frame(self.master, bg="white")
        self.content_frame.pack(side="left", fill="both", expand=True)

        tk.Label(
            scroll_frame,
            text="Teilnehmerinnen\nund Teilnehmer",
            font=("Arial", 14, "bold"),
            bg="white",
            justify="center",
        ).pack(pady=(10, 5))

        # Teilnehmer-Namen aus GPX-Dateien
        files = [f for f in os.listdir(self.gpx_path) if f.lower().endswith(".gpx")]
        names = sorted(
            {(f.split("_")[0], f.split("_")[1]) for f in files if len(f.split("_")) >= 3},
            key=lambda x: x[0],
        )

        for last, first in names:
            display = f"{last}, {first}"
            short   = display if len(display) <= 20 else display[:17] + "…"
            lbl = tk.Label(
                scroll_frame, text=short, font=("Arial", 12),
                bg="white", anchor="w", width=20
            )
            lbl.pack(fill="x", padx=10, pady=2)
            lbl.bind("<Enter>", lambda e, l=lbl: l.config(bg="#e0e0e0"))
            lbl.bind("<Leave>", lambda e, l=lbl: l.config(bg="white"))
            lbl.bind(
                "<Button-1>",
                lambda e, l=last, f=first: self.on_name_click(l, f),
            )

    # ------------------------------------------------------------------- #
    # 4. Klick auf einen Namen                                            #
    # ------------------------------------------------------------------- #
    def on_name_click(self, last: str, first: str) -> None:
        for w in self.content_frame.winfo_children():
            w.destroy()

        tk.Label(
            self.content_frame,
            text=f"Teilnehmer(in): {last}, {first}",
            font=("Arial", 14, "bold"),
            bg="white",
            anchor="w",
        ).pack(fill="x", padx=20, pady=(20, 5))

        tk.Button(
            self.content_frame,
            text="✖",
            font=("Arial", 12, "bold"),
            fg="red",
            bg="white",
            bd=0,
            command=lambda: [w.destroy() for w in self.content_frame.winfo_children()],
        ).place(relx=1.0, x=-10, y=10, anchor="ne")

        importlib.reload(algorithm)
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
        loader.geometry(f"{w}x{h}+{mx+(mw-w)//2}+{my+(mh-h)//2}")
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

    # ------------------------------------------------------------------- #
    # 5. Ergebnis-Anzeige (Orte, Zeiten, Adressen)
    # ------------------------------------------------------------------- #
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
            self.content_frame,
            text=f"Datum der GPX-Datei: {date}",
            font=("Arial", 14, "bold"),
            bg="white",
            anchor="w",
        ).pack(fill="x", padx=20, pady=(5, 2))
        tk.Frame(self.content_frame, bg="black", height=2).pack(fill="x", pady=(0, 10))

        if not places:
            tk.Label(
                self.content_frame,
                text="Keine Orte gefunden.",
                font=("Arial", 12),
                bg="white",
                anchor="w",
            ).pack(fill="x", padx=20, pady=5)
            return

        for idx, place in enumerate(places, 1):
            # Zeitspanne HH:MM Uhr - HH:MM Uhr
            start_str = place["start_dt"].strftime("%H:%M")
            end_str   = place["end_dt"].strftime("%H:%M")
            time_span = f"{start_str} Uhr - {end_str} Uhr"

            # Adresse
            name   = place.get("name", "").strip()
            road   = place.get("road", "").strip()
            house  = place.get("house_number", "").strip()
            street = " ".join(x for x in (road, house) if x)

            pc     = place.get("postcode", "").strip()
            city   = place.get("city", "").strip()
            pc_city = ", ".join(x for x in (pc, city) if x)

            addr_parts: list[str] = []
            if name:
                addr_parts.append(name)
            addr_line = ", ".join(x for x in (street, pc_city) if x)
            if addr_line:
                addr_parts.append(addr_line)

            text = f"Ort {idx} | {time_span}"
            if addr_parts:
                text += " | " + " | ".join(addr_parts)

            tk.Label(
                self.content_frame,
                text=text,
                font=("Arial", 12),
                bg="white",
                anchor="w",
                wraplength=self.window_width * 2,
            ).pack(fill="x", padx=20, pady=5)

# --------------------------------------------------------------------------- #
if __name__ == "__main__":
    root = tk.Tk()
    WegeRadar(root)
    root.mainloop()