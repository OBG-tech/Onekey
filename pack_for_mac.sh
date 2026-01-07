#!/bin/bash
# Mac迁移打包脚本 - 只复制必要文件，排除历史数据
# 使用方法: ./pack_for_mac.sh [目标目录名]

# 目标目录名（默认）
TARGET_DIR=${1:-"onekey_clean"}

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   📦 Mac迁移打包工具 - 精简版                        ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

# 检查是否在onekey目录
if [ ! -f "integrated_system.py" ]; then
    echo -e "${RED}❌ 请在onekey项目根目录运行此脚本${NC}"
    exit 1
fi

# 创建临时目录
echo -e "${YELLOW}📁 创建目标目录: $TARGET_DIR${NC}"
if [ -d "$TARGET_DIR" ]; then
    echo -e "${YELLOW}⚠️  目标目录已存在，是否删除? [y/N]: ${NC}"
    read -r CONFIRM
    if [ "$CONFIRM" = "y" ] || [ "$CONFIRM" = "Y" ]; then
        rm -rf "$TARGET_DIR"
    else
        echo -e "${RED}❌ 取消操作${NC}"
        exit 1
    fi
fi

mkdir -p "$TARGET_DIR"

echo ""
echo -e "${GREEN}📋 复制文件清单:${NC}"
echo ""

# 1. Python源代码
echo -e "${YELLOW}[1/10] 复制 Python 源代码...${NC}"
cp *.py "$TARGET_DIR/" 2>/dev/null
echo "  ✅ Python文件"

# 2. 配置文件
echo -e "${YELLOW}[2/10] 复制配置文件...${NC}"
cp .env.local.example "$TARGET_DIR/" 2>/dev/null
cp requirements.txt "$TARGET_DIR/" 2>/dev/null
cp .gitignore "$TARGET_DIR/" 2>/dev/null
echo "  ✅ 配置文件"

# 3. 启动脚本
echo -e "${YELLOW}[3/10] 复制启动脚本...${NC}"
cp *.sh "$TARGET_DIR/" 2>/dev/null
cp *.command "$TARGET_DIR/" 2>/dev/null
echo "  ✅ 启动脚本"

# 4. HTML界面
echo -e "${YELLOW}[4/10] 复制 HTML 界面...${NC}"
cp *.html "$TARGET_DIR/" 2>/dev/null
cp *.snippet "$TARGET_DIR/" 2>/dev/null
echo "  ✅ HTML界面"

# 5. 文档
echo -e "${YELLOW}[5/10] 复制文档...${NC}"
cp *.md "$TARGET_DIR/" 2>/dev/null
echo "  ✅ 文档文件"

# 6. 模型文件
echo -e "${YELLOW}[6/10] 复制模型文件...${NC}"
cp *.pt "$TARGET_DIR/" 2>/dev/null
echo "  ✅ YOLO模型"

# 7. 子目录（重要的）
echo -e "${YELLOW}[7/10] 复制子目录...${NC}"

# 复制完整的子目录
for dir in MagicLLM FireRedASR vision multi_person_tracker linux_deployment; do
    if [ -d "$dir" ]; then
        cp -r "$dir" "$TARGET_DIR/" 2>/dev/null
        echo "  ✅ $dir/"
    fi
done

# web目录
if [ -d "web" ]; then
    mkdir -p "$TARGET_DIR/web"
    cp web/*.html "$TARGET_DIR/web/" 2>/dev/null
    echo "  ✅ web/"
fi

# 8. 创建空的数据目录结构
echo -e "${YELLOW}[8/10] 创建数据目录结构...${NC}"
mkdir -p "$TARGET_DIR/integrated_data"/{face_database,key_frames,key_moments,snapshots,audio,transcripts,logs,analysis_results,meeting_notes}
echo "  ✅ integrated_data/ (空目录)"

# 9. 复制示例/配置文件
echo -e "${YELLOW}[9/10] 复制配置示例...${NC}"
if [ -d "models" ]; then
    cp -r models "$TARGET_DIR/" 2>/dev/null
    echo "  ✅ models/"
fi

if [ -d "pretrained_models" ]; then
    mkdir -p "$TARGET_DIR/pretrained_models"
    echo "  ✅ pretrained_models/ (空目录，需Mac上下载)"
fi

# 10. 创建README
echo -e "${YELLOW}[10/10] 创建迁移说明...${NC}"
cat > "$TARGET_DIR/MIGRATION_README.md" << 'EOF'
# Mac 迁移包使用说明

## 📦 包含内容

本精简包只包含必要的代码和配置文件，不包含历史数据。

### ✅ 已包含
- 所有Python源代码
- 启动脚本和配置文件
- HTML前端界面
- 文档和说明
- YOLO模型文件
- 空的数据目录结构

### ❌ 未包含（需在Mac上重新创建）
- Python虚拟环境（需重新安装）
- 历史录像数据
- 人脸数据库
- 关键帧图片
- 日志文件

## 🚀 Mac上的安装步骤

### 1. 解压文件
```bash
cd ~/Desktop
# 如果是压缩包，先解压
tar -xzf onekey_clean.tar.gz
```

### 2. 创建虚拟环境
```bash
cd onekey_clean
python3 -m venv .venv
source .venv/bin/activate
```

### 3. 安装依赖
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. 配置环境变量
```bash
cp .env.local.example .env.local
# 编辑 .env.local 填入你的API密钥
nano .env.local
```

### 5. 检查Mac环境
```bash
./check_macos_env.sh
```

### 6. 启动系统
```bash
# 使用Mac专用启动脚本
./🔄\ 一键重启系统.command
```

## 📚 重要文档

- `macOS_M2_移植指南.md` - Mac平台完整配置指南
- `macOS_快速参考.md` - MacOS常用命令
- `README.md` - 项目说明
- `自动录音录像指南.md` - 录音录像功能说明

## ⚠️ 注意事项

1. **模型文件**: YOLO模型已包含，但InsightFace模型需要首次运行时下载
2. **OBS设置**: 需要在Mac上重新配置OBS
3. **摄像头**: Mac摄像头索引可能不同，使用 `detect_cameras_macos.py` 检测
4. **权限**: Mac可能需要授予终端、摄像头、麦克风权限

## 🔗 获取帮助

- 查看 `macOS_M2_移植指南.md` 获取详细的Mac配置步骤
- 遇到问题查看 `📚 重要操作指令汇总.md`

---

**打包时间**: $(date)
**原项目大小**: ~125GB
**精简后大小**: ~500MB
EOF

echo "  ✅ MIGRATION_README.md"

# 统计信息
echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║   📊 打包完成                                         ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════╝${NC}"
echo ""

# 计算大小
ORIGINAL_SIZE=$(du -sh . 2>/dev/null | awk '{print $1}')
PACKED_SIZE=$(du -sh "$TARGET_DIR" 2>/dev/null | awk '{print $1}')

echo -e "${GREEN}统计信息:${NC}"
echo "  原项目大小: $ORIGINAL_SIZE"
echo "  精简后大小: $PACKED_SIZE"
echo "  目标目录: $TARGET_DIR"
echo ""

# 文件数量
FILE_COUNT=$(find "$TARGET_DIR" -type f | wc -l)
echo "  总文件数: $FILE_COUNT 个"
echo ""

# 下一步
echo -e "${YELLOW}📦 下一步操作:${NC}"
echo ""
echo -e "${GREEN}1. 打包成压缩文件:${NC}"
echo "   tar -czf ${TARGET_DIR}.tar.gz $TARGET_DIR"
echo ""
echo -e "${GREEN}2. 复制到Mac:${NC}"
echo "   scp ${TARGET_DIR}.tar.gz your-mac:~/Desktop/"
echo ""
echo -e "${GREEN}3. 或使用网盘/U盘传输${NC}"
echo ""

# 询问是否打包
echo -e "${YELLOW}是否现在打包成 .tar.gz? [Y/n]: ${NC}"
read -r PACK
if [ "$PACK" != "n" ] && [ "$PACK" != "N" ]; then
    echo ""
    echo -e "${YELLOW}正在打包...${NC}"
    tar -czf "${TARGET_DIR}.tar.gz" "$TARGET_DIR"
    
    if [ $? -eq 0 ]; then
        ARCHIVE_SIZE=$(du -sh "${TARGET_DIR}.tar.gz" 2>/dev/null | awk '{print $1}')
        echo -e "${GREEN}✅ 打包完成!${NC}"
        echo "  压缩包: ${TARGET_DIR}.tar.gz"
        echo "  大小: $ARCHIVE_SIZE"
        echo ""
        echo -e "${GREEN}现在可以传输到Mac了！${NC}"
    else
        echo -e "${RED}❌ 打包失败${NC}"
    fi
fi

echo ""
echo -e "${GREEN}✅ 完成！${NC}"
