#!/usr/bin/env bash
# Run project video analysis for stored videos captured after a given time.
# Default video root follows this repo: integrated_data/key_moments.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
VIDEO_ROOT="${VIDEO_ROOT:-"$PROJECT_ROOT/integrated_data/key_moments"}"
PORT="${PORT:-8082}"
TARGET_DATE="${TARGET_DATE:-$(date +%F)}"   # yyyy-mm-dd
AFTER_TIME="${AFTER_TIME:-09:00}"           # HH:MM, 24h
VENV_PATH="${VENV_PATH:-$PROJECT_ROOT/.venv/bin/activate}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [ ! -d "$VIDEO_ROOT" ]; then
  echo "Video root not found: $VIDEO_ROOT" >&2
  exit 1
fi

if [ -f "$VENV_PATH" ]; then
  # shellcheck disable=SC1090
  source "$VENV_PATH"
fi

mapfile -t VIDEO_FILES < <(
  find "$VIDEO_ROOT" -type f \( -iname '*.mp4' -o -iname '*.mkv' -o -iname '*.webm' \) \
    -newermt "$TARGET_DATE $AFTER_TIME" \
    -print | sort
)

if [ ${#VIDEO_FILES[@]} -eq 0 ]; then
  echo "No videos found in $VIDEO_ROOT after $TARGET_DATE $AFTER_TIME"
  exit 0
fi

echo "Found ${#VIDEO_FILES[@]} videos after $TARGET_DATE $AFTER_TIME under $VIDEO_ROOT"
echo "Using integrated_system.py with built-in 3.5 minute AI interval."

for video in "${VIDEO_FILES[@]}"; do
  echo "=== Analyzing: $video ==="
  "$PYTHON_BIN" "$PROJECT_ROOT/integrated_system.py" \
    --video "$video" \
    --port "$PORT" \
    --no-browser \
    --ai
  echo "--- Done: $video ---"
  sleep 2
done
