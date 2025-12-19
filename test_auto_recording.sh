#!/bin/bash
# 测试自动重启脚本的录音功能

PORT=8082

echo "🧪 测试自动录音功能..."
echo ""

# 等待服务启动
echo "⏳ 等待服务启动（10秒）..."
sleep 10

# 测试API
echo "📡 测试录音API..."
response=$(curl -s -X POST "http://localhost:${PORT}/api/realtime_asr/start")

echo "响应: ${response}"
echo ""

if echo "${response}" | grep -q '"success":true'; then
    echo "✅ 录音功能正常！"
    
    # 检查状态
    echo ""
    echo "📊 检查录音状态..."
    status=$(curl -s "http://localhost:${PORT}/api/realtime_asr/status")
    echo "${status}" | python3 -m json.tool 2>/dev/null || echo "${status}"
else
    echo "❌ 录音功能异常"
    echo "可能原因："
    echo "  1. 服务未完全启动"
    echo "  2. PyAudio未安装"
    echo "  3. 麦克风权限问题"
fi
