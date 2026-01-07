#!/bin/bash
# ============================================================
# OneKey macOS 启动脚本
# ============================================================

cd "$(dirname "$0")"

echo "🚀 启动 OneKey 智能视频分析系统..."
echo ""

# 1. 激活虚拟环境
if [ -d ".venv" ]; then
    echo "✓ 激活 Python 虚拟环境"
    source .venv/bin/activate
else
    echo "❌ 错误: 虚拟环境不存在，请先运行安装脚本"
    exit 1
fi

# 2. 加载环境变量
if [ -f ".env.local" ]; then
    echo "✓ 加载环境变量配置"
    source .env.local
else
    echo "⚠️  警告: .env.local 不存在"
    echo "   请先编辑 .env.local 文件配置 API Keys"
    echo ""
    read -p "是否继续启动？(y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# 3. 检查 API Keys
if [[ "$DASHSCOPE_API_KEY" == "sk-your-dashscope-key-here" ]] || [[ "$ANTHROPIC_API_KEY" == "sk-ant-your-anthropic-key-here" ]]; then
    echo "⚠️  警告: API Key 未配置或使用默认值"
    echo "   请编辑 .env.local 文件设置真实的 API Keys"
    echo ""
fi

# 4. 启动系统
echo ""
echo "📹 正在启动系统..."
echo "   按 Ctrl+C 停止"
echo ""

python integrated_system.py

echo ""
echo "👋 系统已停止"
