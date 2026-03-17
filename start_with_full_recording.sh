#!/bin/bash
# 完整录像启动脚本 - 自动开启OBS完整录制
# OBS从启动就开始录制，直到手动停止
# 用法: ./start_with_full_recording.sh [端口号]

# 切换到脚本所在目录
cd "$(dirname "$0")"
source ./script_common.sh

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
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   🎬 完整录像模式 - OBS全程不间断录制                ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

ensure_venv || exit 1

if [ ! -f ".env.local" ] && [ -f ".env.local.example" ]; then
    echo -e "${YELLOW}⚠️  未找到 .env.local，从示例文件创建...${NC}"
fi
ensure_env_file

# 加载环境变量
if [ -f ".env.local" ]; then
    echo -e "${GREEN}✅ 加载环境变量${NC}"
    load_env_file
fi

# 清除代理
clear_proxy_env

# 清理旧进程
echo -e "${YELLOW}🔄 清理旧进程...${NC}"
graceful_pkill_pattern "integrated_system.py" 3
release_port "$PORT" 3

# 重新加载 v4l2loopback
echo -e "${YELLOW}🔧 重新加载 v4l2loopback 模块...${NC}"
sudo modprobe -r v4l2loopback 2>/dev/null
sudo modprobe v4l2loopback devices=1 video_nr=8 card_label="OBS Virtual Camera" exclusive_caps=1
if [ $? -eq 0 ]; then
    echo -e "${GREEN}   ✅ v4l2loopback 模块加载成功${NC}"
fi
sleep 1

# 启动 OBS
echo -e "${YELLOW}📹 启动 OBS...${NC}"
if ! pgrep -x "obs" > /dev/null; then
    nohup obs > /dev/null 2>&1 &
    sleep 5
    echo -e "${GREEN}   ✅ OBS 已启动${NC}"
else
    echo -e "${GREEN}   ✅ OBS 已在运行${NC}"
fi

# 提示启动虚拟摄像机
echo -e "${YELLOW}🎥 启动 OBS 虚拟摄像机...${NC}"
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

# 激活虚拟环境
source .venv/bin/activate
rotate_log "service_output.log" 20

# 检查是否安装了obs-websocket-py
echo ""
echo -e "${YELLOW}🔍 检查 obs-websocket-py...${NC}"
if python3 -c "import obsws_python" 2>/dev/null; then
    echo -e "${GREEN}✅ obs-websocket-py 已安装${NC}"
    OBS_CONTROL_AVAILABLE=true
else
    echo -e "${YELLOW}⚠️  obs-websocket-py 未安装${NC}"
    echo -e "${YELLOW}   无法自动控制OBS录制${NC}"
    echo ""
    echo -e "${YELLOW}是否现在安装? [Y/n]: ${NC}"
    read -r INSTALL_OBSWS
    if [ "$INSTALL_OBSWS" != "n" ] && [ "$INSTALL_OBSWS" != "N" ]; then
        echo -e "${YELLOW}📦 安装 obs-websocket-py...${NC}"
        pip install obs-websocket-py
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✅ 安装成功${NC}"
            OBS_CONTROL_AVAILABLE=true
        else
            echo -e "${RED}❌ 安装失败${NC}"
            OBS_CONTROL_AVAILABLE=false
        fi
    else
        OBS_CONTROL_AVAILABLE=false
    fi
fi

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

# 自动启动语音识别
echo ""
echo -e "${YELLOW}🎤 自动启动实时语音识别...${NC}"
ASR_RESPONSE=$(curl -s -X POST "http://localhost:${PORT}/api/realtime_asr/start" 2>/dev/null)

if echo "$ASR_RESPONSE" | grep -q '"success":true' 2>/dev/null; then
    echo -e "${GREEN}✅ 语音识别已自动启动${NC}"
else
    echo -e "${YELLOW}⚠️  语音识别启动失败（可在Web界面手动启动）${NC}"
fi

# 🎬 自动启动OBS录制
echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   🔴 启动 OBS 完整录制                                ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

if [ "$OBS_CONTROL_AVAILABLE" = true ]; then
    echo -e "${YELLOW}🎬 自动启动 OBS 录制...${NC}"
    
    # 等待OBS完全就绪
    sleep 3
    
    # 使用Python脚本启动录制
    if python3 obs_auto_record.py start --port $OBS_WS_PORT --password "$OBS_WS_PASSWORD" 2>/dev/null; then
        echo -e "${GREEN}✅ OBS 录制已自动启动！${NC}"
        echo -e "${GREEN}   录像将保存到 OBS 设置的路径${NC}"
        AUTO_RECORDING=true
    else
        echo -e "${YELLOW}⚠️  自动启动失败，请检查OBS WebSocket设置${NC}"
        echo ""
        echo -e "${YELLOW}请在 OBS 中：${NC}"
        echo "  1. 工具 → obs-websocket设置"
        echo "  2. 启用WebSocket服务器"
        echo "  3. 端口设置为 $OBS_WS_PORT"
        echo ""
        echo -e "${YELLOW}然后手动点击 OBS 的【开始录制】按钮${NC}"
        AUTO_RECORDING=false
    fi
else
    echo -e "${YELLOW}⚠️  无法自动控制 OBS${NC}"
    echo -e "${YELLOW}请手动在 OBS 中点击【开始录制】按钮${NC}"
    AUTO_RECORDING=false
fi

# 打开浏览器
echo ""
echo -e "${GREEN}🌐 打开Web界面...${NC}"
WEB_URL="http://localhost:${PORT}/integrated_final_live.html"
xdg-open "$WEB_URL" 2>/dev/null || sensible-browser "$WEB_URL" 2>/dev/null || firefox "$WEB_URL" 2>/dev/null

# 最终报告
echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   ✅ 系统启动完成！                                   ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}📊 当前状态:${NC}"
echo "  • Web界面: $WEB_URL"
echo "  • 后台进程 PID: $PYTHON_PID"
echo "  • 语音识别: 已自动启动"

if [ "$AUTO_RECORDING" = true ]; then
    echo -e "  • OBS录制: ${GREEN}✅ 已自动启动（全程录制）${NC}"
else
    echo -e "  • OBS录制: ${YELLOW}⚠️  请手动启动${NC}"
fi

echo ""
echo -e "${YELLOW}💡 使用提示:${NC}"
echo "  • 查看实时日志: tail -f service_output.log"
echo "  • 查看OBS录制状态: python3 obs_auto_record.py status"
echo "  • 停止系统和录制: ./stop_with_full_recording.sh"
echo "  • 或直接停止: kill $PYTHON_PID"
echo ""

if [ "$AUTO_RECORDING" = true ]; then
    echo -e "${GREEN}🎥 OBS正在全程录制中...${NC}"
    echo -e "${GREEN}   关闭系统前请运行 ./stop_with_full_recording.sh 以安全停止录制${NC}"
else
    echo -e "${YELLOW}📹 重要提醒:${NC}"
    echo -e "${RED}   请在 OBS 中手动点击【开始录制】按钮！${NC}"
fi
echo ""
