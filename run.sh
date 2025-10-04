#!/bin/bash

# Skrypt do uruchomienia FastAPI aplikacji - System Zarządzania Satelitami

echo "🚀 Uruchamianie Systemu Śledzenia Orbit Satelitarnych.."
echo ""

# Aktywuj środowisko wirtualne
source .venv/bin/activate

# Uruchom serwer z modułu API
uvicorn satelity_api:system_api --reload --host 0.0.0.0 --port 8000

# Info
echo ""
echo "Serwer uruchomiony: http://localhost:8000"
echo "Dokumentacja API: http://localhost:8000/docs"
echo "Alternatywna dokumentacja: http://localhost:8000/redoc"

