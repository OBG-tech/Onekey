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

echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   ⏹️  停止系统和录制                                  ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

# 激活虚拟环境
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# 1. 停止OBS录制
echo -e "${YELLOW}[1/3] 停止 OBS 录制...${NC}"

if python3 -c "import obsws_python" 2>/dev/null && [ -f "obs_auto_record.py" ]; then
    if python3 obs_auto_record.py stop --port $OBS_WS_PORT --password "$OBS_WS_PASSWORD" 2>/dev/null; then
        echo -e "${GREEN}✅ OBS 录制已停止${NC}"
    else
        echo -e "${YELLOW}⚠️  无法自动停止OBS录制${NC}"
        echo -e "${YELLOW}   请手动在 OBS 中点击【停止录制】${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  请手动在 OBS 中点击【停止录制】${NC}"
fi

echo ""

# 2. 停止系统进程
echo -e "${YELLOW}[2/3] 停止系统进程...${NC}"

if [ -f "service.pid" ]; then
    PID=$(cat service.pid)
    if ps -p $PID > /dev/null 2>&1; then
        echo "停止进程 PID: $PID"
        kill $PID
        sleep 2
        
        # 强制停止
        if ps -p $PID > /dev/null 2>&1; then
            echo "强制停止..."
            kill -9 $PID
        fi
        
        rm -f service.pid
        echo -e "${GREEN}✅ 系统进程已停止${NC}"
    else
        echo -e "${YELLOW}⚠️  进程已不在运行${NC}"
        rm -f service.pid
    fi
else
    echo -e "${YELLOW}⚠️  未找到 service.pid，尝试杀掉所有相关进程${NC}"
    pkill -f "integrated_system.py"
    sleep 1
    echo -e "${GREEN}✅ 清理完成${NC}"
fi

echo ""

# 3. 显示录制统计
echo -e "${YELLOW}[3/3] 录制统计...${NC}"

# 查找最新的OBS录像
if [ -d "$HOME/视频" ]; then
    LATEST_VIDEO=$(find "$HOME/视频" -type f \( -name "*.mkv" -o -name "*.mp4" \) -printf '%T@ %p\n' 2>/dev/null | sort -rn | head -1 | awk '{print $2}')
    
    if [ -n "$LATEST_VIDEO" ]; then
        SIZE=$(du -h "$LATEST_VIDEO" 2>/dev/null | awk '{print $1}')
        BASENAME=$(basename "$LATEST_VIDEO")
        echo -e "${GREEN}📹 最新录像:${NC}"
        echo "  文件: $BASENAME"
        echo "  大小: $SIZE"
        echo "  路径: $LATEST_VIDEO"
    fi
fi

echo ""

# 查看关键时刻统计
if [ -d "integrated_data/key_moments" ]; then
    KM_COUNT=$(find integrated_data/key_moments -name "*.mp4" 2>/dev/null | wc -l)
    KM_SIZE=$(du -sh integrated_data/key_moments 2>/dev/null | awk '{print $1}')
    echo -e "${GREEN}🎬 关键时刻:${NC}"
    echo "  数量: $KM_COUNT 个"
    echo "  大小: $KM_SIZE"
fi

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   ✅ 停止完成                                         ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}💡 录像文件保存位置:${NC}"
echo "  • OBS完整录像: ~/视频/ (或OBS设置的路径)"
echo "  • 关键时刻视频: integrated_data/key_moments/"
echo ""
