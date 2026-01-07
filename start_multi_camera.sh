#!/bin/bash
# 多摄像头录制系统启动脚本
# 独立运行，不依赖OBS

# 切换到脚本所在目录
cd "$(dirname "$0")"

# 颜色定义
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "╔════════════════════════════════════════════════════════╗"
echo "║   📹 多摄像头录制系统                                 ║"
echo "║   无需OBS，纯Python实现                               ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

# 激活虚拟环境
if [ -d ".venv" ]; then
    echo -e "${GREEN}✅ 激活虚拟环境${NC}"
    source .venv/bin/activate
else
    echo -e "${YELLOW}⚠️  未找到虚拟环境，使用系统Python${NC}"
fi

# 默认参数
CAMERAS="${CAMERAS:-0,1,2}"
LAYOUT="${LAYOUT:-horizontal}"
OUTPUT_DIR="${OUTPUT_DIR:-./recordings}"
FPS="${FPS:-30}"
SHOW_PREVIEW="${SHOW_PREVIEW:-true}"
AUTO_START="${AUTO_START:-false}"

# 显示配置
echo "📋 当前配置:"
echo "  摄像头: $CAMERAS"
echo "  布局: $LAYOUT"
echo "  输出目录: $OUTPUT_DIR"
echo "  帧率: $FPS FPS"
echo "  预览: $SHOW_PREVIEW"
echo "  自动录制: $AUTO_START"
echo ""

# 交互式选择（如果未设置环境变量）
if [ "$1" == "--interactive" ] || [ "$1" == "-i" ]; then
    echo "请选择摄像头:"
    echo "1) 单摄像头 (0)"
    echo "2) 双摄像头 (0,1)"
    echo "3) 三摄像头 (0,1,2)"
    echo "4) 自定义"
    read -p "选择 [1-4]: " cam_choice
    
    case $cam_choice in
        1) CAMERAS="0" ;;
        2) CAMERAS="0,1" ;;
        3) CAMERAS="0,1,2" ;;
        4) read -p "输入摄像头索引（逗号分隔）: " CAMERAS ;;
        *) CAMERAS="0,1,2" ;;
    esac
    
    echo ""
    echo "请选择布局:"
    echo "1) 横向拼接 (horizontal)"
    echo "2) 纵向拼接 (vertical)"
    echo "3) 网格布局 (grid)"
    read -p "选择 [1-3]: " layout_choice
    
    case $layout_choice in
        1) LAYOUT="horizontal" ;;
        2) LAYOUT="vertical" ;;
        3) LAYOUT="grid" ;;
        *) LAYOUT="horizontal" ;;
    esac
    
    echo ""
    read -p "是否自动开始录制? [y/N]: " auto_choice
    if [ "$auto_choice" == "y" ] || [ "$auto_choice" == "Y" ]; then
        AUTO_START="true"
    fi
    
    echo ""
fi

# 构建命令
CMD="python3 multi_camera_recording.py --cameras $CAMERAS --layout $LAYOUT --output-dir $OUTPUT_DIR --fps $FPS"

if [ "$SHOW_PREVIEW" != "true" ]; then
    CMD="$CMD --no-preview"
fi

if [ "$AUTO_START" == "true" ]; then
    CMD="$CMD --auto-start"
fi

# 显示最终命令
echo -e "${YELLOW}📝 执行命令:${NC}"
echo "  $CMD"
echo ""

# 运行
echo -e "${GREEN}🚀 启动多摄像头录制系统...${NC}"
echo ""

exec $CMD
