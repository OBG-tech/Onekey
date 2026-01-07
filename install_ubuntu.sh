#!/bin/bash
# ============================================================
# 🐧 Ubuntu 22.04/24.04 LTS 一键安装脚本 (完整版)
# ============================================================
# 用途: 自动安装智能视频分析系统所需的所有依赖 (系统 + Python)
# 使用: chmod +x install_ubuntu.sh && ./install_ubuntu.sh
# ============================================================

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   �� 智能视频分析整合系统 - 依赖安装脚本              ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

# 检测是否为 root 用户
if [ "$EUID" -eq 0 ]; then 
    echo -e "${RED}⚠️  请不要使用 sudo 运行此脚本${NC}"
    echo -e "${YELLOW}   脚本会在需要时自动请求 sudo 权限${NC}"
    exit 1
fi

# 1. 系统更新与依赖安装
echo -e "${BLUE}📦 [1/5] 安装系统依赖...${NC}"
echo "------------------------------------------------------------"

echo -e "${YELLOW}🔄 更新 apt 源...${NC}"
sudo apt update

echo -e "${YELLOW}📦 安装核心库...${NC}"
# Python基础
sudo apt install -y python3-pip python3-venv python3-dev

# 音频 (PortAudio) - 必需 for PyAudio
sudo apt install -y portaudio19-dev python3-pyaudio

# 视频 (OpenCV, FFmpeg)
sudo apt install -y libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender-dev ffmpeg

# 摄像头 (V4L2)
sudo apt install -y v4l-utils

# 添加用户到 video/audio 组
echo -e "${YELLOW}👤 配置用户权限...${NC}"
sudo usermod -a -G video $USER
sudo usermod -a -G audio $USER

# 2. 虚拟环境配置
echo -e "\n${BLUE}🐍 [2/5] 配置 Python 虚拟环境...${NC}"
echo "------------------------------------------------------------"

if [ ! -d ".venv" ]; then
    echo -e "${YELLOW}📂 创建 .venv...${NC}"
    python3 -m venv .venv
else
    echo -e "${GREEN}✅ .venv 已存在${NC}"
fi

# 激活虚拟环境
echo -e "${YELLOW}🔌 激活虚拟环境...${NC}"
source .venv/bin/activate

# 升级 pip
echo -e "${YELLOW}⬆️  升级 pip...${NC}"
python3 -m pip install --upgrade pip

# 3. 安装 Python 依赖
echo -e "\n${BLUE}📥 [3/5] 安装 Python 依赖包...${NC}"
echo "------------------------------------------------------------"

# 安装基础依赖
echo -e "${YELLOW}📦 安装 requirements.txt...${NC}"
pip install -r requirements.txt

# 安装 FireRedASR 依赖 (如果存在)
if [ -d "FireRedASR" ] && [ -f "FireRedASR/requirements.txt" ]; then
    echo -e "${YELLOW}🔥 安装 FireRedASR 依赖...${NC}"
    pip install -r FireRedASR/requirements.txt
fi

# 4. 可选组件安装
echo -e "\n${BLUE}🧩 [4/5] 检查可选组件...${NC}"
echo "------------------------------------------------------------"

# 人脸识别 Check
read -p "👤 是否安装高精度人脸识别 (InsightFace)? [y/N] " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}📦 安装 InsightFace & ONNXRuntime...${NC}"
    pip install insightface onnxruntime-gpu 2>/dev/null || pip install insightface onnxruntime
fi

# 5. 验证安装
echo -e "\n${BLUE}✅ [5/5] 验证安装结果...${NC}"
echo "------------------------------------------------------------"

function check_pkg() {
    python3 -c "import $1; print(f'  ✅ $1: {getattr($1, \"__version__\", \"Installed\")}')" 2>/dev/null || echo -e "  ${RED}❌ $1 未安装${NC}"
}

echo "核心库:"
check_pkg cv2
check_pkg numpy
check_pkg ultralytics
check_pkg pyaudio

echo -e "\nAI 接口:"
check_pkg anthropic
check_pkg openai
check_pkg dashscope

echo -e "\nFireRedASR 依赖:"
check_pkg torch
check_pkg kaldiio

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   🎉 安装全部完成！                                   ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}🚨 重要提示:${NC}"
echo "1. 如果这是首次安装，请${RED}注销并重新登录${NC}以使摄像头权限生效。"
echo "   命令: logout"
echo ""
echo "2. 启动方式:"
echo "   ./start_multicam.sh -i"
echo ""
