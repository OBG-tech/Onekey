#!/bin/bash
# 多摄像头集成系统启动脚本
# 使用4个USB摄像头，2x2拼接，高画质，60 FPS

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "╔════════════════════════════════════════════════════════╗"
echo "║   🎥 多摄像头集成系统 (4K @ 60 FPS)                  ║"
echo "║   4个USB摄像头 → 2x2拼接 → 完整AI分析                ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

# 激活虚拟环境
if [ -d ".venv" ]; then
    echo -e "${GREEN}✅ 激活虚拟环境${NC}"
    source .venv/bin/activate
else
    echo -e "${YELLOW}⚠️  未找到虚拟环境，请先运行: python -m venv .venv${NC}"
    exit 1
fi

# 加载环境变量
if [ -f ".env.local" ]; then
    echo -e "${GREEN}✅ 加载环境变量${NC}"
    set -a
    source .env.local
    set +a
else
    echo -e "${YELLOW}⚠️  未找到 .env.local 文件${NC}"
fi

echo ""

# 默认参数
CAMERAS="${CAMERAS:-0,1,2,3}"
FPS="${FPS:-60}"
RESOLUTION="${RESOLUTION:-1920x1080}"
PORT="${PORT:-8082}"

# 交互式模式
if [ "$1" == "--interactive" ] || [ "$1" == "-i" ]; then
    echo -e "${BLUE}🎮 交互式配置${NC}\n"
    
    echo "请输入摄像头索引 (逗号分隔，例如: 0,1,2,3)"
    read -p "摄像头 [$CAMERAS]: " input_cameras
    if [ ! -z "$input_cameras" ]; then
        # 将中文逗号替换为英文逗号
        CAMERAS="${input_cameras//，/,}"
    fi
    
    echo ""
    echo "请输入每个摄像头的分辨率 (例如: 1920x1080)"
    read -p "分辨率 [$RESOLUTION]: " input_res
    if [ ! -z "$input_res" ]; then
        # 将中文x替换为英文x
        RESOLUTION="${input_res//×/x}"
    fi
    
    echo ""
    echo "请输入目标帧率 (30-60)"
    read -p "FPS [$FPS]: " input_fps
    if [ ! -z "$input_fps" ]; then
        FPS="$input_fps"
    fi
    
    echo ""
fi

# 显示配置
echo -e "${YELLOW}📋 当前配置:${NC}"
echo "  摄像头: $CAMERAS"
echo "  每个摄像头分辨率: $RESOLUTION"

# 计算拼接后分辨率
IFS='x' read -r width height <<< "$RESOLUTION"
stitched_width=$((width * 2))
stitched_height=$((height * 2))
echo "  拼接后分辨率: ${stitched_width}x${stitched_height} (4K)"

echo "  目标FPS: $FPS"
echo "  Web端口: $PORT"
echo ""

# 检查摄像头
echo -e "${BLUE}📹 检测摄像头...${NC}"
python -c "
import cv2
cameras = [${CAMERAS}]
for idx in cameras:
    cap = cv2.VideoCapture(idx)
    if cap.isOpened():
        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        print(f'  ✅ 摄像头 #{idx}: {w}x{h} @ {fps:.1f} FPS')
        cap.release()
    else:
        print(f'  ❌ 摄像头 #{idx}: 无法打开')
"

echo ""
read -p "确认配置无误，按回车启动 (或Ctrl+C取消)..."
echo ""

# 测试模式
if [ "$1" == "--test" ]; then
    echo -e "${YELLOW}🧪 测试模式：仅预览拼接画面${NC}\n"
    
    python start_multicam_system.py \
        --cameras $CAMERAS \
        --fps $FPS \
        --resolution $RESOLUTION \
        --test
    
    exit 0
fi

# 启动完整系统
echo -e "${GREEN}🚀 启动多摄像头集成系统...${NC}\n"

# 启动 Key Moments Viewer 服务 (端口 8084)
echo -e "${BLUE}📹 启动 Key Moments Viewer (端口 8084)...${NC}"
python key_moments_viewer.py > /dev/null 2>&1 &
MOMENTS_VIEWER_PID=$!
sleep 1
echo -e "${GREEN}✅ Key Moments Viewer: http://localhost:8084${NC}\n"

# 启动主系统
python start_multicam_system.py \
    --cameras $CAMERAS \
    --fps $FPS \
    --resolution $RESOLUTION \
    --port $PORT \
    --record

# 捕获退出状态
EXIT_CODE=$?

# 停止后台服务
echo -e "\n${YELLOW}🛑 停止后台服务...${NC}"
kill $MOMENTS_VIEWER_PID 2>/dev/null
echo -e "${GREEN}✅ Key Moments Viewer 已停止${NC}"

if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    echo -e "${YELLOW}⚠️  系统异常退出 (代码: $EXIT_CODE)${NC}"
    echo ""
    echo "故障排除："
    echo "  1. 检查摄像头是否全部可用"
    echo "  2. 确认Terminal有摄像头权限"
    echo "  3. 查看日志: tail -f service_output.log"
else
    echo ""
    echo -e "${GREEN}✅ 系统正常退出${NC}"
fi

echo ""
