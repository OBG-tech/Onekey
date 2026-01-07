#!/bin/bash

# 要生成的压缩包文件名
ZIP_NAME="result.zip"

# 查找并压缩所有文件名包含指定字符串的文件
zip "$ZIP_NAME" *"Replay 2025-10-24"* 2>/dev/null

echo "打包完成：$ZIP_NAME"

