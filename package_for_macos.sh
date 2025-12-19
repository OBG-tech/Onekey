#!/bin/bash
# ============================================================
# OneKey macOS 打包脚本
# ============================================================
# 用法: ./package_for_macos.sh [保留视频数量]
# 默认保留最近10个视频

set -e
cd "$(dirname "$0")"

# 配置
KEEP_VIDEOS=${1:-10}
PACKAGE_NAME="onekey_macos"
PACKAGE_DIR="/tmp/${PACKAGE_NAME}"
OUTPUT_FILE="${HOME}/onekey_macos_$(date +%Y%m%d_%H%M%S).tar.gz"

echo "🚀 开始打包 OneKey for macOS"
echo "   保留最近 ${KEEP_VIDEOS} 个视频"
echo ""

# ============================================================
# 第一步：清理临时文件
# ============================================================
echo "🗑️  清理临时文件..."
rm -rf __pycache__/
rm -f *.log debug_*.log
rm -f context.txt
rm -f integrated_data/key_moments/*_backup_*.json
rm -f integrated_data/audio/*.wav 2>/dev/null || true
rm -rf .vscode/

# ============================================================
# 第二步：清理key_frames（最大节省空间）
# ============================================================
echo "🗑️  清理 key_frames (可重新生成)..."
rm -rf integrated_data/key_frames/*

# ============================================================
# 第三步：处理视频文件 - 只保留最近N个
# ============================================================
echo "📹 处理视频文件..."
VIDEO_DIR="integrated_data/key_moments"
TOTAL_VIDEOS=$(find "$VIDEO_DIR" -name "*.mp4" 2>/dev/null | wc -l)
echo "   当前视频数量: $TOTAL_VIDEOS"

if [ "$TOTAL_VIDEOS" -gt "$KEEP_VIDEOS" ]; then
    echo "   保留最近 $KEEP_VIDEOS 个视频，删除 $((TOTAL_VIDEOS - KEEP_VIDEOS)) 个旧视频..."
    
    # 按修改时间排序，删除最旧的
    find "$VIDEO_DIR" -name "*.mp4" -printf '%T@ %p\n' 2>/dev/null | \
        sort -n | head -n -${KEEP_VIDEOS} | cut -d' ' -f2- | \
        xargs -r rm -f
    
    # 同时删除对应的临时文件
    find "$VIDEO_DIR" -name "*_temp.mp4" -delete 2>/dev/null || true
    
    echo "   ✅ 保留了最近 $KEEP_VIDEOS 个视频"
else
    echo "   ✅ 视频数量 ($TOTAL_VIDEOS) 不超过限制，保留全部"
fi

# ============================================================
# 第四步：创建打包目录
# ============================================================
echo "📦 创建打包目录..."
rm -rf "$PACKAGE_DIR"
mkdir -p "$PACKAGE_DIR"

# ============================================================
# 第五步：复制核心代码文件
# ============================================================
echo "📝 复制核心代码..."
CORE_FILES=(
    "integrated_system.py"
    "key_moments_manager.py"
    "ai_live_commentary.py"
    "audio_manager.py"
    "microphone_recorder.py"
    "realtime_asr.py"
    "meeting_notes.py"
    "esp32_server.py"
    "archive_data.py"
    "LAUNCH_GUI.py"
    "_repair_moments.py"
    "update_old_cards.py"
)

for file in "${CORE_FILES[@]}"; do
    if [ -f "$file" ]; then
        cp "$file" "$PACKAGE_DIR/"
        echo "   ✓ $file"
    fi
done

# ============================================================
# 第六步：复制前端文件
# ============================================================
echo "🌐 复制前端文件..."
cp integrated_final_live.html "$PACKAGE_DIR/"
cp -r web "$PACKAGE_DIR/" 2>/dev/null || true

# HTML备份
cp "integrated final.html" "$PACKAGE_DIR/" 2>/dev/null || true

# ============================================================
# 第七步：复制配置文件
# ============================================================
echo "⚙️  复制配置文件..."
cp requirements.txt "$PACKAGE_DIR/"
cp .env.local.example "$PACKAGE_DIR/"
cp start.sh "$PACKAGE_DIR/"
cp start_live.sh "$PACKAGE_DIR/"

# ============================================================
# 第八步：复制模型文件
# ============================================================
echo "🤖 复制模型文件..."
cp yolo11n.pt "$PACKAGE_DIR/"
cp yolov8n-seg.pt "$PACKAGE_DIR/"
cp -r models "$PACKAGE_DIR/" 2>/dev/null || true
cp -r pretrained_models "$PACKAGE_DIR/"

# ============================================================
# 第九步：复制数据目录（保留结构和最近数据）
# ============================================================
echo "💾 复制数据目录..."
mkdir -p "$PACKAGE_DIR/integrated_data"

# 复制整个 key_moments 目录（已清理旧视频）
cp -r integrated_data/key_moments "$PACKAGE_DIR/integrated_data/"

# 复制人脸数据库
cp -r integrated_data/face_database "$PACKAGE_DIR/integrated_data/"

# 创建空的子目录
mkdir -p "$PACKAGE_DIR/integrated_data/key_frames"
mkdir -p "$PACKAGE_DIR/integrated_data/audio"
mkdir -p "$PACKAGE_DIR/integrated_data/transcripts"
mkdir -p "$PACKAGE_DIR/integrated_data/meeting_notes"
mkdir -p "$PACKAGE_DIR/integrated_data/snapshots"
mkdir -p "$PACKAGE_DIR/integrated_data/analysis_results"

# 复制会议纪要
cp -r integrated_data/meeting_notes/* "$PACKAGE_DIR/integrated_data/meeting_notes/" 2>/dev/null || true
cp -r integrated_data/transcripts/* "$PACKAGE_DIR/integrated_data/transcripts/" 2>/dev/null || true

# ============================================================
# 第十步：复制文档
# ============================================================
echo "📚 复制文档..."
DOC_FILES=(
    "README.md"
    "INSTALL_UBUNTU.md"
    "使用说明.md"
    "ARCHIVE_GUIDE.md"
    "AI_PROMPT_STYLE_GUIDE.md"
    "CARD_DESIGN_GUIDE.md"
    "📚 重要操作指令汇总.md"
)

for file in "${DOC_FILES[@]}"; do
    if [ -f "$file" ]; then
        cp "$file" "$PACKAGE_DIR/"
    fi
done

# ============================================================
# 第十一步：创建macOS专用脚本
# ============================================================
echo "🍎 创建 macOS 安装脚本..."

cat > "$PACKAGE_DIR/install_macos.sh" << 'EOF'
#!/bin/bash
# ============================================================
# OneKey macOS 安装脚本
# ============================================================

set -e
cd "$(dirname "$0")"

echo "🍎 OneKey macOS 安装程序"
echo ""

# 检查 Homebrew
if ! command -v brew &> /dev/null; then
    echo "❌ 需要先安装 Homebrew: https://brew.sh"
    exit 1
fi

# 安装系统依赖
echo "📦 安装系统依赖..."
brew install portaudio ffmpeg python@3.11 || true

# 创建虚拟环境
echo "🐍 创建 Python 虚拟环境..."
python3 -m venv .venv
source .venv/bin/activate

# 升级pip
pip install --upgrade pip

# 安装Python包
echo "📥 安装 Python 依赖..."
pip install opencv-python numpy ultralytics lap
pip install anthropic dashscope openai
pip install PyAudio

# 复制环境变量模板
if [ ! -f .env.local ]; then
    cp .env.local.example .env.local
    echo ""
    echo "⚠️  请编辑 .env.local 添加你的 API 密钥："
    echo "   - DASHSCOPE_API_KEY (阿里云)"
    echo "   - ANTHROPIC_API_KEY (Claude - 可选)"
    echo ""
fi

echo ""
echo "✅ 安装完成！"
echo ""
echo "下一步："
echo "  1. 编辑 .env.local 添加 API 密钥"
echo "  2. 运行 ./start_macos.sh 启动系统"
echo ""
EOF

cat > "$PACKAGE_DIR/start_macos.sh" << 'EOF'
#!/bin/bash
# ============================================================
# OneKey macOS 启动脚本
# ============================================================

cd "$(dirname "$0")"

# 激活虚拟环境
source .venv/bin/activate

# 加载环境变量
if [ -f .env.local ]; then
    export $(cat .env.local | grep -v '^#' | xargs)
fi

# 启动系统
echo "🚀 启动 OneKey 智能视频分析系统..."
echo "   浏览器访问: http://localhost:8080"
echo ""

python3 integrated_system.py --obs --ai
EOF

chmod +x "$PACKAGE_DIR/install_macos.sh"
chmod +x "$PACKAGE_DIR/start_macos.sh"
chmod +x "$PACKAGE_DIR/start.sh"
chmod +x "$PACKAGE_DIR/start_live.sh"

# ============================================================
# 第十二步：压缩打包
# ============================================================
echo "📦 压缩打包..."
cd /tmp
tar -czvf "$OUTPUT_FILE" "$PACKAGE_NAME"

# 清理临时目录
rm -rf "$PACKAGE_DIR"

# ============================================================
# 完成
# ============================================================
FINAL_SIZE=$(du -h "$OUTPUT_FILE" | cut -f1)
echo ""
echo "============================================================"
echo "✅ 打包完成！"
echo "============================================================"
echo "📦 输出文件: $OUTPUT_FILE"
echo "📊 文件大小: $FINAL_SIZE"
echo ""
echo "在 macOS 上使用："
echo "  1. 复制文件到 macOS"
echo "  2. tar -xzvf $(basename $OUTPUT_FILE)"
echo "  3. cd onekey_macos"
echo "  4. ./install_macos.sh"
echo "  5. 编辑 .env.local 添加 API 密钥"
echo "  6. ./start_macos.sh"
echo ""
