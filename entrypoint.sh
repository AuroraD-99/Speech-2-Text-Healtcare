#!/bin/bash
set -e

# Esegui lo script di inizializzazione DB
echo "Eseguo inizializzazione database..."
python ./init_db.py

echo "Inizializzazione completata. Avvio comando principale..."

# Esegui il comando passato a docker run o docker-compose
exec "$@"
