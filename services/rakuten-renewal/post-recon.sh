#!/bin/bash
# post-recon.sh — Schedule the next recon run based on state.json
# Called after each successful recon session.
set -euo pipefail

STATE_FILE="$(dirname "$0")/state.json"

if [[ ! -f "$STATE_FILE" ]]; then
    echo "No state.json found, skipping reschedule"
    exit 0
fi

NEXT=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('next_recon_at', ''))")

if [[ -z "$NEXT" ]]; then
    echo "No next_recon_at in state.json, skipping"
    exit 0
fi

echo "Scheduling next recon at: $NEXT"

# Create a transient systemd timer for the exact Gemini-chosen timestamp
sudo systemd-run \
    --on-calendar="$NEXT" \
    --unit="shinbee-rakuten-recon-next" \
    --description="SHINBEE Rakuten next recon (Gemini-scheduled)" \
    /usr/bin/systemctl start shinbee-rakuten@recon.service

echo "Transient timer created for $NEXT"
