# benutzeroberfläche.py
import os
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import importlib
import algorithm

APP_NAME = "WegeRadar"

class WegeRadar:
    def __init__(self, master):
        self.master = master
        master.title(APP_NAME)

        # kompakteres Startfenster (kleiner)
        win_w, win_h = 500, 380
        self.window_width = win_w
        screen_w = master.winfo_screenwidth()
        screen_h = master.winfo_screenheight()
        x = (screen_w - win_w) // 2
        y = (screen_h - win_h) // 2
        master.geometry(f"{win_w}x{win_h}+{x}+{y}")
        master.resizable(True, True)

        self.content_frame = None
        self.gpx_path = None

        self.setup_ui()

    # ------------------------------------------------------- #
    def setup_ui(self):
        # Überschrift – mittig
        tk.Label(self.master, text="Herzlich Willkommen!",
                 font=("Arial", 24, "bold"))\
            .pack(pady=(20, 5))

        # ---------- GPX-Ordner ---------- #
        gpx_frame = tk.Frame(self.master)
        gpx_frame.pack(fill="x", padx=20, pady=(10, 0), anchor="w")

        tk.Label(gpx_frame, text="GPX-Ordner (Pflicht):",
                 font=("Arial", 12))\
            .grid(row=0, column=0, sticky="w")

        tk.Button(gpx_frame, text="Auswählen", width=12,
                  command=self.select_gpx)\
            .grid(row=1, column=0, sticky="w", pady=3)

        self.gpx_label = tk.Label(gpx_frame, text="Kein Ordner ausgewählt",
                                  font=("Arial", 12), width=25, anchor="w")
        self.gpx_label.grid(row=1, column=1, padx=10, pady=3, sticky="w")

        # Start-Button (direkt unten, weniger Abstand)
        tk.Button(self.master, text="Start", command=self.start_action,
                  font=("Arial", 24, "bold"), height=2)\
            .pack(side="bottom", fill="x", pady=(5, 0))

    # ------------------------------------------------------- #
    def select_gpx(self):
        path = filedialog.askdirectory(title="GPX-Ordner auswählen")
        if path:
            self.gpx_path = path
            self.gpx_label.config(text=os.path.basename(path))

    # ------------------------------------------------------- #
    def start_action(self):
        if not self.gpx_path:
            messagebox.showwarning(APP_NAME, "Bitte wähle einen GPX-Ordner aus.",
                                   parent=self.master)
            return

        # Hauptansicht vorbereiten
        for w in self.master.winfo_children():
            w.destroy()
        self.master.configure(bg="white")
        try:
            self.master.state("zoomed")
        except tk.TclError:
            self.master.attributes("-zoomed", True)

        # ---------- linke Teilnehmerliste ---------- #
        container = tk.Frame(self.master, bg="white", width=200)
        container.pack(side="left", fill="y")
        canvas = tk.Canvas(container, bg="white", width=200,
                           highlightthickness=0)
        scrollbar = tk.Scrollbar(container, orient="vertical",
                                 command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg="white")
        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="y", expand=True)
        scrollbar.pack(side="right", fill="y")

        tk.Frame(self.master, bg="black", width=2)\
            .pack(side="left", fill="y")

        self.content_frame = tk.Frame(self.master, bg="white")
        self.content_frame.pack(side="left", fill="both", expand=True)

        tk.Label(scroll_frame, text="Teilnehmerinnen\nund Teilnehmer",
                 font=("Arial", 14, "bold"), bg="white", justify="center")\
            .pack(pady=(10, 5))

        files = [f for f in os.listdir(self.gpx_path)
                 if f.lower().endswith(".gpx")]
        names = sorted({(f.split("_")[0], f.split("_")[1]) for f in files
                        if len(f.split("_")) >= 3}, key=lambda x: x[0])

        for last, first in names:
            disp = f"{last}, {first}"
            short = disp if len(disp) <= 20 else disp[:17] + "..."
            lbl = tk.Label(scroll_frame, text=short, font=("Arial", 12),
                           bg="white", anchor="w", width=20)
            lbl.pack(fill="x", padx=10, pady=2)
            lbl.bind("<Enter>", lambda e, l=lbl: l.config(bg="#e0e0e0"))
            lbl.bind("<Leave>", lambda e, l=lbl: l.config(bg="white"))
            lbl.bind("<Button-1>",
                     lambda e, l=last, f=first: self.on_name_click(l, f))

    # ------------------------------------------------------- #
    def on_name_click(self, last, first):
        for w in self.content_frame.winfo_children():
            w.destroy()

        tk.Label(self.content_frame,
                 text=f"Teilnehmer(in): {last}, {first}",
                 font=("Arial", 14, "bold"), bg="white", anchor="w")\
            .pack(fill="x", padx=20, pady=(20, 5))
        tk.Button(self.content_frame, text="✖", font=("Arial", 12, "bold"),
                  fg="red", bg="white", bd=0,
                  command=lambda: [w.destroy()
                                   for w in self.content_frame.winfo_children()])\
            .place(relx=1.0, x=-10, y=10, anchor="ne")

        importlib.reload(algorithm)
        date = algorithm.show_date_dialog(self.master, self.gpx_path, last, first)
        if not date:
            return

        loader = tk.Toplevel(self.master)
        loader.title("Bitte warten …")
        loader.resizable(False, False)
        w, h = 300, 80
        self.master.update_idletasks()
        mx, my = self.master.winfo_rootx(), self.master.winfo_rooty()
        mw, mh = self.master.winfo_width(), self.master.winfo_height()
        loader.geometry(f"{w}x{h}+{mx+(mw-w)//2}+{my+(mh-h)//2}")
        loader.transient(self.master)
        loader.grab_set()

        tk.Label(loader, text="Daten werden geladen …",
                 font=("Arial", 12)).pack(pady=10)
        prog = ttk.Progressbar(loader, mode="indeterminate")
        prog.pack(fill="x", padx=20, pady=(0, 10))
        prog.start()

        def run():
            places = algorithm.analyze_gpx(self.gpx_path, last, first, date)
            self.master.after(0, lambda: self.show_stops(loader, prog,
                                                         date, places))

        threading.Thread(target=run, daemon=True).start()

    # ------------------------------------------------------- #
    def show_stops(self, loader, prog, date, places):
        prog.stop()
        loader.destroy()

        tk.Label(self.content_frame, text=f"Datum der GPX-Datei: {date}",
                 font=("Arial", 14, "bold"), bg="white", anchor="w")\
            .pack(fill="x", padx=20, pady=(5, 2))
        tk.Frame(self.content_frame, bg="black", height=2)\
            .pack(fill="x", pady=(0, 10))

        if not places:
            tk.Label(self.content_frame, text="Keine Orte gefunden.",
                     font=("Arial", 12), bg="white", anchor="w")\
                .pack(fill="x", padx=20, pady=5)
            return

        for idx, p in enumerate(places, 1):
            name = p.get("name", "").strip()
            road = p.get("road", "").strip()
            house = p.get("house_number", "").strip()
            street = " ".join(x for x in [road, house] if x)

            pc = p.get("postcode", "").strip()
            city = p.get("city", "").strip()
            pc_city = ", ".join(x for x in [pc, city] if x)

            parts = []
            if name:
                parts.append(name)
            addr = ", ".join(x for x in [street, pc_city] if x)
            if addr:
                parts.append(addr)

            text = f"Ort {idx}: {' | '.join(parts)}"

            tk.Label(self.content_frame, text=text, font=("Arial", 12),
                     bg="white", anchor="w",
                     wraplength=self.window_width * 2)\
                .pack(fill="x", padx=20, pady=5)

# ----------------------------------------------------------- #
if __name__ == "__main__":
    root = tk.Tk()
    WegeRadar(root)
    root.mainloop()