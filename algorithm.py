# algorithm.py
import os
import tkinter as tk
from tkinter import messagebox

def show_date_dialog(master, gpx_folder, last, first):
    """
    Öffnet einen Dialog mit allen verfügbaren GPX-Dateien für
    last_first_<Datum>.gpx im Ordner und lässt den Nutzer ein Datum wählen.
    Gibt das ausgewählte Datum zurück. Wenn nur eine Datei existiert,
    wird direkt dieses Datum zurückgegeben.
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
        return None

    # Datum → Dateiname mappen
    date_map = {}
    for f in files:
        base = os.path.splitext(f)[0]
        parts = base.split('_')
        date = parts[2] if len(parts) >= 3 else "Unbekannt"
        date_map[date] = f

    # Wenn nur eine Datei vorhanden ist, direkt zurückgeben
    if len(date_map) == 1:
        date = next(iter(date_map))
        fullpath = os.path.join(gpx_folder, date_map[date])
        print(f"Ausgewählte GPX-Datei: {fullpath}")
        return date

    # Mehrere Dateien → Auswahl-Dialog
    dates = sorted(date_map.keys())
    selected = {"date": None}

    dialog = tk.Toplevel(master)
    dialog.title("GPX-Datei Auswahl")
    dialog.transient(master)
    dialog.grab_set()

    tk.Label(
        dialog,
        text=(
            "Für diese(n) Teilnehmer(in) stehen mehrere GPX-Dateien zur Verfügung.\n"
            "An welchem Tag soll die auszuwählende GPX-Datei aufgezeichnet worden sein?"
        ),
        font=("Arial", 12),
        justify="center",
        wraplength=300
    ).pack(pady=(10, 10), padx=10)

    def select(d):
        selected["date"] = d
        filename = date_map[d]
        fullpath = os.path.join(gpx_folder, filename)
        print(f"Ausgewählte GPX-Datei: {fullpath}")
        dialog.destroy()

    for d in dates:
        tk.Button(dialog, text=d, width=20, command=lambda d=d: select(d)).pack(pady=2, padx=20)

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
    return selected["date"]