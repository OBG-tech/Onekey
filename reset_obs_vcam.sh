#!/bin/bash
# OBS虚拟相机完全重置脚本
# 解决OBS虚拟相机反复无法启动的问题

echo "=========================================="
echo "OBS虚拟相机完全重置"
echo "=========================================="

# 1. 停止所有相关进程
echo "🔄 停止所有OBS和分析系统进程..."
pkill -9 obs 2>/dev/null
pkill -f integrated_system.py 2>/dev/null
pkill -f esp32_server.py 2>/dev/null
sleep 2

# 2. 检查进程是否已停止
if pgrep -x obs > /dev/null; then
    echo "❌ OBS进程仍在运行，请手动关闭"
    exit 1
fi

# 3. 卸载v4l2loopback模块
echo "🔧 卸载并重新加载v4l2loopback模块..."
sudo modprobe -r v4l2loopback 2>/dev/null
sleep 1

# 4. 重新加载模块
sudo modprobe v4l2loopback devices=1 video_nr=8 card_label="OBS Virtual Camera" exclusive_caps=1

# 5. 验证设备
if [ ! -e /dev/video8 ]; then
    echo "❌ /dev/video8 设备未创建"
    exit 1
fi

echo "✅ v4l2loopback模块加载成功"

# 6. 检查设备状态
v4l2-ctl --list-devices | grep -A2 "OBS"

echo ""
echo "=========================================="
echo "✅ 重置完成！"
echo "=========================================="
echo ""
echo "接下来请按照以下步骤操作："
echo ""
echo "1. 启动OBS:"
echo "   obs &"
echo ""
echo "2. 在OBS界面中："
echo "   - 确保有至少一个场景和源"
echo "   - 菜单：工具 → 虚拟相机 → 启动"
echo ""
echo "3. 如果虚拟相机按钮灰色，请："
echo "   - 添加一个视频源（显示器捕获/窗口捕获）"
echo "   - 重启OBS再试"
echo ""
echo "4. 启动分析系统:"
echo "   cd ~/onekey && ./start_live.sh"
echo ""
