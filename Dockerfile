FROM python:3.11-slim

# Installiere Systempakete inkl. Tkinter & X11 für GUI
RUN apt-get update && apt-get install -y \
    python3-tk tk libx11-6 libxext6 libxrender1 libsm6 libice6 \
    && rm -rf /var/lib/apt/lists/*

# Arbeitsverzeichnis setzen
WORKDIR /app

# Projektdateien kopieren
COPY . .

# Abhängigkeiten installieren
RUN pip install --no-cache-dir gpxpy requests

# App starten
CMD ["python", "app.py"]
