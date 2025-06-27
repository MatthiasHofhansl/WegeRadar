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
        window_width = master.winfo_screenwidth()
        window_height = master.winfo_screenheight()
        x = 0
        y = 0
        master.geometry(f"{window_width}x{window_height}+{x}+{y}")
        master.resizable(False, False)

        # Variablen zur Speicherung
        self.excel_filename = None
        self.gpx_foldername = None

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
            font=("Arial", 24, "bold"),
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
            font=("Arial", 24, "bold"),
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

        # Start-Button ganz unten, füllt Breite
        start_btn = tk.Button(
            self.master,
            text="Start",
            command=self.start_action,
            font=("Arial", 24, "bold"),
            height=1
        )
        start_btn.pack(side="bottom", fill="x")

    def select_excel(self):
        path = filedialog.askopenfilename(
            title="Gebe hier den Pfad für deine Excel-Datei/das Wegetagebuch an:",
            filetypes=[("Excel-Dateien", "*.xlsx *.xls")]
        )
        if not path:
            messagebox.showerror("Fehler", "Keine Datei ausgewählt.")
        else:
            self.excel_filename = os.path.basename(path)
            self.excel_label_selected.config(text=self.excel_filename)

    def select_gpx(self):
        path = filedialog.askdirectory(
            title="Gebe hier den Pfad für den Ordner mit den GPX-Dateien an:"
        )
        if not path:
            messagebox.showerror("Fehler", "Keinen Ordner ausgewählt.")
        else:
            self.gpx_foldername = os.path.basename(path)
            self.gpx_label_selected.config(text=self.gpx_foldername)

    def start_action(self):
        # Fenster in Vollbild umwandeln und leeren
        self.master.title(APP_NAME)
        self.master.configure(background="white")
        for widget in self.master.winfo_children():
            widget.destroy()
        # Setze Vollbild
        try:
            self.master.attributes('-fullscreen', True)
        except:
            # Alternative Maximierung
            w = self.master.winfo_screenwidth()
            h = self.master.winfo_screenheight()
            self.master.geometry(f"{w}x{h}+0+0")

if __name__ == "__main__":
    root = tk.Tk()
    app = WegeRadar(root)
    root.mainloop()