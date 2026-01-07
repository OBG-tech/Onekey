#!/bin/bash
# ============================================================
# macOS 专用清理会话脚本
# 兼容 BSD 工具 (macOS)
# ============================================================

set -e
cd "$(dirname "$0")"

# 配置
INTEGRATED_DATA="integrated_data"
KEY_MOMENTS="$INTEGRATED_DATA/key_moments"
ARCHIVES="archives"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo ""
echo "============================================================"
echo "🗂️  清理当前会话 (macOS 版本)"
echo "============================================================"
echo ""

# ============================================================
# 1. 创建归档目录
# ============================================================
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
ARCHIVE_DIR="$ARCHIVES/session_$TIMESTAMP"

echo -e "${BLUE}📦 创建归档目录...${NC}"
mkdir -p "$ARCHIVE_DIR"

# ============================================================
# 2. 归档关键时刻数据
# ============================================================
echo -e "${BLUE}📁 归档关键时刻数据...${NC}"

if [ -d "$KEY_MOMENTS" ]; then
    MOMENT_COUNT=$(find "$KEY_MOMENTS" -name "*.json" | wc -l | tr -d ' ')
    
    if [ "$MOMENT_COUNT" -gt 0 ]; then
        echo "   发现 $MOMENT_COUNT 个关键时刻"
        
        # macOS 兼容的复制命令
        cp -R "$KEY_MOMENTS" "$ARCHIVE_DIR/"
        
        echo -e "${GREEN}   ✓ 已归档到: $ARCHIVE_DIR/key_moments${NC}"
    else
        echo -e "${YELLOW}   ⚠️  没有关键时刻数据需要归档${NC}"
    fi
else
    echo -e "${YELLOW}   ⚠️  关键时刻目录不存在${NC}"
fi

# ============================================================
# 3. 归档音频文件 (可选)
# ============================================================
AUDIO_DIR="$INTEGRATED_DATA/audio"
if [ -d "$AUDIO_DIR" ] && [ "$(find "$AUDIO_DIR" -type f | wc -l | tr -d ' ')" -gt 0 ]; then
    echo -e "${BLUE}🎤 归档音频文件...${NC}"
    mkdir -p "$ARCHIVE_DIR/audio"
    cp "$AUDIO_DIR"/* "$ARCHIVE_DIR/audio/" 2>/dev/null || true
    echo -e "${GREEN}   ✓ 音频文件已归档${NC}"
fi

# ============================================================
# 4. 归档转录文本 (可选)
# ============================================================
TRANSCRIPT_DIR="$INTEGRATED_DATA/transcripts"
if [ -d "$TRANSCRIPT_DIR" ] && [ "$(find "$TRANSCRIPT_DIR" -type f | wc -l | tr -d ' ')" -gt 0 ]; then
    echo -e "${BLUE}📝 归档转录文本...${NC}"
    mkdir -p "$ARCHIVE_DIR/transcripts"
    cp "$TRANSCRIPT_DIR"/* "$ARCHIVE_DIR/transcripts/" 2>/dev/null || true
    echo -e "${GREEN}   ✓ 转录文本已归档${NC}"
fi

# ============================================================
# 5. 清理当前数据
# ============================================================
echo ""
echo -e "${YELLOW}⚠️  即将清理当前会话数据${NC}"
echo "   归档位置: $ARCHIVE_DIR"
echo ""
read -p "确认清理? (y/N): " -n 1 -r
echo

if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${BLUE}🗑️  清理中...${NC}"
    
    # 清理关键时刻
    if [ -d "$KEY_MOMENTS" ]; then
        rm -rf "${KEY_MOMENTS:?}"/*
        echo -e "${GREEN}   ✓ 已清理关键时刻数据${NC}"
    fi
    
    # 清理音频
    if [ -d "$AUDIO_DIR" ]; then
        rm -f "$AUDIO_DIR"/*.wav 2>/dev/null || true
        rm -f "$AUDIO_DIR"/*.webm 2>/dev/null || true
        echo -e "${GREEN}   ✓ 已清理音频文件${NC}"
    fi
    
    # 清理转录
    if [ -d "$TRANSCRIPT_DIR" ]; then
        rm -f "$TRANSCRIPT_DIR"/*.txt 2>/dev/null || true
        echo -e "${GREEN}   ✓ 已清理转录文本${NC}"
    fi
    
    # 清理关键帧
    if [ -d "$INTEGRATED_DATA/key_frames" ]; then
        rm -f "$INTEGRATED_DATA/key_frames"/*.jpg 2>/dev/null || true
        echo -e "${GREEN}   ✓ 已清理关键帧${NC}"
    fi
    
    # 清理临时文件
    rm -f context.txt 2>/dev/null || true
    rm -f button_log.txt 2>/dev/null || true
    
    echo ""
    echo -e "${GREEN}✅ 会话清理完成!${NC}"
    echo ""
    
    # 显示归档信息
    ARCHIVE_SIZE=$(du -sh "$ARCHIVE_DIR" | cut -f1)
    echo "📊 归档信息:"
    echo "   位置: $ARCHIVE_DIR"
    echo "   大小: $ARCHIVE_SIZE"
    
    # macOS 兼容的文件计数
    if [ -d "$ARCHIVE_DIR/key_moments" ]; then
        ARCHIVED_MOMENTS=$(find "$ARCHIVE_DIR/key_moments" -name "*.json" | wc -l | tr -d ' ')
        echo "   关键时刻: $ARCHIVED_MOMENTS 个"
    fi
else
    echo ""
    echo -e "${YELLOW}❌ 已取消清理${NC}"
fi

echo ""
echo "============================================================"
