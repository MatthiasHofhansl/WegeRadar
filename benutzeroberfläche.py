import os
import tkinter as tk
from tkinter import filedialog, messagebox
import importlib
import algorithm  # stellt sicher, dass das Modul beim Start geladen ist

# App-Name
APP_NAME = "WegeRadar"

class WegeRadar:
    def __init__(self, master):
        self.master = master
        master.title(APP_NAME)

        # Fenstergröße und Zentrierung
        window_width = 500
        window_height = 600
        self.window_width = window_width  # für wraplength des Hinweistextes
        screen_width = master.winfo_screenwidth()
        screen_height = master.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        master.geometry(f"{window_width}x{window_height}+{x}+{y}")
        master.resizable(True, True)

        # Variablen zur Speicherung
        self.excel_path = None
        self.excel_filename = None
        self.gpx_path = None
        self.gpx_foldername = None
        self.content_frame = None  # Platz für Detail-Ansicht

        self.setup_ui()

    def setup_ui(self):
        # Willkommenstext
        tk.Label(
            self.master,
            text="Herzlich Willkommen!",
            font=("Arial", 24, "bold")
        ).pack(pady=(20, 10))

        # Container für Pfadauswahl
        frame = tk.Frame(self.master)
        frame.pack(pady=10)

        # Excel-Datei Auswahl
        tk.Label(
            frame,
            text="Gebe hier den Pfad für deine Excel-Datei/das Wegetagebuch an:",
            font=("Arial", 12)
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=5, pady=(5, 0))
        tk.Button(
            frame,
            text="Auswählen",
            command=self.select_excel,
            width=12
        ).grid(row=1, column=0, padx=5, pady=(5, 5))
        self.excel_label_selected = tk.Label(
            frame,
            text="Keine Datei ausgewählt",
            font=("Arial", 12),
            width=20,
            anchor="w"
        )
        self.excel_label_selected.grid(row=1, column=1, padx=5, pady=(5, 5))

        # GPX-Ordner Auswahl
        tk.Label(
            frame,
            text="Gebe hier den Pfad für den Ordner mit den GPX-Dateien an:",
            font=("Arial", 12)
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=5, pady=(15, 0))
        tk.Button(
            frame,
            text="Auswählen",
            command=self.select_gpx,
            width=12
        ).grid(row=3, column=0, padx=5, pady=(5, 5))
        self.gpx_label_selected = tk.Label(
            frame,
            text="Keinen Ordner ausgewählt",
            font=("Arial", 12),
            width=20,
            anchor="w"
        )
        self.gpx_label_selected.grid(row=3, column=1, padx=5, pady=(5, 5))

        # Hinweistext über dem Start-Button
        tk.Label(
            self.master,
            text=(
                "(Du musst nicht zwingend eine Excel-Datei/ein Wegetagebuch "
                "hochladen. Das Hochladen eines Ordners mit GPX-Dateien "
                "ist allerdings notwendig.)"
            ),
            font=("Arial", 10),
            fg="gray",
            wraplength=self.window_width - 40,
            justify="center"
        ).pack(fill="x", padx=20, pady=(0, 5))

        # Start-Button bündig am unteren Fensterrand
        tk.Button(
            self.master,
            text="Start",
            command=self.start_action,
            font=("Arial", 24, "bold"),
            height=2
        ).pack(side="bottom", fill="x")

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
        # Prüfe, ob GPX-Ordner ausgewählt ist (Excel optional)
        if not self.gpx_path:
            messagebox.showwarning(
                APP_NAME,
                "Um fortzufahren, wähle bitte einen Ordner mit den GPX-Dateien aus.",
                parent=self.master
            )
            return

        # Altes GUI entfernen, Hintergrund weiß setzen
        self.master.title(APP_NAME)
        for widget in self.master.winfo_children():
            widget.destroy()
        self.master.configure(background="white")

        # Fenster maximieren (mit sichtbarer Titelleiste)
        try:
            self.master.state('zoomed')       # Windows/Linux
        except:
            self.master.attributes('-zoomed', True)  # macOS

        # Scrollbarer Container für Namen
        container = tk.Frame(self.master, bg="white", width=200)
        container.pack(side="left", fill="y")
        canvas = tk.Canvas(container, bg="white", width=200, highlightthickness=0)
        scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scroll_frame = tk.Frame(canvas, bg="white")
        scroll_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=scroll_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="y", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Mausrad-Scrollen aktivieren
        def _on_mousewheel(event):
            if hasattr(event, 'delta') and event.delta:
                canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            elif event.num == 4:
                canvas.yview_scroll(-1, "units")
            elif event.num == 5:
                canvas.yview_scroll(1, "units")

        canvas.bind("<Enter>", lambda e: (
            canvas.bind_all("<MouseWheel>", _on_mousewheel),
            canvas.bind_all("<Button-4>", _on_mousewheel),
            canvas.bind_all("<Button-5>", _on_mousewheel)
        ))
        canvas.bind("<Leave>", lambda e: (
            canvas.unbind_all("<MouseWheel>"),
            canvas.unbind_all("<Button-4>"),
            canvas.unbind_all("<Button-5>")
        ))

        # Vertikale Trennlinie rechts neben der Box
        tk.Frame(self.master, bg="black", width=2).pack(side="left", fill="y")

        # Container für Detailansicht rechts
        self.content_frame = tk.Frame(self.master, bg="white")
        self.content_frame.pack(side="left", fill="both", expand=True)

        # Titel in Box (links)
        tk.Label(
            scroll_frame,
            text="Teilnehmerinnen\nund Teilnehmer",
            font=("Arial", 14, "bold"),
            bg="white",
            justify="center"
        ).pack(pady=(10, 5))

        # Namen aus GPX-Dateien einlesen und sortieren
        files = [f for f in os.listdir(self.gpx_path) if f.lower().endswith('.gpx')]
        names_set = set()
        for f in files:
            base = os.path.splitext(f)[0]
            parts = base.split('_')
            if len(parts) >= 2:
                last, first = parts[0], parts[1]
                names_set.add((last, first))
        names = sorted(names_set, key=lambda x: x[0])

        # Anzeige mit Abschneiden, Hover- und Click-Effekt
        max_chars = 20
        for last, first in names:
            full_name = f"{last}, {first}"
            display_name = (full_name[:max_chars-3] + "...") if len(full_name) > max_chars else full_name
            lbl = tk.Label(
                scroll_frame,
                text=display_name,
                font=("Arial", 12),
                bg="white",
                anchor="w",
                width=20
            )
            lbl.pack(fill="x", padx=10, pady=2)

            lbl.bind("<Enter>", lambda e, l=lbl: l.config(bg="#e0e0e0"))
            lbl.bind("<Leave>", lambda e, l=lbl: l.config(bg="white"))
            lbl.bind(
                "<Button-1>",
                lambda e, last=last, first=first: self.on_name_click(last, first)
            )

    def on_name_click(self, last, first):
        """
        Zeigt rechts von der Liste:
        - Überschrift mit kleinem "Teilnehmer(in): Nachname, Vorname"
        - Rotes Kreuz zum Schließen
        - Datum der GPX-Datei
        - Horizontale Linie unter dem Datum
        """
        # Alte Detail-Inhalte löschen
        for w in self.content_frame.winfo_children():
            w.destroy()

        # Header (Arial 14 Bold)
        header = tk.Label(
            self.content_frame,
            text=f"Teilnehmer(in): {last}, {first}",
            font=("Arial", 14, "bold"),
            bg="white",
            anchor="w"
        )
        header.pack(fill="x", padx=20, pady=(20, 5))

        # Close-Kreuz oben rechts
        close_btn = tk.Button(
            self.content_frame,
            text="✖",
            font=("Arial", 12, "bold"),
            fg="red",
            bg="white",
            bd=0,
            command=lambda: [w.destroy() for w in self.content_frame.winfo_children()]
        )
        close_btn.place(relx=1.0, x=-10, y=10, anchor="ne")

        # Datumsauswahl per algorithm.show_date_dialog
        importlib.reload(algorithm)
        date = algorithm.show_date_dialog(self.master, self.gpx_path, last, first)
        if date:
            # Datum-Label
            tk.Label(
                self.content_frame,
                text=f"Datum der GPX-Datei: {date}",
                font=("Arial", 14),
                bg="white",
                anchor="w"
            ).pack(fill="x", padx=20, pady=(5, 2))

            # Horizontale Trennlinie
            tk.Frame(
                self.content_frame,
                bg="black",
                height=2
            ).pack(fill="x", padx=20, pady=(0, 10))

if __name__ == "__main__":
    root = tk.Tk()
    app = WegeRadar(root)
    root.mainloop()