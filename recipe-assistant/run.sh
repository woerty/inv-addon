#!/bin/bash
cd /app
export FLASK_APP=app.py
export OPENAI_API_KEY="dein-api-key"

# Starte Flask API
flask run --host=0.0.0.0 --port=5000 &
echo "Flask API gestartet"

# Serve das React-Frontend
cd /app/frontend
python3 -m http.server 8080
