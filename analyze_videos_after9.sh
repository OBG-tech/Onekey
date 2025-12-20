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
NO_WINDOW="${NO_WINDOW:-1}"             # 1=禁用本地窗口（推荐服务器/无显示场景）
AI_FLAG="${AI_FLAG:-1}"                # 1=启用AI分析（沿用项目3.5分钟切片）
EXTRA_ARGS=()
LOG_DIR="${LOG_DIR:-"$PROJECT_ROOT/integrated_data/logs"}"
LOG_FILE="${LOG_FILE:-"$LOG_DIR/analysis.log"}"

# Headless 环境下避免 Qt 报错退出
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-offscreen}"

if [ ! -d "$VIDEO_ROOT" ]; then
  echo "Video root not found: $VIDEO_ROOT" >&2
  exit 1
fi

mkdir -p "$LOG_DIR"
touch "$LOG_FILE"

log_line() {
  # $1: message
  printf '%s %s\n' "$(date '+%F %T')" "$1" | tee -a "$LOG_FILE"
}

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
log_line "=== Batch start: ${#VIDEO_FILES[@]} videos after $TARGET_DATE $AFTER_TIME (root=$VIDEO_ROOT, port=$PORT) ==="

for video in "${VIDEO_FILES[@]}"; do
  log_line ">>> Start analyzing: $video"
  args=(
    "$PROJECT_ROOT/integrated_system.py"
    --video "$video"
    --port "$PORT"
    --no-browser
  )
  if [ "$NO_WINDOW" -eq 1 ] 2>/dev/null; then
    args+=(--no-window)
  fi
  if [ "$AI_FLAG" -eq 1 ] 2>/dev/null; then
    args+=(--ai)
  fi
  "$PYTHON_BIN" "${args[@]}" "${EXTRA_ARGS[@]}" 2>&1 | tee -a "$LOG_FILE"
  status=${PIPESTATUS[0]}
  if [ "$status" -ne 0 ]; then
    log_line "!!! Failed: $video (exit=$status)"
    exit "$status"
  fi
  log_line "<<< Done: $video"
  sleep 2
done

log_line "=== Batch complete ==="
