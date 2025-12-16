#!/bin/bash
cd "$(dirname "$0")"

echo "📦 开始打包项目文件 (目标: Linux)..."
echo "📂 包含目录: $(pwd)"
echo "🚫 已排除: .venv, .git, __pycache__, .DS_Store, *.log"

# 输出文件名
OUT_FILE="magicrgb_linux_pack_$(date +%Y%m%d).tar.gz"

# 使用 tar 打包
# --exclude: 排除不必要的大文件和系统文件
tar -czf "$OUT_FILE" \
    --exclude='.venv' \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='.DS_Store' \
    --exclude='*.log' \
    --exclude='*.tar.gz' \
    --exclude='tmp_km_test' \
    .

echo ""
echo "✅ 打包完成!"
echo "📄 文件名: $OUT_FILE"
echo "📊 文件大小: $(du -sh "$OUT_FILE" | awk '{print $1}')"
echo ""
echo "🚀 转移步骤:"
echo "1. 将 $OUT_FILE 复制到 Linux 电脑"
echo "2. 在 Linux 上解压: tar -xzf $OUT_FILE"
echo "3. 进入目录并运行安装脚本:"
echo "   chmod +x install_ubuntu.sh"
echo "   ./install_ubuntu.sh"
echo ""
read -p "按任意键退出..."
