#!/bin/bash
# 🎬 智能视频分析系统 + AI直播间 - 完整版启动脚本
# 合并 start_live.sh 和 start_with_full_recording.sh 的所有功能

# 切换到脚本所在目录
cd "$(dirname "$0")"

# 默认端口
PORT=${1:-8082}

# OBS WebSocket配置
OBS_WS_PORT=4455
OBS_WS_PASSWORD=""  # 如果设置了密码，在这里填写

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   🎬 智能视频分析系统 + AI直播间 (完整版)            ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

# 检查虚拟环境
if [ ! -d ".venv" ]; then
    echo -e "${RED}❌ 未找到虚拟环境 .venv${NC}"
    exit 1
fi

# 检查 .env.local
if [ ! -f ".env.local" ]; then
    if [ -f ".env.local.example" ]; then
        echo -e "${YELLOW}⚠️  未找到 .env.local，从示例文件创建...${NC}"
        cp .env.local.example .env.local
    fi
fi

# 加载环境变量
if [ -f ".env.local" ]; then
    echo -e "${GREEN}✅ 加载环境变量: .env.local${NC}"
    set -a
    source .env.local
    set +a
fi

# 显示OneKey环境变量（如果存在）
if [ -n "$DASHSCOPE_API_KEY" ]; then
    echo -e "${GREEN}✅ OneKey 环境变量已加载${NC}"
    echo "  DASHSCOPE_API_KEY: ${DASHSCOPE_API_KEY:0:20}..."
    [ -n "$ANTHROPIC_API_KEY" ] && echo "  ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY:0:20}..."
fi

# 清除代理
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
echo -e "${GREEN}✅ 已清除代理设置${NC}"

# 清理旧进程
echo -e "${YELLOW}🔄 清理旧进程...${NC}"
pkill -f "integrated_system.py" 2>/dev/null
lsof -ti:$PORT | xargs kill -9 2>/dev/null
sleep 1

# 🔧 检查操作系统
OS_TYPE=$(uname -s)

if [ "$OS_TYPE" = "Linux" ]; then
    # Linux: 重新加载 v4l2loopback 模块
    echo -e "${YELLOW}🔧 重新加载 v4l2loopback 模块...${NC}"
    sudo modprobe -r v4l2loopback 2>/dev/null
    sudo modprobe v4l2loopback devices=1 video_nr=8 card_label="OBS Virtual Camera" exclusive_caps=1
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}   ✅ v4l2loopback 模块加载成功${NC}"
    fi
    sleep 1
fi

# 启动 OBS
echo -e "${YELLOW}📹 检查 OBS...${NC}"
if [ "$OS_TYPE" = "Linux" ]; then
    if ! pgrep -x "obs" > /dev/null; then
        nohup obs > /dev/null 2>&1 &
        sleep 5
        echo -e "${GREEN}   ✅ OBS 已启动${NC}"
    else
        echo -e "${GREEN}   ✅ OBS 已在运行${NC}"
    fi
else
    # macOS
    if ! pgrep -x "OBS" > /dev/null; then
        echo -e "${YELLOW}   启动 OBS...${NC}"
        open -a "OBS" 2>/dev/null
        sleep 5
    else
        echo -e "${GREEN}   ✅ OBS 已在运行${NC}"
    fi
fi

# 提示启动虚拟摄像机
echo -e "${YELLOW}🎥 启动 OBS 虚拟摄像机...${NC}"
if [ "$OS_TYPE" = "Linux" ]; then
    V4L2_USE_COUNT=$(lsmod | grep v4l2loopback | awk '{print $3}')
    if [ "$V4L2_USE_COUNT" == "0" ] || [ -z "$V4L2_USE_COUNT" ]; then
        zenity --question --title="OBS 虚拟摄像机" \
            --text="请在 OBS 中启动虚拟摄像机：\n\n工具(Tools) → 虚拟相机(Virtual Camera) → 启动(Start)\n\n完成后点击'是'继续" \
            --ok-label="是，已启动" --cancel-label="取消" \
            --width=400 2>/dev/null
        
        if [ $? -ne 0 ]; then
            echo -e "${RED}   ❌ 用户取消，退出${NC}"
            exit 1
        fi
    else
        echo -e "${GREEN}   ✅ 虚拟摄像机已激活${NC}"
    fi
else
    # macOS
    echo -e "${YELLOW}   ⏳ 请确认 OBS 中虚拟摄像机已启动${NC}"
    echo -e "${YELLOW}   （工具 → 启动虚拟摄像机）${NC}"
    echo ""
    read -p "   按任意键继续... " -n 1 -r
    echo ""
    echo -e "${GREEN}   ✅ 继续启动系统${NC}"
fi

# 激活虚拟环境
source .venv/bin/activate

# 检查obs-websocket-py (用于OBS录制控制)
echo ""
echo -e "${YELLOW}🔍 检查 obs-websocket-py...${NC}"
if python -c "import obswebsocket" 2>/dev/null; then
    echo -e "${GREEN}✅ obs-websocket-py 已安装${NC}"
    OBS_CONTROL_AVAILABLE=true
else
    echo -e "${YELLOW}⚠️  obs-websocket-py 未安装${NC}"
    echo -e "${YELLOW}   无法自动控制OBS录制${NC}"
    OBS_CONTROL_AVAILABLE=false
fi

# 启动模式选择
echo ""
echo -e "${GREEN}请选择启动模式:${NC}"
echo "1) OBS虚拟摄像头模式（推荐）"
echo "2) 摄像头模式（指定索引）"
echo "3) 视频文件模式"
echo ""
read -p "请输入选项 [1-3]: " choice

# 后台启动系统
case $choice in
    1)
        echo -e "${GREEN}🔴 启动OBS模式 (端口: $PORT)...${NC}"
        nohup python integrated_system.py --obs --port $PORT > service_output.log 2>&1 &
        PYTHON_PID=$!
        ;;
    2)
        echo ""
        echo "检测到的OBS虚拟摄像头："
        echo "  0: 1920x1080, 5fps"
        echo "  1: 1920x1080, 5fps"
        echo "  2: 1920x1080, 60fps (推荐)"
        echo ""
        read -p "请输入摄像头索引 [0-2]: " cam_index
        echo -e "${GREEN}🎥 启动摄像头模式 (索引: $cam_index, 端口: $PORT)...${NC}"
        nohup python integrated_system.py --camera $cam_index --port $PORT > service_output.log 2>&1 &
        PYTHON_PID=$!
        ;;
    3)
        read -p "请输入视频文件路径: " video_path
        if [ ! -f "$video_path" ]; then
            echo -e "${RED}错误: 文件不存在${NC}"
            exit 1
        fi
        echo -e "${GREEN}🎬 启动视频分析 (端口: $PORT)...${NC}"
        nohup python integrated_system.py --video "$video_path" --port $PORT > service_output.log 2>&1 &
        PYTHON_PID=$!
        ;;
    *)
        echo -e "${RED}无效选项，使用默认OBS模式${NC}"
        nohup python integrated_system.py --obs --port $PORT > service_output.log 2>&1 &
        PYTHON_PID=$!
        ;;
esac

echo $PYTHON_PID > service.pid
echo -e "${GREEN}✅ 系统已在后台启动 (PID: $PYTHON_PID)${NC}"

# 等待服务启动
echo ""
echo -e "${YELLOW}⏳ 等待服务启动（15秒）...${NC}"
sleep 15

# 🎤 自动启动实时语音识别
echo ""
echo -e "${YELLOW}🎤 自动启动实时语音识别...${NC}"
ASR_RESPONSE=$(curl -s -X POST "http://localhost:${PORT}/api/realtime_asr/start" 2>/dev/null)

if echo "$ASR_RESPONSE" | grep -q '"success":true' 2>/dev/null; then
    echo -e "${GREEN}✅ 语音识别已自动启动${NC}"
else
    echo -e "${YELLOW}⚠️  语音识别启动失败（可在Web界面手动启动）${NC}"
fi

# 🎬 OBS自动录制
echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   🔴 OBS 录制控制                                     ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

if [ "$OBS_CONTROL_AVAILABLE" = true ]; then
    echo -e "${YELLOW}是否启动OBS自动录制? [Y/n]: ${NC}"
    read -t 10 -n 1 -r ENABLE_OBS_REC
    echo ""
    
    if [[ ! $ENABLE_OBS_REC =~ ^[Nn]$ ]]; then
        echo -e "${YELLOW}🎬 自动启动 OBS 录制...${NC}"
        sleep 3
        
        if python obs_auto_record.py start --port $OBS_WS_PORT --password "$OBS_WS_PASSWORD" 2>/dev/null; then
            echo -e "${GREEN}✅ OBS 录制已自动启动！${NC}"
            echo -e "${GREEN}   录像将保存到 OBS 设置的路径${NC}"
            AUTO_RECORDING=true
        else
            echo -e "${YELLOW}⚠️  自动启动失败，请检查OBS WebSocket设置${NC}"
            echo "  1. OBS → 工具 → obs-websocket设置"
            echo "  2. 启用WebSocket服务器，端口: $OBS_WS_PORT"
            echo ""
            echo -e "${YELLOW}或手动在OBS中点击【开始录制】${NC}"
            AUTO_RECORDING=false
        fi
    else
        echo -e "${YELLOW}⏭️  跳过OBS录制${NC}"
        AUTO_RECORDING=false
    fi
else
    echo -e "${YELLOW}⚠️  obs-websocket-py未安装，无法自动控制OBS${NC}"
    echo -e "${YELLOW}安装: pip install obs-websocket-py${NC}"
    echo ""
    echo -e "${YELLOW}请手动在OBS中点击【开始录制】（如需录制）${NC}"
    AUTO_RECORDING=false
fi

# 打开浏览器
echo ""
echo -e "${GREEN}🌐 打开Web界面...${NC}"
WEB_URL="http://localhost:${PORT}/integrated_final_live.html"

if command -v open &> /dev/null; then
    # macOS
    open "$WEB_URL" &> /dev/null &
elif command -v xdg-open &> /dev/null; then
    # Linux
    xdg-open "$WEB_URL" &> /dev/null &
else
    echo -e "${YELLOW}⚠️  无法自动打开浏览器${NC}"
fi

# 最终报告
echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   ✅ 系统启动完成！                                   ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}📊 当前状态:${NC}"
echo "  • Web界面: $WEB_URL"
echo "  • 后台进程 PID: $PYTHON_PID"
echo "  • 语音识别: ✅ 已自动启动"

if [ "$AUTO_RECORDING" = true ]; then
    echo -e "  • OBS录制: ${GREEN}✅ 已自动启动（全程录制）${NC}"
else
    echo -e "  • OBS录制: ⏭️  未启动（可手动开启）"
fi

echo ""
echo -e "${YELLOW}💡 使用提示:${NC}"
echo "  • 查看实时日志: tail -f service_output.log"
echo "  • 查看OBS录制状态: python obs_auto_record.py status"

if [ "$AUTO_RECORDING" = true ]; then
    echo "  • 停止系统和录制: kill $PYTHON_PID && python obs_auto_record.py stop"
    echo -e "  • 或使用: ./stop_with_full_recording.sh"
else
    echo "  • 停止系统: kill $PYTHON_PID"
fi

echo ""

if [ "$AUTO_RECORDING" = true ]; then
    echo -e "${GREEN}🎥 OBS正在全程录制中...${NC}"
    echo -e "${YELLOW}   重要: 关闭时请使用停止脚本以安全停止录制${NC}"
fi

echo ""
echo -e "${YELLOW}按 Ctrl+C 或关闭终端不会停止后台服务${NC}"
echo -e "${YELLOW}如需停止，请执行上述停止命令${NC}"
echo ""
