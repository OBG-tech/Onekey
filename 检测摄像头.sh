#!/bin/bash
# 快速检测所有摄像头设备

cd "$(dirname "$0")"

echo "🔍 检测摄像头设备..."
echo ""

# 激活虚拟环境
if [ -d ".venv" ]; then
    source .venv/bin/activate
else
    echo "❌ 虚拟环境不存在"
    exit 1
fi

# 运行检测脚本
python3 detect_cameras.py

echo ""
echo "💡 提示："
echo "   找到OBS虚拟摄像头的索引号（标记为🎥虚拟相机）"
echo "   然后使用以下命令启动："
echo ""
echo "   python3 integrated_system.py --camera X"
echo "   （将X替换为OBS虚拟摄像头的索引号）"
