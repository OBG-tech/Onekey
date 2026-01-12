#!/usr/bin/env python3
"""
Sync individual JSON cards to the main moments.json file
This ensures all converted cards appear in the web interface at port 8082
"""

import json
import os
from pathlib import Path
from datetime import datetime

def load_json_file(filepath):
    """Load a JSON file"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {filepath}: {e}")
        return None

def sync_to_moments_json():
    """Sync all individual .json files to the main moments.json"""
    key_moments_dir = Path("/home/artinx/onekey/integrated_data/key_moments")
    moments_json_file = key_moments_dir / "moments.json"
    
    # Load existing moments.json
    if moments_json_file.exists():
        with open(moments_json_file, 'r', encoding='utf-8') as f:
            moments_data = json.load(f)
    else:
        moments_data = {"moments": []}
    
    existing_moments = moments_data.get("moments", [])
    existing_ids = {m['id'] for m in existing_moments}
    
    print(f"Existing moments in moments.json: {len(existing_moments)}")
    
    # Find all individual .json files (excluding moments.json and backups)
    json_files = []
    for file in key_moments_dir.glob("*.json"):
        if file.name == "moments.json" or file.name.startswith("moments.backup"):
            continue
        json_files.append(file)
    
    print(f"Found {len(json_files)} individual .json files")
    
    # Add new moments
    added_count = 0
    for json_file in sorted(json_files):
        moment = load_json_file(json_file)
        if moment and moment.get('id'):
            if moment['id'] not in existing_ids:
                existing_moments.append(moment)
                existing_ids.add(moment['id'])
                added_count += 1
                print(f"  + Added: {moment['id']}")
    
    # Sort by timestamp
    existing_moments.sort(key=lambda m: m.get('timestamp', 0))
    
    # Create backup
    if moments_json_file.exists():
        backup_file = key_moments_dir / f"moments.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(backup_file, 'w', encoding='utf-8') as f:
            json.dump(moments_data, f, ensure_ascii=False, indent=2)
        print(f"\n✓ Backup created: {backup_file.name}")
    
    # Save updated moments.json
    moments_data['moments'] = existing_moments
    with open(moments_json_file, 'w', encoding='utf-8') as f:
        json.dump(moments_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'='*60}")
    print(f"Sync complete!")
    print(f"Total moments in moments.json: {len(existing_moments)}")
    print(f"Newly added: {added_count}")
    print(f"{'='*60}")
    print(f"\n✅ The web interface at port 8082 should now show all {len(existing_moments)} cards!")

if __name__ == "__main__":
    sync_to_moments_json()
