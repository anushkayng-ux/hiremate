#!/bin/bash
# HireMate - double-click to start on Mac (first run installs things, 3-5 minutes)
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null; then echo "Install Python 3.11+ from https://www.python.org/downloads/ then run again."; read; exit 1; fi
[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q --upgrade pip && pip install -q -r requirements.txt
python -m uvicorn backend.app.main:app --port 8000 &
sleep 8
echo "Opening http://localhost:8501  -  sign in: muskan@hiremate.demo / recruit123"
open http://localhost:8501
cd frontend && API_URL=http://127.0.0.1:8000 python -m streamlit run app.py --server.port 8501 --server.fileWatcherType none
