#!/bin/bash
# 模型配置验证脚本

echo "========================================"
echo "🔍 检查 AI 模型配置"
echo "========================================"
echo ""

# 检查 .env.local 文件
if [ ! -f ".env.local" ]; then
    echo "❌ .env.local 文件不存在"
    echo "   请复制 .env.local.example 并填写配置"
    exit 1
fi

echo "✅ .env.local 文件存在"
echo ""

# 加载环境变量
set -a
source .env.local 2>/dev/null
set +a

# 检查 API Key
echo "📋 API 配置:"
if [ -z "$DASHSCOPE_API_KEY" ]; then
    echo "   ❌ DASHSCOPE_API_KEY 未设置"
else
    echo "   ✅ DASHSCOPE_API_KEY: ${DASHSCOPE_API_KEY:0:10}...${DASHSCOPE_API_KEY: -4}"
fi
echo ""

# 检查模型配置
echo "🤖 模型配置:"
echo "   LLM_PROVIDER: ${LLM_PROVIDER:-qwen (默认)}"
echo "   LLM_MODEL: ${LLM_MODEL:-qwen-max (默认)}"
echo "   VISION_MODEL_FAST: ${VISION_MODEL_FAST:-qwen-vl-plus (默认)}"
echo "   VISION_MODEL: ${VISION_MODEL:-qwen-vl-max-latest (默认)}"
echo ""

# 验证模型名称
VALID=true

# 检查是否使用了错误的模型名称
if [[ "$LLM_MODEL" == gpt-* ]]; then
    echo "   ❌ LLM_MODEL 使用了 GPT 模型名称（$LLM_MODEL）"
    echo "      应该使用 Qwen 模型，如: qwen-max"
    VALID=false
fi

if [[ "$VISION_MODEL" == gpt-* ]]; then
    echo "   ❌ VISION_MODEL 使用了 GPT 模型名称（$VISION_MODEL）"
    echo "      应该使用 Qwen 模型，如: qwen-vl-max-latest"
    VALID=false
fi

if [[ "$VISION_MODEL_FAST" == gpt-* ]]; then
    echo "   ❌ VISION_MODEL_FAST 使用了 GPT 模型名称（$VISION_MODEL_FAST）"
    echo "      应该使用 Qwen 模型，如: qwen-vl-plus"
    VALID=false
fi

# 检查 Qwen 文本模型
case "${LLM_MODEL:-qwen-max}" in
    qwen-max|qwen-plus|qwen-turbo|qwen-long)
        echo "   ✅ LLM_MODEL 配置正确"
        ;;
    claude-*)
        if [[ "${LLM_PROVIDER}" == "claude" ]]; then
            echo "   ✅ LLM_MODEL 配置正确（Claude）"
        else
            echo "   ❌ 使用了 Claude 模型但 LLM_PROVIDER 不是 claude"
            VALID=false
        fi
        ;;
    *)
        echo "   ⚠️  未知的 LLM_MODEL: ${LLM_MODEL}"
        ;;
esac

# 检查 Qwen 视觉模型
case "${VISION_MODEL:-qwen-vl-max-latest}" in
    qwen-vl-max-latest|qwen-vl-max|qwen-vl-plus)
        echo "   ✅ VISION_MODEL 配置正确"
        ;;
    claude-*)
        if [[ "${LLM_PROVIDER}" == "claude" ]]; then
            echo "   ✅ VISION_MODEL 配置正确（Claude）"
        else
            echo "   ❌ 使用了 Claude 模型但 LLM_PROVIDER 不是 claude"
            VALID=false
        fi
        ;;
    *)
        echo "   ⚠️  未知的 VISION_MODEL: ${VISION_MODEL}"
        ;;
esac

echo ""

if [ "$VALID" = true ]; then
    echo "========================================"
    echo "✅ 配置验证通过！"
    echo "========================================"
    echo ""
    echo "💡 推荐配置（已应用）："
    echo "   LLM_MODEL=qwen-max"
    echo "   VISION_MODEL_FAST=qwen-vl-plus"
    echo "   VISION_MODEL=qwen-vl-max-latest"
    echo ""
    echo "🧪 运行测试："
    echo "   python3 test_ai_analysis.py"
    echo ""
    echo "🚀 启动系统："
    echo "   ./start_multicam.sh"
    echo ""
else
    echo "========================================"
    echo "❌ 配置存在问题，请修复后重试"
    echo "========================================"
    echo ""
    echo "🔧 修复方法："
    echo "   1. 编辑 .env.local 文件"
    echo "   2. 将模型名称改为正确的 Qwen 模型"
    echo "   3. 重新运行此脚本验证"
    echo ""
    echo "📖 参考文档："
    echo "   cat MODEL_CONFIG_FIX.md"
    echo ""
    exit 1
fi
