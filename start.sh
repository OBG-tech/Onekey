#!/bin/bash
# 一键启动脚本 - 启动智能视频分析系统并打开日志终端
# 用法: ./start.sh [端口号]

# 切换到脚本所在目录
cd "$(dirname "$0")"

# 默认端口
PORT=${1:-8083}

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   🎬 智能视频分析与人脸追踪整合系统                   ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

# 检查虚拟环境
if [ ! -d ".venv" ]; then
    echo -e "${RED}❌ 未找到虚拟环境 .venv${NC}"
    echo -e "${YELLOW}请先运行: ./install_ubuntu.sh${NC}"
    exit 1
fi

# 检查 .env.local 是否存在
if [ ! -f ".env.local" ]; then
    if [ -f ".env.local.example" ]; then
        echo -e "${YELLOW}⚠️  未找到 .env.local，从示例文件创建...${NC}"
        cp .env.local.example .env.local
        echo -e "${YELLOW}   请编辑 .env.local 填入您的 DASHSCOPE_API_KEY${NC}"
    fi
fi

# 加载环境变量
if [ -f ".env.local" ]; then
    echo -e "${GREEN}✅ 加载环境变量: .env.local${NC}"
    set -a
    source .env.local
    set +a
fi

# 检查 API Key
if [ -z "$DASHSCOPE_API_KEY" ]; then
    echo -e "${YELLOW}⚠️  DASHSCOPE_API_KEY 未设置，部分AI功能将不可用${NC}"
    echo -e "${YELLOW}   请编辑 .env.local 添加您的 API Key${NC}"
fi

# 清除代理环境变量 (避免GNOME系统代理干扰API调用)
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY no_proxy NO_PROXY
echo -e "${GREEN}✅ 已清除代理设置${NC}"

# 杀掉之前的进程
echo -e "${YELLOW}🔄 清理旧进程...${NC}"
pkill -f "integrated_system.py" 2>/dev/null
sleep 1

# 释放端口
lsof -ti:$PORT | xargs kill -9 2>/dev/null
sleep 1

# 🔧 重新加载 v4l2loopback 模块（确保虚拟摄像机能正常启动）
echo -e "${YELLOW}🔧 重新加载 v4l2loopback 模块...${NC}"
sudo modprobe -r v4l2loopback 2>/dev/null
sudo modprobe v4l2loopback devices=1 video_nr=8 card_label="OBS Virtual Camera" exclusive_caps=1
if [ $? -eq 0 ]; then
    echo -e "${GREEN}   ✅ v4l2loopback 模块加载成功${NC}"
else
    echo -e "${YELLOW}   ⚠️  v4l2loopback 模块加载失败，将尝试继续...${NC}"
fi
sleep 1

# 自动启动 OBS 虚拟摄像机
echo -e "${YELLOW}📹 检查 OBS 虚拟摄像机...${NC}"

# 检查 v4l2loopback 模块是否已激活
V4L2_USE_COUNT=$(lsmod | grep v4l2loopback | awk '{print $3}')
if [ "$V4L2_USE_COUNT" != "0" ] && [ -n "$V4L2_USE_COUNT" ]; then
    echo -e "${GREEN}   ✅ OBS 虚拟摄像机模块已加载${NC}"
else
    # 虚拟摄像机未激活，需要启动 OBS
    if ! pgrep -x "obs" > /dev/null; then
        echo -e "${YELLOW}   启动 OBS...${NC}"
        nohup obs > /dev/null 2>&1 &
        sleep 3
    fi

    # 使用 zenity 弹窗提醒用户（与 LAUNCH_GUI.py 一致）
    echo -e "${YELLOW}   ⏳ 请在 OBS 中启动虚拟摄像机...${NC}"
    zenity --question --title="OBS 虚拟摄像机" \
        --text="请在 OBS 中启动虚拟摄像机：\n\n工具(Tools) → 虚拟相机(Virtual Camera) → 启动(Start)\n\n完成后点击'是'继续" \
        --ok-label="是，已启动" --cancel-label="取消" \
        --width=400 2>/dev/null

    if [ $? -ne 0 ]; then
        echo -e "${RED}   ❌ 用户取消，退出${NC}"
        exit 1
    fi

    # 再次检查
    sleep 1
    V4L2_USE_COUNT=$(lsmod | grep v4l2loopback | awk '{print $3}')
    if [ "$V4L2_USE_COUNT" != "0" ] && [ -n "$V4L2_USE_COUNT" ]; then
        echo -e "${GREEN}   ✅ 虚拟摄像机已激活${NC}"
    else
        echo -e "${RED}   ⚠️  虚拟摄像机可能未激活，将尝试继续...${NC}"
    fi
fi

# 激活虚拟环境
source .venv/bin/activate

# 启动模式选择
echo ""
echo -e "${GREEN}请选择启动模式:${NC}"
echo "1) OBS虚拟摄像头模式"
echo "2) 摄像头模式（前置摄像头）"
echo "3) 视频文件模式"
echo ""
read -p "请输入选项 [1-3]: " choice

case $choice in
    1)
        echo -e "${GREEN}🔴 启动OBS模式 (端口: $PORT)...${NC}"
        python3 integrated_system.py --obs --port $PORT
        ;;
    2)
        echo -e "${GREEN}🎥 启动摄像头模式 (端口: $PORT)...${NC}"
        python3 integrated_system.py --camera 0 --port $PORT
        ;;
    3)
        read -p "请输入视频文件路径: " video_path
        if [ ! -f "$video_path" ]; then
            echo -e "${RED}错误: 文件不存在${NC}"
            exit 1
        fi
        echo -e "${GREEN}🎬 启动视频分析 (端口: $PORT)...${NC}"
        python3 integrated_system.py --video "$video_path" --port $PORT
        ;;
    *)
        echo -e "${RED}无效选项，使用默认OBS模式${NC}"
        python3 integrated_system.py --obs --port $PORT
        ;;
esac

# 如果脚本被中断
echo ""
echo -e "${YELLOW}👋 系统已停止${NC}"
