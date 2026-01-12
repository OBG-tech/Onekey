#!/usr/bin/env python3
"""
Convert key moment _context.txt files to individual .json files
so they can be displayed in the web viewer at port 8082
"""

import os
import json
import re
from pathlib import Path

def load_moments_json(moments_file):
    """Load the main moments.json file"""
    if not os.path.exists(moments_file):
        print(f"Warning: {moments_file} not found")
        return {"moments": []}
    
    with open(moments_file, 'r', encoding='utf-8') as f:
        return json.load(f)

def parse_context_txt(txt_file):
    """Parse a _context.txt file to get moment_id, timestamp, user_note"""
    with open(txt_file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    data = {}
    for line in content.strip().split('\n'):
        if ':' in line:
            key, value = line.split(':', 1)
            key = key.strip()
            value = value.strip()
            if key == 'moment_id':
                data['moment_id'] = value
            elif key == 'timestamp':
                try:
                    data['timestamp'] = float(value)
                except:
                    data['timestamp'] = value
            elif key == 'user_note':
                data['user_note'] = value
    
    return data

def find_moment_in_json(moments_data, moment_id):
    """Find a moment in moments.json by its ID"""
    for moment in moments_data.get('moments', []):
        if moment.get('id') == moment_id:
            return moment
    return None

def create_json_from_txt(txt_file, moments_data):
    """Create a .json file from a _context.txt file"""
    # Parse the txt file
    txt_data = parse_context_txt(txt_file)
    moment_id = txt_data.get('moment_id')
    
    if not moment_id:
        print(f"Warning: No moment_id found in {txt_file}")
        return False
    
    # Find the corresponding entry in moments.json
    moment = find_moment_in_json(moments_data, moment_id)
    
    if moment:
        # Use the full data from moments.json
        json_data = moment
    else:
        # Create a basic structure if not found in moments.json
        print(f"Info: {moment_id} not found in moments.json, creating basic structure")
        
        # Extract base name without _context.txt
        base_name = os.path.basename(txt_file).replace('_context.txt', '')
        base_path = os.path.dirname(txt_file)
        
        json_data = {
            "id": moment_id,
            "timestamp": txt_data.get('timestamp', 0),
            "frame_number": 0,
            "source": "user_anchor" if "anchor" in moment_id else "ai" if "ai" in moment_id else "multimodal",
            "frame_path": os.path.join(base_path, f"{base_name}.jpg"),
            "video_path": os.path.join(base_path, f"{base_name}.mp4"),
            "user_note": txt_data.get('user_note', ''),
            "transcript": "",
            "ai_description": "待处理",
            "ai_tagline": "",
            "ai_importance": 0.0,
            "ai_tags": [],
            "analysis": "",
            "person_count": 0,
            "track_ids": []
        }
    
    # Write to .json file
    json_file = txt_file.replace('_context.txt', '.json')
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    
    print(f"✓ Created: {os.path.basename(json_file)}")
    return True

def main():
    # Set up paths
    key_moments_dir = "/home/artinx/onekey/integrated_data/key_moments"
    moments_json_file = os.path.join(key_moments_dir, "moments.json")
    
    print(f"Key moments directory: {key_moments_dir}")
    
    # Try to load from backup files first (they have full descriptions)
    print(f"Looking for backup files with full descriptions...")
    backup_files = sorted(Path(key_moments_dir).glob("moments.backup_*.json"), reverse=True)
    
    moments_data = None
    if backup_files:
        for backup_file in backup_files:
            print(f"  Trying: {backup_file.name}")
            try:
                moments_data = load_moments_json(str(backup_file))
                if moments_data and len(moments_data.get('moments', [])) > 50:
                    print(f"  ✓ Using {backup_file.name} with {len(moments_data.get('moments', []))} moments")
                    break
            except:
                continue
    
    # Fallback to main moments.json if no good backup found
    if not moments_data or len(moments_data.get('moments', [])) < 50:
        print(f"Loading moments.json...")
        moments_data = load_moments_json(moments_json_file)
    print(f"Found {len(moments_data.get('moments', []))} moments in moments.json")
    
    # Find all _context.txt files
    txt_files = []
    for file in os.listdir(key_moments_dir):
        if file.endswith('_context.txt'):
            txt_files.append(os.path.join(key_moments_dir, file))
    
    print(f"\nFound {len(txt_files)} _context.txt files to convert")
    
    if not txt_files:
        print("No _context.txt files found!")
        return
    
    # Convert each file
    print("\nConverting files...")
    success_count = 0
    for txt_file in sorted(txt_files):
        if create_json_from_txt(txt_file, moments_data):
            success_count += 1
    
    print(f"\n{'='*60}")
    print(f"Conversion complete!")
    print(f"Successfully converted: {success_count}/{len(txt_files)} files")
    print(f"{'='*60}")
    
    # List some example json files created
    json_files = [f for f in os.listdir(key_moments_dir) if f.endswith('.json') and f != 'moments.json' and not f.startswith('moments.backup')]
    if json_files:
        print(f"\nExample .json files created (first 10):")
        for json_file in sorted(json_files)[:10]:
            print(f"  - {json_file}")
        if len(json_files) > 10:
            print(f"  ... and {len(json_files) - 10} more")

if __name__ == "__main__":
    main()
