#!/bin/bash
# ============================================================
# macOS 移植验证测试脚本
# 在 macOS 上运行此脚本以验证移植是否成功
# ============================================================

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

PASSED=0
FAILED=0
WARNINGS=0

echo ""
echo "============================================================"
echo "🧪 OneKey macOS 移植验证测试"
echo "============================================================"
echo ""

# 辅助函数
test_pass() {
    echo -e "${GREEN}✓ PASS${NC}: $1"
    ((PASSED++))
}

test_fail() {
    echo -e "${RED}✗ FAIL${NC}: $1"
    echo "       $2"
    ((FAILED++))
}

test_warn() {
    echo -e "${YELLOW}⚠ WARN${NC}: $1"
    echo "       $2"
    ((WARNINGS++))
}

# ============================================================
# 测试 1: 虚拟环境
# ============================================================
echo -e "${BLUE}[测试 1/10]${NC} Python 虚拟环境"
if [ -d ".venv" ]; then
    test_pass "虚拟环境目录存在"
else
    test_fail "虚拟环境不存在" "运行: ./install_macos.sh"
fi

# 激活虚拟环境
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    test_pass "虚拟环境已激活"
else
    test_fail "无法激活虚拟环境" "虚拟环境可能未正确创建"
fi
echo ""

# ============================================================
# 测试 2: Python 版本
# ============================================================
echo -e "${BLUE}[测试 2/10]${NC} Python 版本"
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)

if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 8 ]; then
    test_pass "Python $PYTHON_VERSION (>= 3.8)"
else
    test_fail "Python 版本过低: $PYTHON_VERSION" "需要 Python >= 3.8"
fi
echo ""

# ============================================================
# 测试 3: 核心依赖
# ============================================================
echo -e "${BLUE}[测试 3/10]${NC} 核心 Python 依赖"

# OpenCV
if python3 -c "import cv2" 2>/dev/null; then
    CV_VERSION=$(python3 -c "import cv2; print(cv2.__version__)" 2>/dev/null)
    test_pass "OpenCV $CV_VERSION"
else
    test_fail "OpenCV 未安装" "pip install opencv-python"
fi

# NumPy
if python3 -c "import numpy" 2>/dev/null; then
    test_pass "NumPy"
else
    test_fail "NumPy 未安装" "pip install numpy"
fi

# Ultralytics
if python3 -c "from ultralytics import YOLO" 2>/dev/null; then
    test_pass "Ultralytics (YOLO)"
else
    test_fail "Ultralytics 未安装" "pip install ultralytics"
fi

# PyAudio
if python3 -c "import pyaudio" 2>/dev/null; then
    test_pass "PyAudio"
else
    test_warn "PyAudio 未安装" "pip install PyAudio (需要 portaudio)"
fi

echo ""

# ============================================================
# 测试 4: AI 依赖
# ============================================================
echo -e "${BLUE}[测试 4/10]${NC} AI 依赖"

# OpenAI/DashScope
if python3 -c "import openai" 2>/dev/null; then
    test_pass "OpenAI SDK (用于 Qwen)"
else
    test_warn "OpenAI SDK 未安装" "pip install openai"
fi

# Anthropic
if python3 -c "import anthropic" 2>/dev/null; then
    test_pass "Anthropic SDK (用于 Claude)"
else
    test_warn "Anthropic SDK 未安装" "pip install anthropic"
fi

# DashScope
if python3 -c "import dashscope" 2>/dev/null; then
    test_pass "DashScope SDK"
else
    test_warn "DashScope SDK 未安装" "pip install dashscope"
fi

echo ""

# ============================================================
# 测试 5: 系统工具
# ============================================================
echo -e "${BLUE}[测试 5/10]${NC} 系统工具"

if command -v ffmpeg &> /dev/null; then
    FFMPEG_VERSION=$(ffmpeg -version 2>&1 | head -n 1 | awk '{print $3}')
    test_pass "FFmpeg $FFMPEG_VERSION"
else
    test_fail "FFmpeg 未安装" "brew install ffmpeg"
fi

echo ""

# ============================================================
# 测试 6: 配置文件
# ============================================================
echo -e "${BLUE}[测试 6/10]${NC} 配置文件"

if [ -f ".env.local" ]; then
    test_pass ".env.local 存在"
    
    # 检查 API 密钥
    if grep -q "DASHSCOPE_API_KEY" .env.local && ! grep -q "sk-your" .env.local; then
        test_pass "DASHSCOPE_API_KEY 已配置"
    elif grep -q "ANTHROPIC_API_KEY" .env.local && ! grep -q "sk-ant-your" .env.local; then
        test_pass "ANTHROPIC_API_KEY 已配置"
    else
        test_warn "API 密钥可能未配置" "编辑 .env.local 添加有效的 API 密钥"
    fi
else
    test_warn ".env.local 不存在" "从 .env.local.example 创建"
fi

echo ""

# ============================================================
# 测试 7: 模型文件
# ============================================================
echo -e "${BLUE}[测试 7/10]${NC} YOLO 模型文件"

if [ -f "yolo11n.pt" ]; then
    SIZE=$(du -h yolo11n.pt | cut -f1)
    test_pass "yolo11n.pt ($SIZE)"
else
    test_fail "yolo11n.pt 不存在" "模型会在首次运行时自动下载"
fi

if [ -f "yolov8n-seg.pt" ]; then
    SIZE=$(du -h yolov8n-seg.pt | cut -f1)
    test_pass "yolov8n-seg.pt ($SIZE)"
else
    test_warn "yolov8n-seg.pt 不存在" "模型会在首次运行时自动下载"
fi

echo ""

# ============================================================
# 测试 8: 数据目录
# ============================================================
echo -e "${BLUE}[测试 8/10]${NC} 数据目录结构"

REQUIRED_DIRS=(
    "integrated_data"
    "integrated_data/key_moments"
    "integrated_data/audio"
    "integrated_data/transcripts"
    "integrated_data/key_frames"
    "integrated_data/logs"
)

for dir in "${REQUIRED_DIRS[@]}"; do
    if [ -d "$dir" ]; then
        test_pass "$dir/"
    else
        mkdir -p "$dir"
        test_warn "$dir/ 不存在，已创建" ""
    fi
done

echo ""

# ============================================================
# 测试 9: macOS 工具脚本
# ============================================================
echo -e "${BLUE}[测试 9/10]${NC} macOS 专用工具"

MACOS_TOOLS=(
    "check_macos_env.sh"
    "clear_session_macos.sh"
    "detect_cameras_macos.py"
    "install_macos.sh"
    "start_macos.sh"
)

for tool in "${MACOS_TOOLS[@]}"; do
    if [ -f "$tool" ]; then
        if [ -x "$tool" ]; then
            test_pass "$tool (可执行)"
        else
            chmod +x "$tool"
            test_warn "$tool (已设置可执行权限)" ""
        fi
    else
        test_warn "$tool 不存在" "可能需要重新打包"
    fi
done

echo ""

# ============================================================
# 测试 10: 相机访问
# ============================================================
echo -e "${BLUE}[测试 10/10]${NC} 相机访问测试"

python3 - << 'PYTHON_TEST'
import sys
try:
    import cv2
    camera_found = False
    for i in range(3):
        cap = cv2.VideoCapture(i)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                print(f"PASS:Camera {i} ({w}x{h})")
                camera_found = True
            cap.release()
    
    if not camera_found:
        print("WARN:No camera found")
        sys.exit(1)
except Exception as e:
    print(f"FAIL:{e}")
    sys.exit(2)
PYTHON_TEST

TEST_RESULT=$?
if [ $TEST_RESULT -eq 0 ]; then
    test_pass "至少找到一个可用相机"
elif [ $TEST_RESULT -eq 1 ]; then
    test_warn "未找到可用相机" "检查系统权限: 系统偏好设置 → 安全性与隐私 → 相机"
else
    test_fail "相机测试失败" "检查 OpenCV 安装"
fi

echo ""

# ============================================================
# 总结
# ============================================================
echo "============================================================"
echo "📊 测试结果汇总"
echo "============================================================"
echo ""
echo -e "${GREEN}✓ 通过${NC}: $PASSED"
echo -e "${YELLOW}⚠ 警告${NC}: $WARNINGS"
echo -e "${RED}✗ 失败${NC}: $FAILED"
echo ""

if [ $FAILED -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}🎉 所有测试通过! 系统已准备就绪!${NC}"
    echo ""
    echo "下一步:"
    echo "  1. 运行: ./start_macos.sh"
    echo "  2. 浏览器访问: http://localhost:8080"
    echo ""
    exit 0
elif [ $FAILED -eq 0 ]; then
    echo -e "${YELLOW}⚠️  测试通过，但有警告${NC}"
    echo ""
    echo "建议:"
    echo "  1. 检查上述警告信息"
    echo "  2. 安装缺失的可选依赖"
    echo "  3. 配置 .env.local 文件"
    echo ""
    echo "仍可运行系统:"
    echo "  ./start_macos.sh"
    echo ""
    exit 0
else
    echo -e "${RED}❌ 测试失败! 请修复上述错误${NC}"
    echo ""
    echo "常见问题:"
    echo "  1. 虚拟环境: ./install_macos.sh"
    echo "  2. 系统依赖: brew install portaudio ffmpeg"
    echo "  3. Python 依赖: pip install -r requirements.txt"
    echo ""
    exit 1
fi
