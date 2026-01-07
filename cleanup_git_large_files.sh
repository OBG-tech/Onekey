#!/bin/bash
# 快速修复脚本 - 移除 Git 历史中的大文件

echo "=== 开始清理 Git 仓库中的大文件 ==="

# 检查是否安装了 git filter-repo
if ! command -v git-filter-repo &> /dev/null; then
    echo "正在安装 git-filter-repo..."
    pip install git-filter-repo
fi

echo "步骤 1: 从 Git 历史中移除大文件..."

# 方法 1: 使用 git filter-branch (不需要额外安装)
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch pretrained_models/FireRedASR-AED-L/model.pth.tar yolov8n-seg.pt models/yolo11n.pt" \
  --prune-empty --tag-name-filter cat -- --all

echo "步骤 2: 清理本地仓库..."
rm -rf .git/refs/original/
git reflog expire --expire=now --all
git gc --prune=now --aggressive

echo "步骤 3: 显示当前仓库大小..."
du -sh .git

echo ""
echo "=== 清理完成！==="
echo ""
echo "下一步操作："
echo "1. 检查工作区状态: git status"
echo "2. 强制推送到远程: git push origin --force --all"
echo ""
echo "⚠️  注意: 强制推送会重写远程仓库历史！"
echo "   如果有其他协作者，请先通知他们。"
