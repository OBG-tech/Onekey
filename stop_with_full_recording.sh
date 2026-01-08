#!/bin/bash
# 停止录制脚本 - 安全停止OBS录制和系统
# 用法: ./stop_with_full_recording.sh

cd "$(dirname "$0")"

# OBS WebSocket配置
OBS_WS_PORT=4455
OBS_WS_PASSWORD=""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}======================================================${NC}"
echo -e "${BLUE}   ?  停止系统和录制                                  ${NC}"
echo -e "${BLUE}======================================================${NC}"
echo ""

# 激活虚拟环境
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# 1. 停止 OBS 录制
echo -e "${YELLOW}[1/2] 停止 OBS 录制...${NC}"

if python3 -c "import obsws_python" 2>/dev/null && [ -f "obs_auto_record.py" ]; then
    if python3 obs_auto_record.py stop --port $OBS_WS_PORT --password "$OBS_WS_PASSWORD" 2>/dev/null; then
        echo -e "${GREEN}? OBS 录制已停止${NC}"
    else
        echo -e "${YELLOW}??  无法自动停止OBS录制${NC}"
        echo -e "${YELLOW}   请手动在 OBS 中点击【停止录制】。${NC}"
    fi
else
    echo -e "${YELLOW}??  请手动在 OBS 中点击【停止录制】。${NC}"
fi

echo ""

# 2. 停止系统进程 (并等待视频合成)
echo -e "${YELLOW}[2/2] 停止系统进程 (等待视频合成)...${NC}"

if [ -f "service.pid" ]; then
    PID=$(cat service.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "停止进程 PID: $PID"
        kill $PID
        
        # 给一定时间让程序合成视频 (recordings文件夹)
        # 多摄像头录制需要时间进行ffmpeg合并，请勿强制关闭太快
        echo "等待后台任务完成..."
        for i in {1..5}; do
            if ! ps -p $PID > /dev/null 2>&1; then
                break
            fi
            sleep 1
        done
        
        # 强制停止
        if ps -p $PID > /dev/null 2>&1; then
            echo "服务未响应，强制停止..."
            kill -9 $PID
        fi
        
        rm -f service.pid
        echo -e "${GREEN}? 系统进程已停止${NC}"
    else
        echo -e "${YELLOW}??  进程已不在运行${NC}"
        rm -f service.pid
    fi
else
    echo -e "${YELLOW}??  没找到 service.pid，尝试杀掉所有相关进程${NC}"
    pkill -f "integrated_system.py"
    sleep 1
    echo -e "${GREEN}? 清理完成${NC}"
fi

echo ""
echo -e "${BLUE}======================================================${NC}"
echo -e "${BLUE}   ? 停止完成                                         ${NC}"
echo -e "${BLUE}======================================================${NC}"
