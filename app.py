# app.py
import tkinter as tk
from benutzeroberfläche import WegeRadar


def main():
    root = tk.Tk()
    WegeRadar(root)
    root.mainloop()


if __name__ == "__main__":
    main()