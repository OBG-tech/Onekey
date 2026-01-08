# -*- coding: utf-8 -*-

import os
import sys
import json
import time
from pathlib import Path

# Add current dir to path
sys.path.append(os.getcwd())

from key_moments_manager import KeyMomentsManager, KeyMoment

# Force set env vars for testing
os.environ["DASHSCOPE_API_KEY"] = "sk-84c8ffcad83c4718827763555733ff07"
os.environ["LLM_PROVIDER"] = "qwen"
os.environ["LLM_MODEL"] = "gpt-5.1-codex-max"

def main():
    print("🔥 Initializing KeyMomentsManager...")
    mgr = KeyMomentsManager()
    
    # 强制开启 LLM Trace 以在控制台看到交互
    os.environ["KEY_MOMENT_LLM_TRACE"] = "1"

    print(f"📂 Data dir: {mgr.data_dir}")
    
    # Get current moments via API method
    moments_data = mgr.get_moments()
    print(f"🔢 Loaded moments count: {len(moments_data)}")

    # Add dummy moments if empty
    if len(moments_data) < 2:
        print("⚠️  Not enough moments, generating dummy ones for testing...")
        
        m1 = KeyMoment(
            id="test_m1",
            timestamp=1700000100.0,
            frame_number=0,
            source="camera",
            frame_path="",
            ai_tagline="User asks for Retro Style",
            ai_description="The user requested to change the UI to a Macintosh retro pixel style.",
            user_note="",
            transcript="I want black and white pixel style.",
            ai_tags=["design", "ui", "retro"]
        )
        
        m2 = KeyMoment(
            id="test_m2",
            timestamp=1700000120.0,
            frame_number=0,
            source="camera",
            frame_path="",
            ai_tagline="System applies Retro CSS",
            ai_description="The system updated the CSS files to match the retro requirements.",
            user_note="Fixed borders and fonts",
            narrative_role="rising",
            transcript="Updating the interface now.",
            ai_tags=["implementation", "css", "retro"]
        )
        
        mgr.moments.append(m1)
        mgr.moments.append(m2)
        print("✅ Added 2 dummy moments.")
        
        # Refresh data
        moments_data = mgr.get_moments()
    
    # Limit to latest 10 for speed
    if len(moments_data) > 10:
        moments_data = moments_data[-10:]
        
    print(f"\n🚀 Starting Linkography Generation using Qwen3-Max with {len(moments_data)} moments...")
    start_t = time.time()
    result = mgr.generate_linkography(moments=moments_data)
    end_t = time.time()
    
    print(f"\n⏱️  Time taken: {end_t - start_t:.2f}s")
    print("\n📋 Result:")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    
    if result.get("status") == "ok":
        edges = result.get("edges", [])
        if len(edges) > 0:
            print(f"\n✅ SUCCESS! Generated {len(edges)} links.")
        else:
            print("\n⚠️  LLM returned OK but found 0 links (maybe content not related?).")
    else:
        print(f"\n❌ FAILED: {result.get('status')}")

if __name__ == "__main__":
    main()
