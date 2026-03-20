#!/bin/bash
# Convert WAV call recordings to MP3, then delete originals.
# Runs inside raspbx-core container via cron.
set -euo pipefail

MONITOR_DIR="${1:-/var/spool/asterisk/monitor}"

shopt -s nullglob globstar
files=("$MONITOR_DIR"/**/*.wav)
shopt -u nullglob globstar

if [[ ${#files[@]} -eq 0 ]]; then
  exit 0
fi

converted=0
failed=0
for wav in "${files[@]}"; do
  mp3="${wav%.wav}.mp3"
  if lame -b 192 -m m --quiet "$wav" "$mp3" 2>/dev/null; then
    rm -f "$wav"
    ((converted++))
  else
    echo "WARN: failed to convert $wav" >&2
    ((failed++))
  fi
done

echo "recording-mp3: converted=$converted failed=$failed"
