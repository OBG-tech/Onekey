#!/bin/bash
# 🔄 自动定时重启脚本 - 防止长时间运行导致的内存泄漏
# 使用方法: ./auto_restart.sh [重启间隔小时数,默认2小时]

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置
RESTART_INTERVAL_HOURS=${1:-2}  # 默认2小时重启一次
RESTART_INTERVAL_SECONDS=$((RESTART_INTERVAL_HOURS * 3600))
PORT=${2:-8082}  # 默认端口
LOG_FILE="auto_restart.log"

echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   🔄 自动定时重启服务                                 ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}📋 配置信息:${NC}"
echo -e "   重启间隔: ${RESTART_INTERVAL_HOURS} 小时"
echo -e "   端口: ${PORT}"
echo -e "   日志文件: ${LOG_FILE}"
echo ""

# 切换到脚本所在目录
cd "$(dirname "$0")"
source ./script_common.sh
rotate_log "${LOG_FILE}" 20

# 记录日志函数
log() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[${timestamp}] $1" | tee -a "${LOG_FILE}"
}

# 启动服务函数
start_service() {
    log "🚀 启动服务..."
    
    # 使用 nohup 在后台启动服务
    nohup ./start_live.sh <<EOF > service_output.log 2>&1 &
1
EOF
    
    local PID=$!
    log "✅ 服务已启动 (PID: ${PID})"
    echo ${PID} > service.pid
    
    # 等待服务完全启动（等待Web服务就绪）
    log "⏳ 等待Web服务就绪..."
    sleep 10
    
    # 自动启动麦克风录音
    log "🎤 正在启动麦克风录音..."
    local response=$(curl -s -X POST "http://localhost:${PORT}/api/realtime_asr/start" 2>/dev/null)
    
    if echo "${response}" | grep -q '"success":true'; then
        log "✅ 麦克风录音已自动启动"
    else
        log "⚠️  麦克风录音启动失败，可能需要手动启动"
        log "   响应: ${response}"
    fi
    
    return 0
}

# 停止服务函数
stop_service() {
    log "🛑 停止服务..."
    
    # 优先优雅停止，再超时强制结束
    graceful_pkill_pattern "integrated_system.py" 3
    release_port "${PORT}" 3
    
    # 等待进程完全停止
    sleep 2
    
    # 删除 PID 文件
    rm -f service.pid
    
    log "✅ 服务已停止"
}

# 检查服务是否运行
is_service_running() {
    pgrep -f "integrated_system.py" > /dev/null
    return $?
}

# 信号处理 - 优雅退出
cleanup() {
    echo ""
    log "⚠️  收到退出信号，正在停止..."
    stop_service
    log "👋 自动重启脚本已退出"
    exit 0
}

trap cleanup SIGINT SIGTERM

# 主循环
log "🎬 自动重启脚本启动"

# 首次启动服务
start_service
START_TIME=$(date +%s)

echo ""
echo -e "${GREEN}✅ 服务运行中...${NC}"
echo -e "${YELLOW}💡 提示:${NC}"
echo -e "   - 系统将每 ${RESTART_INTERVAL_HOURS} 小时自动重启一次"
echo -e "   - Web界面: http://localhost:${PORT}/integrated_final_live.html"
echo -e "   - 按 Ctrl+C 停止自动重启"
echo ""

# 定时检查和重启
while true; do
    # 等待一段时间
    sleep 60  # 每分钟检查一次
    
    # 检查服务是否还在运行
    if ! is_service_running; then
        log "⚠️  检测到服务已停止，正在重启..."
        start_service
        START_TIME=$(date +%s)
        continue
    fi
    
    # 计算运行时间
    CURRENT_TIME=$(date +%s)
    ELAPSED_TIME=$((CURRENT_TIME - START_TIME))
    REMAINING_TIME=$((RESTART_INTERVAL_SECONDS - ELAPSED_TIME))
    
    # 显示倒计时（每10分钟显示一次）
    if [ $((ELAPSED_TIME % 600)) -eq 0 ]; then
        REMAINING_MINUTES=$((REMAINING_TIME / 60))
        log "⏰ 运行时间: $((ELAPSED_TIME / 60)) 分钟 | 距下次重启: ${REMAINING_MINUTES} 分钟"
    fi
    
    # 检查是否需要重启
    if [ ${ELAPSED_TIME} -ge ${RESTART_INTERVAL_SECONDS} ]; then
        log "🔄 达到重启间隔 (${RESTART_INTERVAL_HOURS} 小时)，开始重启..."
        
        # 停止服务
        stop_service
        
        # 等待一小段时间
        sleep 5
        
        # 重新启动服务
        start_service
        START_TIME=$(date +%s)
        
        log "✅ 重启完成"
    fi
done
