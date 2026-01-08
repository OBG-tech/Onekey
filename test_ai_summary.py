
import os
import sys
import base64
import cv2
import numpy as np
from key_moments_manager import KeyMomentsManager

# Verify API Key
api_key = os.environ.get("DASHSCOPE_API_KEY")
if not api_key:
    # Try loading from .env.local manually
    try:
        with open(".env.local", "r") as f:
            for line in f:
                if line.strip().startswith("DASHSCOPE_API_KEY="):
                    api_key = line.strip().split("=", 1)[1]
                    os.environ["DASHSCOPE_API_KEY"] = api_key
                    print(f"Loaded API KEY from .env.local: {api_key[:5]}...")
    except FileNotFoundError:
        print("Creating dummy .env.local for test if needed")

if not os.environ.get("DASHSCOPE_API_KEY"):
    print("❌ DASHSCOPE_API_KEY not set")
    sys.exit(1)

print("✅ Found API Key")

# Initialize Manager
try:
    mgr = KeyMomentsManager()
    print("✅ KeyMomentsManager initialized")
except Exception as e:
    print(f"❌ Failed to init manager: {e}")
    sys.exit(1)
    
# Create dummy image
img = np.zeros((100, 100, 3), dtype=np.uint8)
cv2.rectangle(img, (20, 20), (80, 80), (0, 255, 0), -1)
ret, buffer = cv2.imencode('.jpg', img)
b64 = base64.b64encode(buffer).decode('utf-8')

# Test _run_vision_llm
print("🔄 Testing _run_vision_llm...")
try:
    res = mgr._run_vision_llm(
        image_base64=b64,
        prompt="Describe this image in one word.",
        max_tokens=10
    )
    print(f"✅ Result: {res}")
except Exception as e:
    print(f"❌ _run_vision_llm Failed: {e}")
    import traceback
    traceback.print_exc()

# Test logic in _analyze_moment_with_ai (mocking)
print("\n🔄 Testing _analyze_moment_with_ai logic...")
# We can't easily call it because it depends on existing moments.
# But we can verify if proper imports are there
import openai
print(f"✅ OpenAI module: {openai.__version__}")
