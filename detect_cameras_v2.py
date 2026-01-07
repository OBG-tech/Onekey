
import glob
import subprocess
import re
import sys
import os

DEBUG = False

def get_valid_cameras():
    valid_indices = []
    
    # 目标设备ID (ARC International Camera)
    TARGET_VENDOR = "05a3"
    TARGET_PRODUCT = "9230"

    print(f"🔍 正在扫描USB摄像头 (ID {TARGET_VENDOR}:{TARGET_PRODUCT})...", file=sys.stderr)
    
    devices = sorted(glob.glob("/dev/video*"))
    # Sort by number to keep order
    devices.sort(key=lambda x: int(re.search(r'video(\d+)', x).group(1)))

    for dev in devices:
        try:
            device_idx = int(re.search(r'video(\d+)', dev).group(1))
            sysfs_path = f"/sys/class/video4linux/video{device_idx}/device/../"
            
            # 1. 检查 vendor/product ID
            vendor_path = os.path.join(sysfs_path, "idVendor")
            product_path = os.path.join(sysfs_path, "idProduct")
            
            if not os.path.exists(vendor_path) or not os.path.exists(product_path):
                if DEBUG: print(f"  [SKIP] {dev}: No USB ID found", file=sys.stderr)
                continue
                
            with open(vendor_path, 'r') as f:
                vendor = f.read().strip()
            with open(product_path, 'r') as f:
                product = f.read().strip()
                
            if vendor != TARGET_VENDOR or product != TARGET_PRODUCT:
                if DEBUG: print(f"  [SKIP] {dev}: ID mismatch {vendor}:{product}", file=sys.stderr)
                continue

            # 2. 检查功能 (Filtering Metadata nodes)
            # Run v4l2-ctl to check device capabilities
            cmd = ["v4l2-ctl", "-d", dev, "--all"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            output = result.stdout
            
            if "Device Caps" in output:
                caps_part = output.split("Device Caps")[1].split("Media Driver Info")[0]
                
                # Check for Video Capture capability
                if "Video Capture" in caps_part: 
                     # Exclude metadata-only or incompatible nodes if necessary
                     # Usually Video Capture with MJPG support is what we want
                     if "Scanning" not in caps_part:
                        if DEBUG: print(f"  [ OK ] {dev}: Match found!", file=sys.stderr)
                        valid_indices.append(device_idx)
            
        except Exception as e:
            if DEBUG: print(f"  [ERR ] {dev}: {e}", file=sys.stderr)
            continue
            
    return valid_indices

if __name__ == "__main__":
    cams = get_valid_cameras()
    if cams:
        # Output strictly minimal string "1,2,3,4" for shell script
        print(",".join(map(str, cams)))
    else:
        # If no specific cameras found, fallback or empty
        print("")
