#!/bin/sh
set -e

# Start Xvfb on :99 (required for headless=false to bypass Akamai on Sagawa)
Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp &
sleep 1

# Ensure state.json exists (bind mount may be an empty file)
[ -s /app/state.json ] || echo '{}' > /app/state.json

exec uvicorn daemon.main:app --host 0.0.0.0 --port 8020
