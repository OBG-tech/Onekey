
with open('/home/artinx/onekey/backup_before_recovery/multi_camera_capture.py', 'rb') as f:
    data = f.read()

target = b'print(f"\\n'
idx = data.find(target)
if idx != -1:
    snippet = data[idx:idx+150]
    print(f"Hex dump at {idx}:")
    print(snippet.hex(' '))
    try:
        print("Decoded utf-8:", snippet.decode('utf-8'))
    except:
        print("Decode utf-8 failed")
else:
    print("Target not found")
