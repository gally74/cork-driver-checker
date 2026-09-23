#!/usr/bin/env bash
# Start the Cork Driver Checker in Codespaces / Linux.
set -e
cd "$(dirname "$0")"
pip install -q -r requirements.txt
exec streamlit run streamlit_app.py \
  --server.address 0.0.0.0 \
  --server.port 8501 \
  --server.headless true \
  --server.enableCORS false \
  --server.enableXsrfProtection false \
  --browser.gatherUsageStats false
