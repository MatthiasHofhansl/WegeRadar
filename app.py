import tkinter as tk
from benutzeroberfläche import WegeRadar

def main():
    # Erstelle das Hauptfenster und starte die Benutzeroberfläche
    root = tk.Tk()
    app = WegeRadar(root)
    root.mainloop()

if __name__ == "__main__":
    main()