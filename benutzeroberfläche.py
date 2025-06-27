import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import importlib
import algorithm  # stellt sicher, dass das Modul beim Start geladen ist

APP_NAME = "WegeRadar"

class WegeRadar:
    def __init__(self, master):
        self.master = master
        master.title(APP_NAME)
        window_width, window_height = 500, 600
        self.window_width = window_width
        screen_width = master.winfo_screenwidth()
        screen_height = master.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        master.geometry(f"{window_width}x{window_height}+{x}+{y}")
        master.resizable(True, True)

        self.excel_path = None
        self.excel_filename = None
        self.gpx_path = None
        self.gpx_foldername = None
        self.content_frame = None

        self.setup_ui()

    def setup_ui(self):
        tk.Label(self.master, text="Herzlich Willkommen!", font=("Arial", 24, "bold")).pack(pady=(20,10))
        frame = tk.Frame(self.master)
        frame.pack(pady=10)

        tk.Label(frame, text="Excel-Datei (optional):", font=("Arial",12)).grid(row=0, column=0, columnspan=2, sticky="w", padx=5)
        tk.Button(frame, text="Auswählen", command=self.select_excel, width=12).grid(row=1, column=0, padx=5, pady=5)
        self.excel_label_selected = tk.Label(frame, text="Keine Datei ausgewählt", font=("Arial",12), width=20, anchor="w")
        self.excel_label_selected.grid(row=1, column=1, padx=5, pady=5)

        tk.Label(frame, text="GPX-Ordner (Pflicht):", font=("Arial",12)).grid(row=2, column=0, columnspan=2, sticky="w", padx=5, pady=(15,0))
        tk.Button(frame, text="Auswählen", command=self.select_gpx, width=12).grid(row=3, column=0, padx=5, pady=5)
        self.gpx_label_selected = tk.Label(frame, text="Kein Ordner ausgewählt", font=("Arial",12), width=20, anchor="w")
        self.gpx_label_selected.grid(row=3, column=1, padx=5, pady=5)

        tk.Label(self.master,
                 text="(Excel optional; GPX-Ordner ist notwendig.)",
                 font=("Arial",10), fg="gray",
                 wraplength=self.window_width-40, justify="center").pack(fill="x", padx=20, pady=(0,5))

        tk.Button(self.master, text="Start", command=self.start_action,
                  font=("Arial",24,"bold"), height=2).pack(side="bottom", fill="x")

    def select_excel(self):
        path = filedialog.askopenfilename(title="Excel-Datei auswählen",
                                          filetypes=[("Excel-Dateien","*.xlsx *.xls")])
        if path:
            self.excel_path = path
            self.excel_filename = os.path.basename(path)
            self.excel_label_selected.config(text=self.excel_filename)

    def select_gpx(self):
        path = filedialog.askdirectory(title="GPX-Ordner auswählen")
        if path:
            self.gpx_path = path
            self.gpx_foldername = os.path.basename(path)
            self.gpx_label_selected.config(text=self.gpx_foldername)

    def start_action(self):
        if not self.gpx_path:
            messagebox.showwarning(APP_NAME, "Bitte wähle einen GPX-Ordner aus.", parent=self.master)
            return

        for w in self.master.winfo_children():
            w.destroy()
        self.master.configure(bg="white")
        try:
            self.master.state('zoomed')
        except:
            self.master.attributes('-zoomed', True)

        # linke Liste
        container = tk.Frame(self.master, bg="white", width=200)
        container.pack(side="left", fill="y")
        canvas = tk.Canvas(container, bg="white", width=200, highlightthickness=0)
        scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg="white")
        scroll_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0,0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="y", expand=True)
        scrollbar.pack(side="right", fill="y")

        tk.Frame(self.master, bg="black", width=2).pack(side="left", fill="y")
        self.content_frame = tk.Frame(self.master, bg="white")
        self.content_frame.pack(side="left", fill="both", expand=True)

        tk.Label(scroll_frame, text="Teilnehmerinnen\nund Teilnehmer",
                 font=("Arial",14,"bold"), bg="white", justify="center").pack(pady=(10,5))

        files = [f for f in os.listdir(self.gpx_path) if f.lower().endswith('.gpx')]
        names = set()
        for f in files:
            parts = os.path.splitext(f)[0].split('_')
            if len(parts) >= 3:
                names.add((parts[0], parts[1]))
        names = sorted(names, key=lambda x: x[0])

        for last, first in names:
            full = f"{last}, {first}"
            disp = (full[:17] + "...") if len(full)>20 else full
            lbl = tk.Label(scroll_frame, text=disp, font=("Arial",12), bg="white", anchor="w", width=20)
            lbl.pack(fill="x", padx=10, pady=2)
            lbl.bind("<Enter>", lambda e, l=lbl: l.config(bg="#e0e0e0"))
            lbl.bind("<Leave>", lambda e, l=lbl: l.config(bg="white"))
            lbl.bind("<Button-1>", lambda e, l=last, f=first: self.on_name_click(l,f))

    def on_name_click(self, last, first):
        for w in self.content_frame.winfo_children():
            w.destroy()
        tk.Label(self.content_frame,
                 text=f"Teilnehmer(in): {last}, {first}",
                 font=("Arial",14,"bold"), bg="white", anchor="w").pack(fill="x", padx=20, pady=(20,5))
        tk.Button(self.content_frame, text="✖", font=("Arial",12,"bold"),
                  fg="red", bg="white", bd=0,
                  command=lambda: [w.destroy() for w in self.content_frame.winfo_children()])\
            .place(relx=1.0, x=-10, y=10, anchor="ne")

        importlib.reload(algorithm)
        date = algorithm.show_date_dialog(self.master, self.gpx_path, last, first)
        if not date:
            return

        loader = tk.Toplevel(self.master)
        loader.title("Bitte warten...")
        w, h = 300, 80
        self.master.update_idletasks()
        mx, my = self.master.winfo_rootx(), self.master.winfo_rooty()
        mw, mh = self.master.winfo_width(), self.master.winfo_height()
        loader.geometry(f"{w}x{h}+{mx + (mw-w)//2}+{my + (mh-h)//2}")
        loader.transient(self.master)
        loader.grab_set()
        tk.Label(loader, text="Daten werden geladen...", font=("Arial",12)).pack(pady=10)
        progress = ttk.Progressbar(loader, mode="indeterminate")
        progress.pack(fill="x", padx=20, pady=(0,10))
        progress.start()

        def run_analysis():
            stops = algorithm.analyze_gpx(self.gpx_path, last, first, date)
            self.master.after(0, lambda: self.show_stops(loader, progress, date, stops))

        threading.Thread(target=run_analysis, daemon=True).start()

    def show_stops(self, loader, progress, date, stops):
        progress.stop()
        loader.destroy()

        tk.Label(self.content_frame,
                 text=f"Datum der GPX-Datei: {date}",
                 font=("Arial",14,"bold"), bg="white", anchor="w")\
            .pack(fill="x", padx=20, pady=(5,2))
        tk.Frame(self.content_frame, bg="black", height=2).pack(fill="x", pady=(0,10))

        if not stops:
            tk.Label(self.content_frame, text="Keine Aufenthaltsorte ≥3 Min. gefunden.",
                     font=("Arial",12), bg="white", anchor="w",
                     wraplength=self.window_width*2).pack(fill="x", padx=20, pady=5)
            return

        for stop in stops:
            frame = tk.Frame(self.content_frame, bg="white")
            frame.pack(fill="x", padx=20, pady=5)

            start = stop["start_time"].strftime("%H:%M")
            end   = stop["end_time"].strftime("%H:%M")
            addr  = stop.get("address", "Unbekannte Adresse")
            mins  = int(stop["duration_seconds"] / 60)

            tk.Label(frame,
                     text=f"[{start}–{end}] {addr} – {mins} Min.",
                     font=("Arial",12), bg="white", anchor="w",
                     wraplength=self.window_width*2)\
                .pack(fill="x")
            pois = stop.get("pois", [])
            if pois:
                tk.Label(frame, text="POIs: " + ", ".join(pois),
                         font=("Arial",10,"italic"), bg="white",
                         anchor="w", wraplength=self.window_width*2)\
                    .pack(fill="x", padx=(10,0), pady=(2,0))