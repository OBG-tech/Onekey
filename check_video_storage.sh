#!/bin/bash
# 视频文件存储状态查看脚本

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   📹 视频文件存储状态报告                             ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

# 检查数据目录
if [ ! -d "integrated_data" ]; then
    echo -e "${RED}❌ 未找到 integrated_data 目录${NC}"
    exit 1
fi

# 1. 关键时刻视频
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}[1] 关键时刻视频 (integrated_data/key_moments/)${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if [ -d "integrated_data/key_moments" ]; then
    # 统计视频数量
    TOTAL_MP4=$(find integrated_data/key_moments -name "*.mp4" 2>/dev/null | wc -l)
    ANCHOR_MP4=$(find integrated_data/key_moments -name "anchor_*.mp4" 2>/dev/null | wc -l)
    MULTIMODAL_MP4=$(find integrated_data/key_moments -name "multimodal_*.mp4" 2>/dev/null | wc -l)
    
    # 计算总大小
    TOTAL_SIZE=$(du -sh integrated_data/key_moments 2>/dev/null | awk '{print $1}')
    
    echo -e "${GREEN}  📊 统计信息：${NC}"
    echo "    • 总视频数量: ${TOTAL_MP4} 个"
    echo "    • 手动标记 (anchor): ${ANCHOR_MP4} 个"
    echo "    • AI检测 (multimodal): ${MULTIMODAL_MP4} 个"
    echo "    • 目录总大小: ${TOTAL_SIZE}"
    echo ""
    
    if [ $TOTAL_MP4 -gt 0 ]; then
        echo -e "${GREEN}  📹 最新的5个视频：${NC}"
        find integrated_data/key_moments -name "*.mp4" -printf '%T@ %p\n' 2>/dev/null | \
            sort -rn | head -5 | while read timestamp path; do
            SIZE=$(du -h "$path" 2>/dev/null | awk '{print $1}')
            DATE=$(date -d "@${timestamp%.*}" "+%Y-%m-%d %H:%M:%S" 2>/dev/null || echo "Unknown")
            BASENAME=$(basename "$path")
            echo "    • [$DATE] $BASENAME ($SIZE)"
        done
        echo ""
        
        # 显示完整路径示例
        FIRST_VIDEO=$(find integrated_data/key_moments -name "*.mp4" 2>/dev/null | head -1)
        if [ -n "$FIRST_VIDEO" ]; then
            ABS_PATH=$(readlink -f "$FIRST_VIDEO" 2>/dev/null)
            echo -e "${YELLOW}  💡 完整路径示例：${NC}"
            echo "    $ABS_PATH"
            echo ""
        fi
    else
        echo -e "${YELLOW}  ⚠️  暂无关键时刻视频${NC}"
        echo ""
    fi
else
    echo -e "${RED}  ❌ 目录不存在${NC}"
    echo ""
fi

# 2. OBS录制视频
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}[2] OBS录制视频（完整录像）${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

echo -e "${YELLOW}  ℹ️  OBS录像不在项目目录中，请在OBS中查看设置：${NC}"
echo "    OBS → 文件 → 设置 → 输出 → 录像路径"
echo ""

# 尝试查找常见位置
FOUND_OBS=false
for DIR in ~/Videos ~/视频 ~/Movies ~/Documents/Videos; do
    if [ -d "$DIR" ]; then
        COUNT=$(find "$DIR" -maxdepth 1 -name "*.mp4" -o -name "*.mkv" 2>/dev/null | wc -l)
        if [ $COUNT -gt 0 ]; then
            FOUND_OBS=true
            SIZE=$(du -sh "$DIR" 2>/dev/null | awk '{print $1}')
            echo -e "${GREEN}  📁 发现可能的录像目录: $DIR${NC}"
            echo "    • 视频文件数: $COUNT 个"
            echo "    • 目录大小: $SIZE"
            
            # 显示最新的3个视频
            echo "    • 最新文件:"
            find "$DIR" -maxdepth 1 \( -name "*.mp4" -o -name "*.mkv" \) -printf '%T@ %p\n' 2>/dev/null | \
                sort -rn | head -3 | while read timestamp path; do
                SIZE=$(du -h "$path" 2>/dev/null | awk '{print $1}')
                BASENAME=$(basename "$path")
                echo "      - $BASENAME ($SIZE)"
            done
            echo ""
        fi
    fi
done

if [ "$FOUND_OBS" = false ]; then
    echo -e "${YELLOW}  ⚠️  未在常见位置找到OBS录像${NC}"
    echo "    可能原因："
    echo "    1. OBS录制路径设置在其他位置"
    echo "    2. 还未进行过OBS录制"
    echo ""
fi

# 3. 其他相关文件
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}[3] 其他相关数据${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

# 关键帧图片
if [ -d "integrated_data/key_frames" ]; then
    KF_COUNT=$(find integrated_data/key_frames -name "*.jpg" 2>/dev/null | wc -l)
    KF_SIZE=$(du -sh integrated_data/key_frames 2>/dev/null | awk '{print $1}')
    echo -e "${GREEN}  📸 关键帧图片: $KF_COUNT 个 ($KF_SIZE)${NC}"
else
    echo -e "${YELLOW}  📸 关键帧图片: 目录不存在${NC}"
fi

# 音频文件
if [ -d "integrated_data/audio" ]; then
    AUDIO_COUNT=$(find integrated_data/audio -name "*.wav" -o -name "*.mp3" 2>/dev/null | wc -l)
    AUDIO_SIZE=$(du -sh integrated_data/audio 2>/dev/null | awk '{print $1}')
    echo -e "${GREEN}  🎤 音频录制: $AUDIO_COUNT 个 ($AUDIO_SIZE)${NC}"
else
    echo -e "${YELLOW}  🎤 音频录制: 目录不存在${NC}"
fi

# 人脸数据库
if [ -d "integrated_data/face_database" ]; then
    FACE_COUNT=$(find integrated_data/face_database -name "*.jpg" 2>/dev/null | wc -l)
    FACE_SIZE=$(du -sh integrated_data/face_database 2>/dev/null | awk '{print $1}')
    echo -e "${GREEN}  👤 人脸数据库: $FACE_COUNT 个 ($FACE_SIZE)${NC}"
else
    echo -e "${YELLOW}  👤 人脸数据库: 目录不存在${NC}"
fi

# 转写文本
if [ -d "integrated_data/transcripts" ]; then
    TRANS_COUNT=$(find integrated_data/transcripts -name "*.txt" 2>/dev/null | wc -l)
    TRANS_SIZE=$(du -sh integrated_data/transcripts 2>/dev/null | awk '{print $1}')
    echo -e "${GREEN}  📝 语音转写: $TRANS_COUNT 个 ($TRANS_SIZE)${NC}"
else
    echo -e "${YELLOW}  📝 语音转写: 目录不存在${NC}"
fi

echo ""

# 4. 磁盘空间
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}[4] 磁盘空间${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

DISK_USAGE=$(df -h . | tail -1 | awk '{print $5}' | sed 's/%//')
DISK_AVAIL=$(df -h . | tail -1 | awk '{print $4}')
DISK_TOTAL=$(df -h . | tail -1 | awk '{print $2}')

echo "  磁盘总容量: $DISK_TOTAL"
echo "  可用空间: $DISK_AVAIL"

if [ $DISK_USAGE -lt 70 ]; then
    echo -e "  ${GREEN}使用率: ${DISK_USAGE}% ✅ 空间充足${NC}"
elif [ $DISK_USAGE -lt 85 ]; then
    echo -e "  ${YELLOW}使用率: ${DISK_USAGE}% ⚠️  建议清理${NC}"
else
    echo -e "  ${RED}使用率: ${DISK_USAGE}% ❌ 空间紧张！${NC}"
fi

echo ""

# integrated_data 总大小
TOTAL_DATA_SIZE=$(du -sh integrated_data 2>/dev/null | awk '{print $1}')
echo -e "${GREEN}  📊 integrated_data 总大小: $TOTAL_DATA_SIZE${NC}"
echo ""

# 5. 快捷操作
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${YELLOW}[5] 快捷操作${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

echo ""
echo -e "${GREEN}📦 备份关键时刻视频：${NC}"
echo "  tar -czf moments_backup_\$(date +%Y%m%d_%H%M%S).tar.gz integrated_data/key_moments/"
echo ""

echo -e "${GREEN}🗑️  清理旧数据：${NC}"
echo "  python3 archive_data.py"
echo ""

echo -e "${GREEN}📂 打开关键时刻目录：${NC}"
echo "  xdg-open integrated_data/key_moments/"
echo ""

echo -e "${GREEN}📋 查看详细信息：${NC}"
echo "  cat 📹\ 视频存储位置说明.md"
echo ""

echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   ✅ 报告完成                                         ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
