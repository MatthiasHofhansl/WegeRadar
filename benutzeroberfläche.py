import os
import tkinter as tk
from tkinter import filedialog, messagebox

# App-Name
APP_NAME = "WegeRadar"

class WegeRadar:
    def __init__(self, master):
        self.master = master
        master.title(APP_NAME)

        # Fenstergröße und Zentrierung
        window_width = 500
        window_height = 600
        screen_width = master.winfo_screenwidth()
        screen_height = master.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        master.geometry(f"{window_width}x{window_height}+{x}+{y}")
        master.resizable(False, False)

        # Variablen zur Speicherung
        self.excel_filename = None
        self.excel_path = None
        self.gpx_foldername = None
        self.gpx_path = None

        self.setup_ui()

    def setup_ui(self):
        # Willkommenstext
        welcome = tk.Label(
            self.master,
            text="Herzlich Willkommen!",
            font=("Arial", 24, "bold")
        )
        welcome.pack(pady=(20, 10))

        # Container für Pfadauswahl
        frame = tk.Frame(self.master)
        frame.pack(pady=10)

        # Excel-Datei Auswahl
        prompt_excel = tk.Label(
            frame,
            text="Gebe hier den Pfad für deine Excel-Datei/das Wegetagebuch an:",
            font=("Arial", 12)
        )
        prompt_excel.grid(row=0, column=0, columnspan=2, sticky="w", padx=5, pady=(5, 0))
        btn_excel = tk.Button(
            frame,
            text="Auswählen",
            command=self.select_excel,
            width=12
        )
        btn_excel.grid(row=1, column=0, padx=5, pady=(5, 5))
        self.excel_label_selected = tk.Label(
            frame,
            text="Keine Datei ausgewählt",
            font=("Arial", 12),
            width=20,
            anchor="w"
        )
        self.excel_label_selected.grid(row=1, column=1, padx=5, pady=(5, 5))

        # GPX-Ordner Auswahl
        prompt_gpx = tk.Label(
            frame,
            text="Gebe hier den Pfad für den Ordner mit den GPX-Dateien an:",
            font=("Arial", 12)
        )
        prompt_gpx.grid(row=2, column=0, columnspan=2, sticky="w", padx=5, pady=(15, 0))
        btn_gpx = tk.Button(
            frame,
            text="Auswählen",
            command=self.select_gpx,
            width=12
        )
        btn_gpx.grid(row=3, column=0, padx=5, pady=(5, 5))
        self.gpx_label_selected = tk.Label(
            frame,
            text="Keinen Ordner ausgewählt",
            font=("Arial", 12),
            width=20,
            anchor="w"
        )
        self.gpx_label_selected.grid(row=3, column=1, padx=5, pady=(5, 5))

        # Start-Button bündig am unteren Fensterrand ohne Padding
        start_btn = tk.Button(
            self.master,
            text="Start",
            command=self.start_action,
            font=("Arial", 24, "bold"),
            height=2
        )
        start_btn.pack(side="bottom", fill="x")

    def select_excel(self):
        path = filedialog.askopenfilename(
            title="Gebe hier den Pfad für deine Excel-Datei/das Wegetagebuch an:",
            filetypes=[("Excel-Dateien", "*.xlsx *.xls")]
        )
        if path:
            self.excel_path = path
            self.excel_filename = os.path.basename(path)
            self.excel_label_selected.config(text=self.excel_filename)

    def select_gpx(self):
        path = filedialog.askdirectory(
            title="Gebe hier den Pfad für den Ordner mit den GPX-Dateien an:"
        )
        if path:
            self.gpx_path = path
            self.gpx_foldername = os.path.basename(path)
            self.gpx_label_selected.config(text=self.gpx_foldername)

    def start_action(self):
        # Prüfe, ob Excel und GPX ausgewählt sind
        if not self.excel_path or not self.gpx_path:
            messagebox.showwarning(
                APP_NAME,
                "Um fortzufahren, wähle bitte sowohl eine Excel-Datei als auch einen Ordner mit den GPX-Dateien aus.",
                parent=self.master
            )
            return
        # Alles entfernen, Hintergrund weiß
        self.master.title(APP_NAME)
        for widget in self.master.winfo_children():
            widget.destroy()
        self.master.configure(background="white")
        # Fenster maximieren (mit Titel-Leiste weiterhin sichtbar)
        try:
            self.master.state('zoomed')  # Windows/Linux
        except:
            self.master.attributes('-zoomed', True)  # macOS

        # Linke Box für GPX-Dateien-Liste
        left_frame = tk.Frame(self.master, bg="white", width=200)
        left_frame.pack(side="left", fill="y")

        # Titel in Box
        title = tk.Label(
            left_frame,
            text="Teilnehmerinnen\nund Teilnehmer",
            font=("Arial", 14, "bold"),
            bg="white",
            justify="center"
        )
        title.pack(pady=(10, 5))

        # Dateien aus Ordner auslesen und Namen sortieren
        files = [f for f in os.listdir(self.gpx_path) if f.lower().endswith('.gpx')]
        names_set = set()
        for f in files:
            base = os.path.splitext(f)[0]
            parts = base.split('_')
            if len(parts) >= 2:
                last = parts[0]
                first = parts[1]
                names_set.add((last, first))
        # Alphabetisch nach Nachname sortieren
        names = sorted(names_set, key=lambda x: x[0])

        # Anzeige
        for last, first in names:
            lbl = tk.Label(
                left_frame,
                text=f"{last}, {first}",
                font=("Arial", 12),
                bg="white",
                anchor="w"
            )
            lbl.pack(fill="x", padx=10, pady=2)

if __name__ == "__main__":
    root = tk.Tk()
    app = WegeRadar(root)
    root.mainloop()