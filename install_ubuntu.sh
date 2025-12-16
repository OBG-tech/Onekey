#!/bin/bash
# ============================================================
# 🐧 Ubuntu 24.04 LTS 一键安装脚本
# ============================================================
# 用途: 自动安装智能视频分析系统所需的所有依赖
# 使用: chmod +x install_ubuntu.sh && ./install_ubuntu.sh
# ============================================================

set -e  # 遇到错误立即退出

echo "🎬 智能视频分析整合系统 - Ubuntu 24.04 安装脚本"
echo "============================================================"
echo ""

# 检测是否为 root 用户
if [ "$EUID" -eq 0 ]; then 
    echo "⚠️  请不要使用 sudo 运行此脚本"
    echo "   脚本会在需要时自动请求 sudo 权限"
    exit 1
fi

# 检测 Ubuntu 版本
if [ -f /etc/os-release ]; then
    . /etc/os-release
    if [[ "$ID" != "ubuntu" ]]; then
        echo "⚠️  警告: 此脚本为 Ubuntu 24.04 优化，您的系统是: $PRETTY_NAME"
        read -p "   是否继续? (y/n) " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
fi

echo "📦 步骤 1/4: 更新系统包索引..."
echo "------------------------------------------------------------"
sudo apt update

echo ""
echo "📦 步骤 2/4: 安装系统依赖..."
echo "------------------------------------------------------------"

# Python 开发环境
echo "  ⏳ 安装 Python 开发工具..."
sudo apt install -y python3-pip python3-venv python3-dev

# 音频依赖
echo "  🎤 安装音频处理库..."
sudo apt install -y portaudio19-dev python3-pyaudio

# OpenCV 依赖
echo "  📷 安装图像处理库..."
sudo apt install -y libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender-dev

# 视频处理工具
echo "  🎬 安装 FFmpeg..."
sudo apt install -y ffmpeg

# 摄像头支持
echo "  📹 配置摄像头权限..."
sudo apt install -y v4l-utils
sudo usermod -a -G video $USER

echo ""
echo "✅ 系统依赖安装完成！"
echo ""

# 选择安装方式
echo "📦 步骤 3/4: 选择 Python 包安装方式"
echo "------------------------------------------------------------"
echo "请选择安装方式:"
echo "  1) 基础安装 (仅视频分析，不含 AI)"
echo "  2) 完整安装 - Claude Haiku 4.5 (推荐)"
echo "  3) 完整安装 - Qwen 通义千问"
echo "  4) 完整安装 - 同时支持 Claude 和 Qwen"
echo "  5) 手动安装 (跳过此步骤)"
echo ""
read -p "请输入选项 (1-5): " choice

# 检查是否在虚拟环境中
if [[ -z "$VIRTUAL_ENV" ]]; then
    echo ""
    echo "⚠️  您不在虚拟环境中"
    echo "   建议创建虚拟环境以避免污染系统 Python"
    read -p "   是否创建虚拟环境? (y/n) " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo "  📦 创建虚拟环境 .venv ..."
        python3 -m venv .venv
        echo "  ✅ 虚拟环境已创建"
        echo "  💡 请运行: source .venv/bin/activate"
        echo "     然后重新执行此脚本"
        exit 0
    fi
fi

echo ""
echo "  ⏳ 升级 pip..."
pip install --upgrade pip

case $choice in
    1)
        echo "  📦 基础安装..."
        pip install opencv-python numpy ultralytics
        ;;
    2)
        echo "  📦 完整安装 (Claude Haiku 4.5)..."
        pip install opencv-python numpy ultralytics anthropic PyAudio
        ;;
    3)
        echo "  📦 完整安装 (Qwen)..."
        pip install opencv-python numpy ultralytics openai dashscope PyAudio
        ;;
    4)
        echo "  📦 完整安装 (Claude + Qwen)..."
        pip install opencv-python numpy ultralytics anthropic openai dashscope PyAudio
        ;;
    5)
        echo "  ⏭️  跳过 Python 包安装"
        ;;
    *)
        echo "  ❌ 无效选项，跳过安装"
        ;;
esac

echo ""
echo "📦 步骤 4/4: 验证安装"
echo "------------------------------------------------------------"

# 验证核心包
echo "  🔍 检查核心依赖..."
python3 -c "import cv2; print(f'  ✅ OpenCV: {cv2.__version__}')" 2>/dev/null || echo "  ❌ OpenCV 未安装"
python3 -c "import numpy; print(f'  ✅ NumPy: {numpy.__version__}')" 2>/dev/null || echo "  ❌ NumPy 未安装"
python3 -c "from ultralytics import YOLO; print('  ✅ YOLO: 已安装')" 2>/dev/null || echo "  ❌ YOLO 未安装"

# 验证可选包
if python3 -c "import anthropic" 2>/dev/null; then
    echo "  ✅ Anthropic (Claude): 已安装"
fi

if python3 -c "import openai" 2>/dev/null; then
    echo "  ✅ OpenAI (Qwen): 已安装"
fi

if python3 -c "import pyaudio" 2>/dev/null; then
    echo "  ✅ PyAudio: 已安装"
fi

if python3 -c "import insightface" 2>/dev/null; then
    echo "  ✅ InsightFace: 已安装"
fi

echo ""
echo "============================================================"
echo "✅ 安装完成！"
echo "============================================================"
echo ""
echo "📋 后续步骤:"
echo ""
echo "1. 重新登录以应用用户组更改 (摄像头权限)"
echo "   logout && login"
echo ""
echo "2. 配置 API 密钥 (如需 AI 功能):"
echo "   export LLM_PROVIDER=\"claude\"  # 或 \"qwen\""
echo "   export ANTHROPIC_API_KEY=\"sk-ant-your-key\""
echo ""
echo "3. 测试摄像头:"
echo "   python3 integrated_system.py --camera 0"
echo ""
echo "4. 启动完整系统:"
echo "   python3 LAUNCH_GUI.py"
echo ""
echo "💡 提示:"
echo "   - 如遇到摄像头权限问题，请重新登录系统"
echo "   - 如需人脸识别，运行: pip install insightface onnxruntime"
echo "   - 查看日志: tail -f integrated_data/logs/*.log"
echo ""
echo "📚 文档: README.md | 使用说明.md"
echo "============================================================"
