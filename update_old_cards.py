#!/usr/bin/env python3
"""临时脚本：查看所有卡片的时间，然后修改最近的几个"""
import json
from pathlib import Path
from datetime import datetime

moments_file = Path("/home/nucleus/onekey/integrated_data/key_moments/moments.json")

# 读取moments
with open(moments_file, 'r', encoding='utf-8') as f:
    data = json.load(f)

print("📋 所有卡片的时间：")
for moment in data.get('moments', [])[-10:]:  # 只显示最后10个
    dt_str = moment.get('datetime', '')
    moment_id = moment['id']
    desc = moment.get('ai_description', '')[:40]
    print(f"  {dt_str} | {moment_id[:25]}... | {desc}...")

# 备份
backup_file = moments_file.parent / f"moments_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
with open(backup_file, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print(f"\n✅ 备份已保存到: {backup_file}")

# 修改最后5个卡片
modified_count = 0
moments_list = data.get('moments', [])
for moment in moments_list[-5:]:  # 修改最后5个
    old_desc = moment.get('ai_description', '')
    test_desc = f"【测试】讨论3D打印降低门槛💡"
    moment['ai_description'] = test_desc
    modified_count += 1
    print(f"✅ 修改 {moment['id'][:25]}... ({moment.get('datetime', '')})")
    print(f"   旧: {old_desc[:50]}...")
    print(f"   新: {test_desc}")

# 保存
with open(moments_file, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"\n✅ 共修改 {modified_count} 个卡片")
print(f"🔄 刷新浏览器（Ctrl+Shift+R）查看卡片是否显示: 【测试】讨论3D打印降低门槛💡")
