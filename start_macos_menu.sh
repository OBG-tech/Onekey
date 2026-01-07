#!/bin/bash
# 🎬 macOS智能视频分析系统 - 带选择菜单的启动脚本

# 切换到脚本所在目录
cd "$(dirname "$0")"

# 默认端口
PORT=${1:-8080}

echo "╔════════════════════════════════════════════════════════╗"
echo "║   🎬 智能视频分析系统 (macOS版)                       ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

# 检查虚拟环境
if [ ! -d ".venv" ]; then
    echo "❌ 未找到虚拟环境 .venv"
    echo "请先创建虚拟环境"
    exit 1
fi

# 激活虚拟环境
echo "✓ 激活 Python 虚拟环境"
source .venv/bin/activate

# 加载环境变量
if [ -f ".env.local" ]; then
    echo "✓ 加载环境变量配置"
    set -a
    source .env.local
    set +a
fi

# 显示选择菜单
echo ""
echo "请选择启动模式:"
echo ""
echo "  1) OBS虚拟摄像头模式 (自动检测)"
echo "  2) OBS摄像头 - 索引0 (1920x1080, 5fps)"
echo "  3) OBS摄像头 - 索引1 (1920x1080, 5fps)"
echo "  4) OBS摄像头 - 索引2 (1920x1080, 60fps) 🌟推荐"
echo "  5) 物理摄像头模式"
echo "  6) 视频文件模式"
echo ""
read -p "请输入选项 [1-6]: " choice

# 清理旧进程
echo ""
echo "🔄 清理旧进程..."
pkill -f "integrated_system.py" 2>/dev/null
sleep 1

# 根据选择启动
case $choice in
    1)
        echo "🎥 启动OBS虚拟摄像头模式（自动检测）..."
        echo "📹 正在启动系统..."
        echo "   按 Ctrl+C 停止"
        echo ""
        python3 integrated_system.py --obs --port $PORT
        ;;
    2)
        echo "🎥 启动OBS摄像头 - 索引0..."
        echo "📹 正在启动系统..."
        echo "   按 Ctrl+C 停止"
        echo ""
        python3 integrated_system.py --camera 0 --port $PORT
        ;;
    3)
        echo "🎥 启动OBS摄像头 - 索引1..."
        echo "📹 正在启动系统..."
        echo "   按 Ctrl+C 停止"
        echo ""
        python3 integrated_system.py --camera 1 --port $PORT
        ;;
    4)
        echo "🎥 启动OBS摄像头 - 索引2 (60fps)..."
        echo "📹 正在启动系统..."
        echo "   按 Ctrl+C 停止"
        echo ""
        python3 integrated_system.py --camera 2 --port $PORT
        ;;
    5)
        echo "📷 启动物理摄像头模式..."
        echo ""
        echo "提示: 运行以下命令查看可用摄像头："
        echo "  python3 detect_cameras_macos.py"
        echo ""
        read -p "请输入摄像头索引号: " cam_index
        echo ""
        echo "📹 正在启动系统..."
        echo "   按 Ctrl+C 停止"
        echo ""
        python3 integrated_system.py --camera $cam_index --port $PORT
        ;;
    6)
        read -p "请输入视频文件路径: " video_path
        if [ ! -f "$video_path" ]; then
            echo "❌ 错误: 文件不存在"
            exit 1
        fi
        echo ""
        echo "🎬 启动视频分析..."
        echo "   按 Ctrl+C 停止"
        echo ""
        python3 integrated_system.py --video "$video_path" --port $PORT
        ;;
    *)
        echo "❌ 无效选项"
        exit 1
        ;;
esac

echo ""
echo "👋 系统已停止"
