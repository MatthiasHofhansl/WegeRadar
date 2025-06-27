# algorithm.py
import os
import tkinter as tk
from tkinter import messagebox

def show_date_dialog(master, gpx_folder, last, first):
    """
    Öffnet einen Dialog mit allen verfügbaren GPX-Dateien für
    last_first_<Datum>.gpx im Ordner und lässt den Nutzer ein Datum wählen.
    Wenn nur eine Datei existiert, wird direkt diese ausgewählt.
    """
    prefix = f"{last}_{first}_"
    files = [
        f for f in os.listdir(gpx_folder)
        if f.startswith(prefix) and f.lower().endswith('.gpx')
    ]

    if not files:
        messagebox.showinfo(
            "WegeRadar",
            f"Keine GPX-Dateien für {last}, {first} gefunden.",
            parent=master
        )
        return

    # Wenn nur eine Datei vorhanden ist, direkt auswählen
    if len(files) == 1:
        filename = files[0]
        fullpath = os.path.join(gpx_folder, filename)
        print(f"Ausgewählte GPX-Datei: {fullpath}")
        return

    # Mehrere Dateien: Datum → Dateiname mappen
    date_map = {}
    for f in files:
        base = os.path.splitext(f)[0]
        parts = base.split('_')
        date = parts[2] if len(parts) >= 3 else "Unbekannt"
        date_map[date] = f

    dates = sorted(date_map.keys())

    # Dialogfenster für die Datumsauswahl
    dialog = tk.Toplevel(master)
    dialog.title("GPX-Auswahl")
    dialog.transient(master)
    dialog.grab_set()

    # Frage-Label mittig
    lbl = tk.Label(
        dialog,
        text="Für welchen Tag möchtest du die GPX-Datei auswerten?",
        font=("Arial", 12),
        justify="center",
        wraplength=300
    )
    lbl.pack(pady=(10, 10), padx=10)

    # Auswahl-Callback
    def select(d):
        filename = date_map[d]
        fullpath = os.path.join(gpx_folder, filename)
        print(f"Ausgewählte GPX-Datei: {fullpath}")
        dialog.destroy()

    # Buttons für jedes Datum
    for d in dates:
        btn = tk.Button(
            dialog,
            text=d,
            width=20,
            command=lambda d=d: select(d)
        )
        btn.pack(pady=2, padx=20)

    # Dialog zentrieren
    dialog.update_idletasks()
    w = dialog.winfo_width()
    h = dialog.winfo_height()
    sw = dialog.winfo_screenwidth()
    sh = dialog.winfo_screenheight()
    x = (sw - w) // 2
    y = (sh - h) // 2
    dialog.geometry(f"{w}x{h}+{x}+{y}")

    master.wait_window(dialog)