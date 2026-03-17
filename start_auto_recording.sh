#!/bin/bash
# 一键启动脚本 - 自动开启录音识别和OBS录制
# 用法: ./start_auto_recording.sh [端口号]

# 切换到脚本所在目录
cd "$(dirname "$0")"
source ./script_common.sh

# 默认端口
PORT=${1:-8082}

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   🎬 智能视频分析系统 - 自动录音录像模式             ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

ensure_venv || exit 1

if [ ! -f ".env.local" ] && [ -f ".env.local.example" ]; then
    echo -e "${YELLOW}⚠️  未找到 .env.local，从示例文件创建...${NC}"
    echo -e "${YELLOW}   请编辑 .env.local 填入您的 DASHSCOPE_API_KEY${NC}"
fi
ensure_env_file

# 加载环境变量
if [ -f ".env.local" ]; then
    echo -e "${GREEN}✅ 加载环境变量: .env.local${NC}"
    load_env_file
fi

# 检查 API Key
if [ -z "$DASHSCOPE_API_KEY" ]; then
    echo -e "${YELLOW}⚠️  DASHSCOPE_API_KEY 未设置，部分AI功能将不可用${NC}"
    echo -e "${YELLOW}   请编辑 .env.local 添加您的 API Key${NC}"
fi

# 清除代理环境变量
clear_proxy_env
echo -e "${GREEN}✅ 已清除代理设置${NC}"

# 杀掉之前的进程
echo -e "${YELLOW}🔄 清理旧进程...${NC}"
graceful_pkill_pattern "integrated_system.py" 3
release_port "$PORT" 3

# 🔧 重新加载 v4l2loopback 模块
echo -e "${YELLOW}🔧 重新加载 v4l2loopback 模块...${NC}"
sudo modprobe -r v4l2loopback 2>/dev/null
sudo modprobe v4l2loopback devices=1 video_nr=8 card_label="OBS Virtual Camera" exclusive_caps=1
if [ $? -eq 0 ]; then
    echo -e "${GREEN}   ✅ v4l2loopback 模块加载成功${NC}"
else
    echo -e "${YELLOW}   ⚠️  v4l2loopback 模块加载失败，将尝试继续...${NC}"
fi
sleep 1

# 📹 自动启动 OBS（如果未运行）
echo -e "${YELLOW}📹 检查 OBS 状态...${NC}"
if ! pgrep -x "obs" > /dev/null; then
    echo -e "${YELLOW}   启动 OBS...${NC}"
    nohup obs > /dev/null 2>&1 &
    sleep 3
    echo -e "${GREEN}   ✅ OBS 已启动${NC}"
else
    echo -e "${GREEN}   ✅ OBS 已在运行${NC}"
fi

# 🎬 启动 OBS 虚拟摄像机
echo -e "${YELLOW}🎥 启动 OBS 虚拟摄像机...${NC}"
V4L2_USE_COUNT=$(lsmod | grep v4l2loopback | awk '{print $3}')
if [ "$V4L2_USE_COUNT" == "0" ] || [ -z "$V4L2_USE_COUNT" ]; then
    # 使用 zenity 弹窗提醒用户
    zenity --question --title="OBS 虚拟摄像机" \
        --text="请在 OBS 中启动虚拟摄像机：\n\n工具(Tools) → 虚拟相机(Virtual Camera) → 启动(Start)\n\n完成后点击'是'继续" \
        --ok-label="是，已启动" --cancel-label="取消" \
        --width=400 2>/dev/null

    if [ $? -ne 0 ]; then
        echo -e "${RED}   ❌ 用户取消，退出${NC}"
        exit 1
    fi
    
    sleep 1
    V4L2_USE_COUNT=$(lsmod | grep v4l2loopback | awk '{print $3}')
    if [ "$V4L2_USE_COUNT" != "0" ] && [ -n "$V4L2_USE_COUNT" ]; then
        echo -e "${GREEN}   ✅ 虚拟摄像机已激活${NC}"
    else
        echo -e "${YELLOW}   ⚠️  虚拟摄像机可能未激活，将尝试继续...${NC}"
    fi
else
    echo -e "${GREEN}   ✅ 虚拟摄像机已激活${NC}"
fi

# 🎥 启动 OBS 录制（使用 obs-cli 或 WebSocket）
echo -e "${YELLOW}🔴 启动 OBS 录制...${NC}"

# 方法1: 尝试使用 obs-cli (如果已安装)
if command -v obs-cli &> /dev/null; then
    obs-cli recording start 2>/dev/null
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}   ✅ OBS 录制已通过 obs-cli 启动${NC}"
    else
        echo -e "${YELLOW}   ⚠️  obs-cli 启动失败，请手动在 OBS 中点击开始录制${NC}"
    fi
else
    # 方法2: 提醒用户手动启动
    echo -e "${YELLOW}   ⚠️  未安装 obs-cli，请手动在 OBS 中点击【开始录制】按钮${NC}"
    echo -e "${YELLOW}   或者安装 obs-cli: pip install obs-cli${NC}"
fi

# 激活虚拟环境
source .venv/bin/activate
rotate_log "service_output.log" 20

# 启动模式选择
echo ""
echo -e "${GREEN}请选择启动模式:${NC}"
echo "1) OBS虚拟摄像头模式（推荐）"
echo "2) 摄像头模式（前置摄像头）"
echo "3) 视频文件模式"
echo ""
read -p "请输入选项 [1-3]: " choice

# 后台启动系统
case $choice in
    1)
        echo -e "${GREEN}🔴 启动OBS模式 (端口: $PORT)...${NC}"
        nohup python3 integrated_system.py --obs --port $PORT > service_output.log 2>&1 &
        PYTHON_PID=$!
        ;;
    2)
        echo -e "${GREEN}🎥 启动摄像头模式 (端口: $PORT)...${NC}"
        nohup python3 integrated_system.py --camera 0 --port $PORT > service_output.log 2>&1 &
        PYTHON_PID=$!
        ;;
    3)
        read -p "请输入视频文件路径: " video_path
        if [ ! -f "$video_path" ]; then
            echo -e "${RED}错误: 文件不存在${NC}"
            exit 1
        fi
        echo -e "${GREEN}🎬 启动视频分析 (端口: $PORT)...${NC}"
        nohup python3 integrated_system.py --video "$video_path" --port $PORT > service_output.log 2>&1 &
        PYTHON_PID=$!
        ;;
    *)
        echo -e "${RED}无效选项，使用默认OBS模式${NC}"
        nohup python3 integrated_system.py --obs --port $PORT > service_output.log 2>&1 &
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
RESPONSE=$(curl -s -X POST "http://localhost:${PORT}/api/realtime_asr/start" 2>/dev/null)

if echo "$RESPONSE" | grep -q '"success":true' 2>/dev/null; then
    echo -e "${GREEN}✅ 语音识别已自动启动${NC}"
else
    echo -e "${YELLOW}⚠️  语音识别启动失败，可能原因：${NC}"
    echo -e "${YELLOW}   1. 服务还未完全启动（请稍后在Web界面手动点击）${NC}"
    echo -e "${YELLOW}   2. 麦克风权限问题${NC}"
    echo -e "${YELLOW}   3. PyAudio未正确安装${NC}"
    echo ""
    echo -e "${YELLOW}   响应: ${RESPONSE}${NC}"
fi

# 打开浏览器
echo ""
echo -e "${GREEN}🌐 打开Web界面...${NC}"
WEB_URL="http://localhost:${PORT}/integrated_final_live.html"
xdg-open "$WEB_URL" 2>/dev/null || sensible-browser "$WEB_URL" 2>/dev/null || firefox "$WEB_URL" 2>/dev/null

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   ✅ 系统启动完成！                                   ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}📊 状态检查:${NC}"
echo -e "   • Web界面: ${WEB_URL}"
echo -e "   • 后台进程 PID: ${PYTHON_PID}"
echo -e "   • OBS 录制: ${YELLOW}请确认 OBS 中已开始录制${NC}"
echo -e "   • 语音识别: ${GREEN}已自动启动${NC}"
echo ""
echo -e "${YELLOW}💡 使用提示:${NC}"
echo -e "   • 查看日志: tail -f service_output.log"
echo -e "   • 停止系统: kill ${PYTHON_PID}"
echo -e "   • 或运行: pkill -f integrated_system.py"
echo ""
echo -e "${YELLOW}📹 重要提醒:${NC}"
echo -e "   ${RED}请在 OBS 中手动点击【开始录制】按钮，确保完整录像！${NC}"
echo ""
