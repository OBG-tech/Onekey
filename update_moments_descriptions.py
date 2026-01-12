#!/usr/bin/env python3
"""
Update moments.json with full descriptions from individual JSON files
This replaces "待处理" descriptions with actual AI analysis
"""

import json
from pathlib import Path
from datetime import datetime

def update_moments_with_descriptions():
    """Update moments in moments.json with descriptions from individual files"""
    key_moments_dir = Path("/home/artinx/onekey/integrated_data/key_moments")
    moments_json_file = key_moments_dir / "moments.json"
    
    # Load existing moments.json
    with open(moments_json_file, 'r', encoding='utf-8') as f:
        moments_data = json.load(f)
    
    moments = moments_data.get("moments", [])
    print(f"Loaded {len(moments)} moments from moments.json")
    
    # Create a mapping of moment IDs to their index
    moment_map = {m['id']: i for i, m in enumerate(moments)}
    
    # Find all individual .json files
    json_files = [f for f in key_moments_dir.glob("*.json") 
                  if f.name != "moments.json" and not f.name.startswith("moments.backup")]
    
    print(f"Found {len(json_files)} individual .json files")
    
    # Update moments with full descriptions
    updated_count = 0
    for json_file in sorted(json_files):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                new_moment = json.load(f)
            
            moment_id = new_moment.get('id')
            if not moment_id or moment_id not in moment_map:
                continue
            
            idx = moment_map[moment_id]
            old_moment = moments[idx]
            
            # Check if we need to update (if current description is empty or "待处理")
            old_desc = old_moment.get('ai_description', '').strip()
            new_desc = new_moment.get('ai_description', '').strip()
            
            needs_update = (
                not old_desc or 
                old_desc == '待处理' or 
                old_desc == 'AI处理中…' or
                (new_desc and len(new_desc) > len(old_desc))
            )
            
            if needs_update:
                # Update fields that might have better data
                for field in ['ai_description', 'ai_tagline', 'transcript', 'analysis', 
                             'ai_tags', 'ai_importance', 'ai_framework_tags', 
                             'llm_provider', 'llm_model', 'asr_provider', 'asr_model']:
                    if field in new_moment:
                        new_value = new_moment[field]
                        # Only update if new value is better
                        if field in ['ai_description', 'transcript', 'analysis']:
                            if new_value and new_value.strip() and new_value.strip() != '待处理':
                                moments[idx][field] = new_value
                                updated_count += 1
                                print(f"  ✓ Updated {moment_id}: {field}")
                        else:
                            moments[idx][field] = new_value
        
        except Exception as e:
            print(f"  ✗ Error processing {json_file.name}: {e}")
            continue
    
    if updated_count == 0:
        print("\n⚠️ No updates needed - all moments already have descriptions")
        return
    
    # Create backup
    backup_file = key_moments_dir / f"moments.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(backup_file, 'w', encoding='utf-8') as f:
        json.dump(moments_data, f, ensure_ascii=False, indent=2)
    print(f"\n✓ Backup created: {backup_file.name}")
    
    # Save updated moments.json
    moments_data['moments'] = moments
    with open(moments_json_file, 'w', encoding='utf-8') as f:
        json.dump(moments_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*60}")
    print(f"Update complete!")
    print(f"Updated {updated_count} field(s) across moments")
    print(f"{'='*60}")
    print(f"\n✅ Descriptions restored! Restart the system to see changes at http://localhost:8082")

if __name__ == "__main__":
    update_moments_with_descriptions()
