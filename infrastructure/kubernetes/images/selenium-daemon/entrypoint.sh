#!/bin/sh
set -e

# Start Xvfb on :99 (headless=false required — Akamai blocks headless Chrome on Sagawa)
Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp &
sleep 1

# Ensure state.json exists
[ -s /app/state/state.json ] || echo '{}' > /app/state/state.json

exec uvicorn daemon.main:app --host 0.0.0.0 --port 8020
