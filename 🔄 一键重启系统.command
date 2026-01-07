#!/bin/bash
# 🔄 一键重启整合系统 - 自动清理旧进程并启动新进程

# 获取脚本所在目录（使用绝对路径，避免相对路径/外部环境干扰）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "${SCRIPT_DIR}"

clear
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🚀 智能视频分析系统 - 快速启动"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "💡 提示: 浏览器打开后即可使用"
echo "   模型将在后台自动加载..."
echo ""

# 1. 清理旧进程
echo "🧹 正在清理旧进程..."
pkill -f "python.*integrated_system.py" 2>/dev/null
pkill -f "python.*LAUNCH_GUI.py" 2>/dev/null
sleep 1

# 再次确认清理
if pgrep -f "integrated_system.py" > /dev/null; then
    echo "⚠️  强制终止残留进程..."
    pkill -9 -f "python.*integrated_system.py"
    sleep 1
fi

echo "✅ 旧进程已清理"
echo ""

# 2. 激活虚拟环境（强制使用当前目录的 .venv，避免误用别的项目 venv）
VENV_DIR="${SCRIPT_DIR}/.venv"
if [ -d "${VENV_DIR}" ]; then
    echo "🐍 激活虚拟环境..."
    source "${VENV_DIR}/bin/activate"
else
    echo "❌ 错误：找不到虚拟环境！"
    echo "请先在当前目录创建虚拟环境："
    echo ""
    echo "或者先创建虚拟环境："
    echo "  python3 -m venv .venv"
    echo "  source .venv/bin/activate"
    echo "  python -m pip install -r requirements.txt"
    echo ""
    read -n 1
    exit 1
fi

# 2.1 载入本地环境变量（推荐把 Key 放这里，避免写进脚本）
# 文件格式示例见：.env.local.example
if [ -f ".env.local" ]; then
    echo "🔐 载入本地配置: .env.local"
    set -a
    source ".env.local"
    set +a
fi

# 3. ASR 后端选择（默认使用通义千问云端实时ASR）
# 说明：
# - qwen: 使用 DashScope/Qwen（云端实时ASR，推荐，速度快、准确率高）
# - funasr: 使用 FunASR（离线，需手动下载模型）
# - fireredasr: 使用 FireRedASR-AED（本地离线，CPU模式较慢）

# 允许你在外部手动覆盖：export ASR_PROVIDER=qwen 或 fireredasr 或 funasr
if [ -z "${ASR_PROVIDER}" ]; then
    # 默认使用通义千问云端实时ASR（最快最准）
    export ASR_PROVIDER="qwen"
fi

# 3.1 LLM 分析默认使用 Qwen3-Max（可在外部覆盖）
export LLM_PROVIDER="${LLM_PROVIDER:-qwen}"
export LLM_MODEL="${LLM_MODEL:-qwen3-max}"

# 3.2 关键时刻窗口/麦克风缓冲默认值（可在 .env.local 或外部覆盖）
export KEY_MOMENT_BEFORE_SECONDS="${KEY_MOMENT_BEFORE_SECONDS:-15}"
export KEY_MOMENT_AFTER_SECONDS="${KEY_MOMENT_AFTER_SECONDS:-15}"
export MIC_BUFFER_SECONDS="${MIC_BUFFER_SECONDS:-60}"

# FireRedASR 默认参数（仅在 fireredasr 时使用；允许外部覆盖）
export FIREREDASR_USE_GPU="${FIREREDASR_USE_GPU:-0}"
export FIREREDASR_BEAM_SIZE="${FIREREDASR_BEAM_SIZE:-3}"
export FIREREDASR_NBEST="${FIREREDASR_NBEST:-1}"

echo "🎤 ASR_PROVIDER=${ASR_PROVIDER}"
if [ "${ASR_PROVIDER}" = "qwen" ]; then
    echo "   ✅ 通义千问云端实时ASR（paraformer-realtime-v2）"
elif [ "${ASR_PROVIDER}" = "funasr" ]; then
    echo "   ✅ FunASR 离线识别"
elif [ "${ASR_PROVIDER}" = "fireredasr" ]; then
    echo "   ✅ FireRedASR 离线识别: ${FIREREDASR_MODEL_DIR}"
else
    echo "   ⚠️  未知 ASR 提供商，将自动回退到通义千问"
fi

echo "🤖 LLM_PROVIDER=${LLM_PROVIDER}"
echo "   🧠 LLM_MODEL=${LLM_MODEL}"
echo "⏱️ KEY_MOMENT_BEFORE_SECONDS=${KEY_MOMENT_BEFORE_SECONDS}"
echo "⏱️ KEY_MOMENT_AFTER_SECONDS=${KEY_MOMENT_AFTER_SECONDS}"
echo "🎙️ MIC_BUFFER_SECONDS=${MIC_BUFFER_SECONDS}"

# 3. 配置环境变量 (可选)
# DashScope/Qwen 仅在使用云端能力（ASR/LLM/多模态）时需要。
# 建议在你的 shell 环境中设置，不要在脚本里硬编码。
# 例如：export DASHSCOPE_API_KEY="sk-xxx"

# 4. 启动系统
echo "🚀 启动整合系统..."
echo "📱 浏览器将自动打开: http://localhost:8080/integrated%20final.html"
echo ""

# 3秒后自动打开浏览器
(sleep 3 && open "http://localhost:8080/integrated%20final.html") &

# 始终使用当前目录 .venv 的解释器（避免 $VIRTUAL_ENV 指向别处导致缺包/回退）
PYTHON_BIN="${VENV_DIR}/bin/python"
if [ ! -x "${PYTHON_BIN}" ]; then
    PYTHON_BIN="$(command -v python3)"
fi

echo "🐍 使用解释器: ${PYTHON_BIN}"
echo ""

"${PYTHON_BIN}" integrated_system.py --camera 0 --no-window

# 如果退出，保持窗口打开
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "系统已退出"
echo "按任意键关闭此窗口..."
read -n 1
