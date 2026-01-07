#!/bin/bash
# ============================================================
# macOS 环境检测和安装检查脚本
# ============================================================

set -e

echo "🍎 macOS M2 环境检测"
echo "===================================================="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检测结果
ALL_PASS=true

# ============================================================
# 1. 系统信息
# ============================================================
echo "📊 系统信息"
echo "----------------------------------------------------"
echo "操作系统: $(sw_vers -productName) $(sw_vers -productVersion)"
echo "芯片类型: $(uname -m)"

if [[ "$(uname -m)" == "arm64" ]]; then
    echo -e "${GREEN}✓ 确认 Apple Silicon (M1/M2/M3)${NC}"
else
    echo -e "${YELLOW}⚠ 检测到 Intel 芯片,建议使用 M 系列芯片${NC}"
fi
echo ""

# ============================================================
# 2. Homebrew
# ============================================================
echo "🍺 Homebrew 检查"
echo "----------------------------------------------------"
if command -v brew &> /dev/null; then
    echo -e "${GREEN}✓ Homebrew 已安装${NC}"
    echo "  版本: $(brew --version | head -n 1)"
else
    echo -e "${RED}✗ Homebrew 未安装${NC}"
    echo "  安装命令:"
    echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
    ALL_PASS=false
fi
echo ""

# ============================================================
# 3. Python
# ============================================================
echo "🐍 Python 检查"
echo "----------------------------------------------------"
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
    echo -e "${GREEN}✓ Python3 已安装${NC}"
    echo "  版本: $PYTHON_VERSION"
    
    # 检查版本是否 >= 3.8
    MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
    MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
    if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 8 ]; then
        echo -e "${GREEN}✓ Python 版本符合要求 (>= 3.8)${NC}"
    else
        echo -e "${RED}✗ Python 版本过低,需要 >= 3.8${NC}"
        ALL_PASS=false
    fi
else
    echo -e "${RED}✗ Python3 未安装${NC}"
    echo "  安装命令: brew install python@3.11"
    ALL_PASS=false
fi
echo ""

# ============================================================
# 4. FFmpeg
# ============================================================
echo "🎬 FFmpeg 检查"
echo "----------------------------------------------------"
if command -v ffmpeg &> /dev/null; then
    echo -e "${GREEN}✓ FFmpeg 已安装${NC}"
    echo "  版本: $(ffmpeg -version 2>&1 | head -n 1 | awk '{print $3}')"
else
    echo -e "${RED}✗ FFmpeg 未安装${NC}"
    echo "  安装命令: brew install ffmpeg"
    ALL_PASS=false
fi
echo ""

# ============================================================
# 5. PortAudio
# ============================================================
echo "🎤 PortAudio 检查"
echo "----------------------------------------------------"
if brew list portaudio &> /dev/null; then
    echo -e "${GREEN}✓ PortAudio 已安装${NC}"
else
    echo -e "${RED}✗ PortAudio 未安装${NC}"
    echo "  安装命令: brew install portaudio"
    ALL_PASS=false
fi
echo ""

# ============================================================
# 6. 摄像头访问
# ============================================================
echo "📹 摄像头检测"
echo "----------------------------------------------------"
python3 - << 'PYTHON_SCRIPT'
import sys
try:
    import cv2
    print("✓ OpenCV 可用")
    
    # 尝试打开摄像头
    camera_found = False
    for i in range(5):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                print(f"✓ 摄像头 {i}: {w}x{h}")
                camera_found = True
            cap.release()
    
    if not camera_found:
        print("⚠ 未找到可用摄像头")
        print("  请检查系统权限: 系统偏好设置 → 安全性与隐私 → 相机")
        
except ImportError:
    print("⚠ OpenCV 未安装 (正常,将在后续步骤安装)")
except Exception as e:
    print(f"⚠ 摄像头检测失败: {e}")
PYTHON_SCRIPT
echo ""

# ============================================================
# 7. 串口设备 (可选)
# ============================================================
echo "🔌 串口设备检测 (ESP32/Arduino)"
echo "----------------------------------------------------"
USB_DEVICES=$(ls /dev/cu.usbmodem* /dev/cu.usbserial* 2>/dev/null || true)
if [ -n "$USB_DEVICES" ]; then
    echo -e "${GREEN}✓ 检测到 USB 串口设备:${NC}"
    echo "$USB_DEVICES" | while read device; do
        echo "  - $device"
    done
else
    echo -e "${YELLOW}⚠ 未检测到 USB 串口设备${NC}"
    echo "  如需使用 ESP32 按钮,请连接设备"
fi
echo ""

# ============================================================
# 8. OBS Studio (可选)
# ============================================================
echo "📡 OBS Studio 检查 (虚拟相机)"
echo "----------------------------------------------------"
if [ -d "/Applications/OBS.app" ]; then
    echo -e "${GREEN}✓ OBS Studio 已安装${NC}"
    echo "  提示: 启动 OBS → Tools → Start Virtual Camera"
else
    echo -e "${YELLOW}⚠ OBS Studio 未安装 (可选)${NC}"
    echo "  下载地址: https://obsproject.com/download"
    echo "  用途: 提供虚拟相机功能"
fi
echo ""

# ============================================================
# 总结
# ============================================================
echo "===================================================="
if [ "$ALL_PASS" = true ]; then
    echo -e "${GREEN}✅ 环境检查通过!${NC}"
    echo ""
    echo "下一步:"
    echo "  1. 运行 ./install_macos.sh 安装项目依赖"
    echo "  2. 配置 .env.local 文件"
    echo "  3. 运行 ./start_macos.sh 启动系统"
else
    echo -e "${YELLOW}⚠️  环境检查发现问题,请先安装缺失的依赖${NC}"
    echo ""
    echo "快速安装命令:"
    if ! command -v brew &> /dev/null; then
        echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
    fi
    echo "  brew install python@3.11 ffmpeg portaudio"
fi
echo "===================================================="
