
with open('/home/artinx/onekey/multi_camera_capture.py', 'rb') as f:
    data = f.read()

# Find the print statement
target = b'print(f"\\n'
idx = data.find(target)
if idx != -1:
    snippet = data[idx:idx+50]
    print(f"Hex dump at {idx}:")
    print(snippet.hex(' '))
else:
    print("Target not found")
