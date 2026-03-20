#!/bin/sh
set -e

# Start Xvfb on :99
Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp &
sleep 1

exec python -m agent.main
