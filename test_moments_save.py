# -*- coding: utf-8 -*-

import os
import sys
import json
from pathlib import Path

# Mock environment
os.environ["LLM_PROVIDER"] = "qwen"

# Import manager
sys.path.insert(0, "/home/artinx/onekey")
from key_moments_manager import KeyMomentsManager, KeyMoment

def test_manager():
    print("Testing KeyMomentsManager...")
    data_dir = Path("test_data")
    data_dir.mkdir(exist_ok=True)
    
    # Initialize
    mgr = KeyMomentsManager(data_dir=data_dir)
    print(f"Initial moments: {len(mgr.moments)}")
    
    # Create a dummy moment
    import time
    moment = KeyMoment(
        id=f"test_{int(time.time())}",
        timestamp=time.time(),
        frame_number=100,
        source="user_anchor",
        frame_path="path/to/img.jpg"
    )
    
    # Manual append and save (simulating mark_user_anchor)
    mgr.moments.append(moment)
    mgr.stats["user_anchors"] += 1
    print("Appending moment...")
    mgr._save_moments()
    
    # Validating file
    moments_file = mgr.moments_dir / "moments.json"
    if not moments_file.exists():
        print("ERROR: moments.json not found")
        return
        
    with open(moments_file, 'r') as f:
        data = json.load(f)
        print(f"File content: moments count = {len(data.get('moments', []))}")
        print(f"Stats: {data.get('stats')}")
        
    if len(data.get('moments')) == 1:
        print("SUCCESS: Moment saved correctly")
    else:
        print("FAILURE: Moment list empty in file")

if __name__ == "__main__":
    test_manager()
