# -*- coding: utf-8 -*-

import json
import os
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any
import glob
import re

# Define paths
BASE_DIR = Path("/home/nucleus/1214zzh/1215zzh/integrated_data/key_moments")
MOMENTS_FILE = BASE_DIR / "moments.json"

@dataclass
class KeyMoment:
    id: str
    timestamp: float
    frame_number: int
    source: str
    frame_path: str
    video_path: str = ""
    video_duration: float = 0
    time_str: str = ""
    duration_seconds: float = 0
    user_note: str = ""
    transcript: str = ""
    asr_provider: str = ""
    asr_model: str = ""
    asr_model_dir: str = ""
    ai_description: str = ""
    ai_tagline: str = ""
    ai_importance: float = 0.0
    ai_tags: List[str] = field(default_factory=list)
    analysis: str = ""
    llm_provider: str = ""
    llm_model: str = ""
    person_count: int = 0
    track_ids: List[int] = field(default_factory=list)
    narrative_role: str = ""
    narrative_text: str = ""

def load_moments() -> Dict[str, dict]:
    if not MOMENTS_FILE.exists():
        return {}
    
    with open(MOMENTS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
        moments_list = data.get('moments', [])
        # Return dict keyed by ID for easy lookup
        return {m['id']: m for m in moments_list}, data.get('stats', {})

def scan_files():
    # Find all anchor_*.jpg files
    pattern = str(BASE_DIR / "anchor_*.jpg")
    files = glob.glob(pattern)
    return sorted(files)

def repair():
    existing_moments, stats = load_moments()
    print(f"Loaded {len(existing_moments)} existing moments from JSON.")
    
    found_files = scan_files()
    print(f"Found {len(found_files)} anchor image files on disk.")
    
    final_moments = []
    
    # Process all found files
    for file_path in found_files:
        p = Path(file_path)
        stem = p.stem # e.g. anchor_1765439249_464
        
        # Determine video path (assume same name .mp4)
        video_path = p.with_suffix(".mp4")
        video_path_str = str(video_path) if video_path.exists() else ""
        
        # Check if exists in JSON
        if stem in existing_moments:
            moment_data = existing_moments[stem]
            # UPDATE PATHS to match current location
            moment_data['frame_path'] = str(p)
            moment_data['video_path'] = video_path_str
            final_moments.append(moment_data)
        else:
            # Create NEW entry
            print(f"Reconstructing missing moment: {stem}")
            
            # Parse filename for data
            # Format: anchor_{timestamp}_{framenum}
            match = re.match(r"anchor_(\d+)_(\d+)", stem)
            ts = 0.0
            frame = 0
            if match:
                ts = float(match.group(1))
                frame = int(match.group(2))
            
            new_moment = KeyMoment(
                id=stem,
                timestamp=ts,
                frame_number=frame,
                source="user_anchor",
                frame_path=str(p),
                video_path=video_path_str
            )
            final_moments.append(asdict(new_moment))
            
    print(f"Total moments after repair: {len(final_moments)}")
    
    # Save back
    output_data = {
        'moments': final_moments,
        'stats': stats, # Keep existing stats or update?
        'last_updated': "2025-12-15T15:40:00" # approximate
    }
    
    with open(MOMENTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print("Saved repaired moments.json")

if __name__ == "__main__":
    repair()
