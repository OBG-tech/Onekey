#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将 log.txt 中的按钮按下记录导入到 moments.json

这些记录是在视频系统未运行时按下的按钮，没有对应的视频帧。
导入后会作为特殊的 "no_video" 类型 moments 显示在 Web 界面上。

用法: python3 import_log_to_moments.py [--dry-run]
"""

import os
import sys
import json
import re
from pathlib import Path
from datetime import datetime

# 数据目录
DATA_DIR = Path("integrated_data/key_moments")
MOMENTS_FILE = DATA_DIR / "moments.json"
LOG_FILE = Path("log.txt")

def parse_log_entries():
    """解析 log.txt 中的记录"""
    if not LOG_FILE.exists():
        print(f"❌ 未找到 {LOG_FILE}")
        return []
    
    entries = []
    with open(LOG_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            
            # 格式: [2025-12-19 21:16:30] 00:00:00.000
            match = re.match(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]\s*(\d{2}:\d{2}:\d{2}\.\d+)', line)
            if match:
                datetime_str = match.group(1)
                duration_str = match.group(2)
                
                # 解析日期时间
                dt = datetime.strptime(datetime_str, '%Y-%m-%d %H:%M:%S')
                timestamp = dt.timestamp()
                
                entries.append({
                    'datetime': datetime_str,
                    'timestamp': timestamp,
                    'duration': duration_str,
                    'time_str': dt.strftime('%H:%M:%S')
                })
    
    return entries

def load_moments():
    """加载 moments.json"""
    if not MOMENTS_FILE.exists():
        return {'moments': [], 'stats': {}}
    
    with open(MOMENTS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_moments(data):
    """保存 moments.json"""
    data['last_updated'] = datetime.now().isoformat()
    with open(MOMENTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ 已保存 {MOMENTS_FILE}")

def get_existing_timestamps(data):
    """获取现有 moments 的时间戳集合"""
    timestamps = set()
    for m in data.get('moments', []):
        ts = m.get('timestamp', 0)
        # 使用1秒容差
        timestamps.add(int(ts))
    return timestamps

def main():
    dry_run = '--dry-run' in sys.argv
    
    print("=" * 60)
    print("📥 导入 log.txt 按钮记录到 moments.json")
    print("=" * 60)
    
    # 解析 log.txt
    entries = parse_log_entries()
    print(f"\n📊 log.txt 中的记录: {len(entries)} 条")
    
    if not entries:
        print("❌ 没有找到有效的记录")
        return
    
    # 加载现有 moments
    data = load_moments()
    existing_ts = get_existing_timestamps(data)
    print(f"📊 现有 moments: {len(data.get('moments', []))} 条")
    
    # 找出新记录（不在现有 moments 中的）
    new_entries = []
    for entry in entries:
        ts_int = int(entry['timestamp'])
        # 检查是否已存在（±2秒容差）
        exists = False
        for existing in existing_ts:
            if abs(ts_int - existing) <= 2:
                exists = True
                break
        
        if not exists:
            new_entries.append(entry)
    
    print(f"📊 新记录（不重复）: {len(new_entries)} 条")
    
    if not new_entries:
        print("\n✅ 没有需要导入的新记录")
        return
    
    if dry_run:
        print("\n🔍 Dry-run 模式 - 将要导入的记录:")
        for entry in new_entries[:10]:
            print(f"   - {entry['datetime']}")
        if len(new_entries) > 10:
            print(f"   ... 还有 {len(new_entries) - 10} 条")
        return
    
    print(f"\n🚀 开始导入 {len(new_entries)} 条记录...\n")
    
    imported = 0
    for entry in new_entries:
        ts = entry['timestamp']
        moment_id = f"log_{int(ts)}"
        
        # 创建 moment 条目
        moment = {
            "id": moment_id,
            "timestamp": ts,
            "frame_number": 0,
            "source": "log_import",  # 特殊来源标识
            "frame_path": "",  # 无图片
            "video_path": "",  # 无视频
            "video_duration": 0.0,
            "time_str": entry['time_str'],
            "duration_seconds": 0.0,
            "user_note": f"📝 按钮按下 (无视频记录)",
            "transcript": "",
            "asr_provider": "",
            "asr_model": "",
            "asr_model_dir": "",
            "ai_description": f"按钮按下于 {entry['datetime']}（视频系统未运行）",
            "ai_tagline": "按钮按下记录📋",
            "ai_importance": 0.1,
            "ai_tags": ["log_import", "no_video"],
            "ai_framework_tags": "",
            "analysis": f"此记录来自 log.txt，按钮按下时视频录制系统未运行，无对应的视频帧数据。\n时间: {entry['datetime']}",
            "llm_provider": "",
            "llm_model": "",
            "person_count": 0,
            "track_ids": [],
            "narrative_role": "",
            "narrative_text": ""
        }
        
        data['moments'].append(moment)
        imported += 1
        print(f"  ✅ 导入: {entry['datetime']}")
    
    # 按时间戳排序
    data['moments'].sort(key=lambda m: m.get('timestamp', 0))
    
    # 更新统计
    if 'stats' not in data:
        data['stats'] = {}
    data['stats']['total_moments'] = len(data['moments'])
    
    # 保存
    print(f"\n📦 保存结果...")
    save_moments(data)
    
    print(f"\n{'=' * 60}")
    print(f"✅ 完成! 导入了 {imported} 条记录")
    print(f"{'=' * 60}")

if __name__ == "__main__":
    main()
