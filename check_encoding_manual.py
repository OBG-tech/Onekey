
import codecs

filepath = '/home/artinx/onekey/multi_camera_capture.py'

try:
    with open(filepath, 'rb') as f:
        bytes_content = f.read()

    # Try decoding as gb18030
    decoded = bytes_content.decode('gb18030')
    print("Sucessfully decoded with gb18030")
    print(" First 500 chars:")
    print(decoded[:500])
except Exception as e:
    print(f"Failed to decode as gb18030: {e}")

try:
    decoded_utf8 = bytes_content.decode('utf-8')
    print("Sucessfully decoded with utf-8")
except Exception as e:
    print(f"Failed to decode as utf-8: {e}")
