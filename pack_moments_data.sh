#!/bin/bash
# 一键打包 Key Moments 数据脚本
# 打包 19-21 号的所有 timeline 文本数据

set -e

# 获取当前日期时间作为文件名
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
PACK_DIR="/home/nucleus/onekey"
OUTPUT_FILE="${PACK_DIR}/moments_data_backup_${TIMESTAMP}.tar.gz"

echo "🗂️  开始打包 Key Moments 数据..."
echo "================================================"

# 创建临时目录
TEMP_DIR=$(mktemp -d)
BACKUP_DIR="${TEMP_DIR}/moments_backup_${TIMESTAMP}"
mkdir -p "${BACKUP_DIR}"

# 1. 打包当前活跃的 moments 数据
echo "📦 复制当前活跃数据..."
if [ -d "${PACK_DIR}/integrated_data/key_moments" ]; then
    cp -r "${PACK_DIR}/integrated_data/key_moments" "${BACKUP_DIR}/current_key_moments"
    echo "   ✅ integrated_data/key_moments"
fi

# 2. 打包会议笔记
if [ -d "${PACK_DIR}/integrated_data/meeting_notes" ]; then
    cp -r "${PACK_DIR}/integrated_data/meeting_notes" "${BACKUP_DIR}/meeting_notes"
    echo "   ✅ integrated_data/meeting_notes"
fi

# 3. 打包 12月19日的会话存档
echo "📦 复制 12月19日会话存档..."
for session_dir in "${PACK_DIR}/archives/session_20251219"*; do
    if [ -d "$session_dir" ]; then
        session_name=$(basename "$session_dir")
        cp -r "$session_dir" "${BACKUP_DIR}/archives_${session_name}"
        echo "   ✅ archives/${session_name}"
    fi
done

# 4. 打包按钮日志
if [ -f "${PACK_DIR}/button_log.txt" ]; then
    cp "${PACK_DIR}/button_log.txt" "${BACKUP_DIR}/"
    echo "   ✅ button_log.txt"
fi

# 5. 创建数据摘要
echo ""
echo "📊 生成数据摘要..."
cat > "${BACKUP_DIR}/README.txt" << EOF
====================================================
Key Moments 数据备份
生成时间: $(date '+%Y-%m-%d %H:%M:%S')
====================================================

包含内容:
---------
1. current_key_moments/
   - moments.json: 当前活跃的 timeline 数据
   - 相关的图片和视频文件

2. meeting_notes/
   - 会议笔记 JSON 文件

3. archives_session_*/
   - 12月19日的会话存档

4. button_log.txt
   - 按钮按压记录

数据统计:
---------
EOF

# 统计 moments 数量
if [ -f "${BACKUP_DIR}/current_key_moments/moments.json" ]; then
    MOMENTS_COUNT=$(grep -o '"id":' "${BACKUP_DIR}/current_key_moments/moments.json" | wc -l)
    echo "- Key Moments 数量: ${MOMENTS_COUNT}" >> "${BACKUP_DIR}/README.txt"
fi

# 统计会议笔记数量
if [ -d "${BACKUP_DIR}/meeting_notes" ]; then
    NOTES_COUNT=$(ls -1 "${BACKUP_DIR}/meeting_notes"/*.json 2>/dev/null | wc -l)
    echo "- 会议笔记数量: ${NOTES_COUNT}" >> "${BACKUP_DIR}/README.txt"
fi

# 统计按钮按压次数
if [ -f "${BACKUP_DIR}/button_log.txt" ]; then
    BUTTON_COUNT=$(wc -l < "${BACKUP_DIR}/button_log.txt")
    echo "- 按钮记录数量: ${BUTTON_COUNT}" >> "${BACKUP_DIR}/README.txt"
fi

# 6. 创建压缩包
echo ""
echo "🗜️  创建压缩包..."
cd "${TEMP_DIR}"
tar -czf "${OUTPUT_FILE}" "moments_backup_${TIMESTAMP}"

# 清理临时目录
rm -rf "${TEMP_DIR}"

# 显示结果
echo ""
echo "================================================"
echo "✅ 打包完成!"
echo ""
echo "📁 输出文件: ${OUTPUT_FILE}"
echo "📊 文件大小: $(du -h "${OUTPUT_FILE}" | cut -f1)"
echo ""
echo "解压命令: tar -xzf $(basename ${OUTPUT_FILE})"
echo "================================================"
