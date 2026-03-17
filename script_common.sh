#!/bin/bash
# Ubuntu runtime helpers for OneKey scripts.

DEFAULT_PORT=8082
DEFAULT_OBS_WS_PORT=4455
DEFAULT_LOG_MAX_MB=20

ensure_venv() {
    if [ ! -d ".venv" ]; then
        echo "❌ 未找到虚拟环境 .venv"
        echo "请先运行: ./install_ubuntu.sh"
        return 1
    fi
    return 0
}

ensure_env_file() {
    if [ ! -f ".env.local" ] && [ -f ".env.local.example" ]; then
        cp .env.local.example .env.local
    fi
}

load_env_file() {
    if [ -f ".env.local" ]; then
        set -a
        # shellcheck disable=SC1091
        source .env.local
        set +a
    fi
}

clear_proxy_env() {
    unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
}

rotate_log() {
    local log_file="$1"
    local max_mb="${2:-$DEFAULT_LOG_MAX_MB}"
    if [ -f "$log_file" ]; then
        local size_mb
        size_mb=$(du -m "$log_file" 2>/dev/null | awk '{print $1}')
        if [ -n "$size_mb" ] && [ "$size_mb" -ge "$max_mb" ]; then
            mv "$log_file" "${log_file}.$(date +%Y%m%d_%H%M%S).bak"
        fi
    fi
}

graceful_kill_by_pid() {
    local pid="$1"
    local timeout="${2:-3}"
    if [ -z "$pid" ]; then
        return 0
    fi
    if ps -p "$pid" > /dev/null 2>&1; then
        kill "$pid" 2>/dev/null
        for _ in $(seq 1 "$timeout"); do
            if ! ps -p "$pid" > /dev/null 2>&1; then
                return 0
            fi
            sleep 1
        done
        kill -9 "$pid" 2>/dev/null
    fi
}

graceful_pkill_pattern() {
    local pattern="$1"
    local timeout="${2:-3}"
    if [ -z "$pattern" ]; then
        return 0
    fi
    pkill -f "$pattern" 2>/dev/null
    for _ in $(seq 1 "$timeout"); do
        if ! pgrep -f "$pattern" > /dev/null 2>&1; then
            return 0
        fi
        sleep 1
    done
    pgrep -f "$pattern" | while read -r pid; do
        kill -9 "$pid" 2>/dev/null
    done
}

release_port() {
    local port="$1"
    local timeout="${2:-3}"
    local pids
    pids=$(lsof -ti:"$port" 2>/dev/null)
    if [ -z "$pids" ]; then
        return 0
    fi
    for pid in $pids; do
        graceful_kill_by_pid "$pid" "$timeout"
    done
}
