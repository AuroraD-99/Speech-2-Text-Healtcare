# Usa un'immagine Python slim come base leggera
FROM python:3.10-slim

# Output Python non bufferizzato (utile per logging in real-time)
ENV PYTHONUNBUFFERED=1

# Imposta la directory di lavoro
WORKDIR /app

# --- Configurazione del locale Italiano ---
RUN apt-get update && \
    apt-get install -y --no-install-recommends locales ca-certificates && \
    sed -i '/it_IT.UTF-8/s/^# //' /etc/locale.gen && \
    locale-gen && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

ENV LANG=it_IT.UTF-8
ENV LANGUAGE=it_IT:it:en
ENV LC_ALL=it_IT.UTF-8
# --- Fine locale ---

# Installa dipendenze Python (assicurati che requirements.txt non contenga pyaudio)
COPY requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir -r requirements.txt

# 🔽 Scarica il modello spaCy italiano
RUN python -m spacy download it_core_news_sm

# Copia tutto il codice nel container
COPY . .

# Copia e rende eseguibile lo script di entrypoint
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Espone le porte usate dalla tua app
EXPOSE 8001 8003 8501

# Imposta lo script di entrypoint e il comando default
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["bash"]
