#!/bin/bash
# 快速验证自动录音录像功能
# 检查系统各项功能是否正常启动

PORT=${1:-8082}

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   🔍 自动录音录像功能检查                             ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

# 检查1: 系统进程
echo -e "${YELLOW}[1/6] 检查系统进程...${NC}"
if pgrep -f "integrated_system.py" > /dev/null; then
    PID=$(pgrep -f "integrated_system.py")
    echo -e "${GREEN}  ✅ 系统正在运行 (PID: $PID)${NC}"
else
    echo -e "${RED}  ❌ 系统未运行${NC}"
    echo -e "${YELLOW}  💡 请先运行: ./start_auto_recording.sh${NC}"
    exit 1
fi
echo ""

# 检查2: Web服务
echo -e "${YELLOW}[2/6] 检查Web服务...${NC}"
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:${PORT}/integrated_final_live.html")
if [ "$HTTP_CODE" == "200" ]; then
    echo -e "${GREEN}  ✅ Web服务正常 (端口: $PORT)${NC}"
else
    echo -e "${RED}  ❌ Web服务异常 (HTTP $HTTP_CODE)${NC}"
fi
echo ""

# 检查3: OBS进程
echo -e "${YELLOW}[3/6] 检查OBS状态...${NC}"
if pgrep -x "obs" > /dev/null; then
    echo -e "${GREEN}  ✅ OBS正在运行${NC}"
else
    echo -e "${YELLOW}  ⚠️  OBS未运行${NC}"
fi
echo ""

# 检查4: v4l2loopback虚拟摄像机
echo -e "${YELLOW}[4/6] 检查OBS虚拟摄像机...${NC}"
if lsmod | grep -q v4l2loopback; then
    USE_COUNT=$(lsmod | grep v4l2loopback | awk '{print $3}')
    if [ "$USE_COUNT" != "0" ] && [ -n "$USE_COUNT" ]; then
        echo -e "${GREEN}  ✅ 虚拟摄像机已激活 (使用计数: $USE_COUNT)${NC}"
    else
        echo -e "${YELLOW}  ⚠️  v4l2loopback已加载但未被使用${NC}"
        echo -e "${YELLOW}  💡 请在OBS中启动虚拟摄像机${NC}"
    fi
else
    echo -e "${RED}  ❌ v4l2loopback模块未加载${NC}"
fi
echo ""

# 检查5: 语音识别状态
echo -e "${YELLOW}[5/6] 检查语音识别状态...${NC}"
ASR_STATUS=$(curl -s "http://localhost:${PORT}/api/realtime_asr/status" 2>/dev/null)

if echo "$ASR_STATUS" | grep -q '"is_recording":true' 2>/dev/null; then
    echo -e "${GREEN}  ✅ 语音识别正在录音${NC}"
    
    # 提取麦克风信息
    if echo "$ASR_STATUS" | grep -q '"microphone"' 2>/dev/null; then
        MIC_NAME=$(echo "$ASR_STATUS" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('microphone', {}).get('name', 'Unknown'))" 2>/dev/null)
        if [ -n "$MIC_NAME" ]; then
            echo -e "${GREEN}  📢 麦克风: $MIC_NAME${NC}"
        fi
    fi
elif echo "$ASR_STATUS" | grep -q '"is_recording":false' 2>/dev/null; then
    echo -e "${RED}  ❌ 语音识别未启动${NC}"
    echo ""
    echo -e "${YELLOW}  🔧 尝试自动启动...${NC}"
    START_RESPONSE=$(curl -s -X POST "http://localhost:${PORT}/api/realtime_asr/start" 2>/dev/null)
    
    if echo "$START_RESPONSE" | grep -q '"success":true' 2>/dev/null; then
        echo -e "${GREEN}  ✅ 语音识别已成功启动${NC}"
    else
        echo -e "${RED}  ❌ 自动启动失败${NC}"
        echo -e "${YELLOW}  💡 请在Web界面手动点击【开始录音】按钮${NC}"
        if [ -n "$START_RESPONSE" ]; then
            echo -e "${YELLOW}  响应: $START_RESPONSE${NC}"
        fi
    fi
else
    echo -e "${YELLOW}  ⚠️  无法获取语音识别状态${NC}"
    echo -e "${YELLOW}  响应: ${ASR_STATUS}${NC}"
fi
echo ""

# 检查6: 磁盘空间
echo -e "${YELLOW}[6/6] 检查磁盘空间...${NC}"
DISK_USAGE=$(df -h . | tail -1 | awk '{print $5}' | sed 's/%//')
DISK_AVAIL=$(df -h . | tail -1 | awk '{print $4}')

if [ "$DISK_USAGE" -lt 80 ]; then
    echo -e "${GREEN}  ✅ 磁盘空间充足 (已用: ${DISK_USAGE}%, 可用: ${DISK_AVAIL})${NC}"
elif [ "$DISK_USAGE" -lt 90 ]; then
    echo -e "${YELLOW}  ⚠️  磁盘空间不足 (已用: ${DISK_USAGE}%, 可用: ${DISK_AVAIL})${NC}"
    echo -e "${YELLOW}  💡 建议清理旧数据${NC}"
else
    echo -e "${RED}  ❌ 磁盘空间严重不足 (已用: ${DISK_USAGE}%, 可用: ${DISK_AVAIL})${NC}"
    echo -e "${YELLOW}  ⚠️  录制可能失败！${NC}"
fi
echo ""

# 总结
echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   📊 检查报告总结                                     ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

# OBS录制提醒
echo -e "${YELLOW}⚠️  重要提醒：${NC}"
echo -e "${YELLOW}请确认OBS中已手动点击【开始录制】按钮！${NC}"
echo ""
echo -e "${GREEN}💡 验证方法：${NC}"
echo "1. 打开OBS窗口"
echo "2. 检查控制区域是否显示 '停止录制' 按钮（而不是'开始录制'）"
echo "3. 检查OBS状态栏是否显示红色录制图标和录制时间"
echo ""

# 快捷命令
echo -e "${GREEN}🛠️  常用命令：${NC}"
echo "• 查看实时日志: tail -f service_output.log"
echo "• 停止系统: kill $PID"
echo "• 查看Web界面: http://localhost:${PORT}/integrated_final_live.html"
echo "• 控制OBS录制: ./obs_recording_control.sh"
echo ""

echo -e "${GREEN}✅ 检查完成！${NC}"
