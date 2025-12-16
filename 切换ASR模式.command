#!/bin/bash
cd "$(dirname "$0")"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🎤 实时语音识别(ASR) 模式切换"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "请选择ASR模式："
echo ""
echo "1) 通义千问云端实时ASR (推荐：最快最准，需网络)"
echo "2) FunASR 离线识别 (需手动安装模型)"
echo "3) FireRedASR 离线模式 (CPU, beam_size=1, 较慢)"
echo "4) FireRedASR 离线模式 (CPU, beam_size=3, 最慢最准)"
echo ""
read -p "请输入选项 (1-4): " choice

case $choice in
    1)
        echo "ASR_PROVIDER=qwen" > .env.asr.tmp
        echo ""
        echo "✅ 已切换到: 通义千问云端实时ASR (paraformer-realtime-v2)"
        echo "   - 识别速度最快 (200-500ms 延迟)"
        echo "   - 准确率高，自动标点"
        echo "   - 需要网络连接和DASHSCOPE_API_KEY"
        ;;
    2)
        echo "ASR_PROVIDER=funasr" > .env.asr.tmp
        echo "FUNASR_MODEL=iic/SenseVoiceSmall" >> .env.asr.tmp
        echo ""
        echo "✅ 已切换到: FunASR 离线识别"
        echo "   - 识别速度快"
        echo "   - 需要手动下载模型"
        echo "   - 适合离线场景"
        ;;
    3)
        echo "ASR_PROVIDER=fireredasr" > .env.asr.tmp
        echo "FIREREDASR_BEAM_SIZE=1" >> .env.asr.tmp
        echo "FIREREDASR_USE_GPU=0" >> .env.asr.tmp
        echo ""
        echo "✅ 已切换到: FireRedASR (CPU, beam_size=1, 快速模式)"
        echo "   - 识别速度较快，准确率略低"
        echo "   - CPU模式仍有几十秒延迟"
        ;;
    4)
        echo "ASR_PROVIDER=fireredasr" > .env.asr.tmp
        echo "FIREREDASR_BEAM_SIZE=3" >> .env.asr.tmp
        echo "FIREREDASR_USE_GPU=0" >> .env.asr.tmp
        echo ""
        echo "✅ 已切换到: FireRedASR (CPU, beam_size=3, 准确模式)"
        echo "   - 识别准确率高，速度慢"
        echo "   - CPU模式延迟可能超过1分钟"
        ;;
    *)
        echo "❌ 无效选项，已取消"
        exit 1
        ;;
esac

# 合并到.env.local
if [ -f .env.local ]; then
    # 删除旧的ASR配置行
    sed -i '' '/^ASR_PROVIDER=/d' .env.local
    sed -i '' '/^FIREREDASR_BEAM_SIZE=/d' .env.local
    sed -i '' '/^FIREREDASR_USE_GPU=/d' .env.local
    sed -i '' '/^FUNASR_MODEL=/d' .env.local
    # 追加新配置
    cat .env.asr.tmp >> .env.local
else
    mv .env.asr.tmp .env.local
fi

rm -f .env.asr.tmp

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "💡 提示: 需要重启系统才能生效"
echo "   请运行: ./一键重启系统.command"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
read -p "按回车键退出..."
