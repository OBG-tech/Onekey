#!/bin/bash
# 清空会话脚本 - 使新启动的web界面不显示以前的记录
# 旧数据会被归档保存，不会被删除
#
# 用法: ./clear_session.sh

# 切换到脚本所在目录
cd "$(dirname "$0")"

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   🧹 清空会话 - 归档旧数据                            ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

# 数据目录
DATA_DIR="integrated_data"
MOMENTS_DIR="$DATA_DIR/key_moments"
MOMENTS_FILE="$MOMENTS_DIR/moments.json"
BUTTON_LOG="button_log.txt"

# 归档目录
ARCHIVE_DIR="archives"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
SESSION_ARCHIVE="$ARCHIVE_DIR/session_$TIMESTAMP"

# 检查moments文件是否存在
if [ ! -f "$MOMENTS_FILE" ]; then
    echo -e "${YELLOW}⚠️  moments.json 不存在，无需清理${NC}"
    exit 0
fi

# 统计当前记录数量
MOMENT_COUNT=$(python3 -c "import json; data=json.load(open('$MOMENTS_FILE')); print(len(data.get('moments', [])))" 2>/dev/null)
if [ -z "$MOMENT_COUNT" ]; then
    MOMENT_COUNT=0
fi

if [ "$MOMENT_COUNT" -eq 0 ]; then
    echo -e "${YELLOW}⚠️  当前没有关键时刻记录，无需清理${NC}"
    exit 0
fi

echo -e "${YELLOW}📊 当前状态:${NC}"
echo -e "   - 关键时刻数量: ${GREEN}$MOMENT_COUNT${NC} 条"
echo ""

# 确认操作
read -p "确定要归档这些记录并清空当前会话吗? [y/N]: " confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    echo -e "${YELLOW}操作已取消${NC}"
    exit 0
fi

echo ""
echo -e "${YELLOW}🔄 开始归档...${NC}"

# 创建归档目录
mkdir -p "$SESSION_ARCHIVE"

# 归档 moments.json
echo -e "   📦 归档 moments.json..."
cp "$MOMENTS_FILE" "$SESSION_ARCHIVE/moments.json"

# 归档关键时刻相关的媒体文件（图片和视频）
echo -e "   📦 归档媒体文件..."
MEDIA_COUNT=0
for file in $(find "$MOMENTS_DIR" -maxdepth 1 -type f \( -name "*.jpg" -o -name "*.mp4" -o -name "*.txt" \) 2>/dev/null); do
    if [ -f "$file" ]; then
        mv "$file" "$SESSION_ARCHIVE/"
        ((MEDIA_COUNT++))
    fi
done
echo -e "      已归档 ${GREEN}$MEDIA_COUNT${NC} 个媒体文件"

# 归档 button_log.txt
if [ -f "$BUTTON_LOG" ]; then
    echo -e "   📦 归档 button_log.txt..."
    cp "$BUTTON_LOG" "$SESSION_ARCHIVE/button_log.txt"
    # 清空但保留文件
    > "$BUTTON_LOG"
fi

# 创建空的 moments.json
echo -e "   🔄 创建空的 moments.json..."
cat > "$MOMENTS_FILE" << 'EOF'
{
  "moments": [],
  "stats": {
    "total_moments": 0,
    "user_anchors": 0,
    "ai_detected": 0,
    "speech_markers": 0
  },
  "last_updated": ""
}
EOF

# 更新 last_updated 时间戳
python3 -c "
import json
from datetime import datetime
with open('$MOMENTS_FILE', 'r') as f:
    data = json.load(f)
data['last_updated'] = datetime.now().isoformat()
with open('$MOMENTS_FILE', 'w') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
" 2>/dev/null

echo ""
echo -e "${GREEN}✅ 归档完成!${NC}"
echo ""
echo -e "${BLUE}📁 归档位置: ${NC}$SESSION_ARCHIVE"
echo -e "${BLUE}📊 归档内容:${NC}"
echo -e "   - ${GREEN}$MOMENT_COUNT${NC} 条关键时刻记录"
echo -e "   - ${GREEN}$MEDIA_COUNT${NC} 个媒体文件"
echo ""
echo -e "${GREEN}🎉 新会话已准备就绪，web界面将不显示旧记录${NC}"
echo -e "${YELLOW}   提示: 旧数据保存在 $SESSION_ARCHIVE${NC}"
echo ""
