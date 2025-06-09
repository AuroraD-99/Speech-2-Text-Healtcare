# Usa un'immagine Python slim che è una buona base per applicazioni più piccole.
FROM python:3.10-slim

# Imposta output non bufferizzato per Python. Utile per il logging in tempo reale nei container.
ENV PYTHONUNBUFFERED=1

# Imposta la directory di lavoro all'interno del container.
WORKDIR /app

# --- Configurazione del Locale Italiano ---
RUN apt-get update && \
    apt-get install -y --no-install-recommends locales ca-certificates && \
    sed -i '/it_IT.UTF-8/s/^# //' /etc/locale.gen && \
    locale-gen && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
ENV LANG=it_IT.UTF-8
ENV LANGUAGE=it_IT:it:en
ENV LC_ALL=it_IT.UTF-8
# --- Fine Configurazione Locale ---

# --- Dipendenze di Sistema Aggiuntive ---
# Le installiamo prima di installare le dipendenze Python, così PyAudio può compilare correttamente.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
        portaudio19-dev \
        pulseaudio \
        libasound-dev \
        build-essential && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
# --- Fine Dipendenze di Sistema Aggiuntive ---

# --- Installazione delle Dipendenze Python ---
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt
# --- Fine Installazione Dipendenze Python ---

# Copia il resto del codice dell'applicazione.
COPY . .

# Copia e rendi eseguibile lo script entrypoint.
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Espone le porte necessarie per la tua applicazione.
EXPOSE 8001 8003 8501

# L'ENTRYPOINT è lo script che verrà eseguito quando il container si avvia.
ENTRYPOINT ["/app/entrypoint.sh"]

# Il CMD fornisce argomenti predefiniti all'ENTRYPOINT
CMD ["bash"]
