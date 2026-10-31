#!/usr/bin/env bash
# Starts the API (internal, port 8000) and the Streamlit app (public, port ${PORT:-7860}).
set -e
cd "$(dirname "$0")"
python3 -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 &
API_PID=$!
for i in $(seq 1 60); do
  python3 - 2>/dev/null <<'EOF' && break || sleep 1
import urllib.request; urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=1)
EOF
done
cd frontend
export API_URL=${API_URL:-http://127.0.0.1:8000}
exec streamlit run app.py --server.port "${PORT:-7860}" --server.address 0.0.0.0 --server.fileWatcherType none
