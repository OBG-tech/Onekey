#!/usr/bin/env python3
"""
摄像头诊断工具 - 检测所有可用的摄像头和USB设备
"""

import cv2
import subprocess
import sys

def get_usb_cameras():
    """获取USB摄像头列表"""
    try:
        result = subprocess.run(['lsusb'], capture_output=True, text=True)
        lines = result.stdout.split('\n')
        cameras = [line for line in lines if '05a3:9230' in line.lower() or 'camera' in line.lower()]
        return cameras
    except Exception as e:
        print(f"无法运行lsusb: {e}")
        return []

def test_camera_indices(max_index=10):
    """测试所有可能的摄像头索引"""
    print("=" * 60)
    print("🔍 扫描摄像头设备 (0-{})...".format(max_index))
    print("=" * 60)
    
    available_cameras = []
    
    for idx in range(max_index):
        cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
        
        if cap.isOpened():
            # 获取摄像头属性
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            
            # 尝试读取一帧
            ret, frame = cap.read()
            read_status = "✅ 可读取" if ret else "❌ 无法读取"
            
            print(f"\n✅ /dev/video{idx}:")
            print(f"   分辨率: {width}x{height}")
            print(f"   FPS: {fps:.1f}")
            print(f"   状态: {read_status}")
            
            if ret:
                available_cameras.append(idx)
            
            cap.release()
        else:
            print(f"❌ /dev/video{idx}: 无法打开")
    
    return available_cameras

def check_v4l2_devices():
    """检查V4L2设备列表"""
    print("\n" + "=" * 60)
    print("🔍 V4L2设备列表:")
    print("=" * 60)
    
    try:
        result = subprocess.run(['v4l2-ctl', '--list-devices'], 
                              capture_output=True, text=True)
        print(result.stdout)
    except FileNotFoundError:
        print("⚠️  v4l2-ctl 未安装. 安装方法:")
        print("   sudo apt install v4l-utils")
    except Exception as e:
        print(f"错误: {e}")

def main():
    print("\n" + "=" * 60)
    print("📹 摄像头诊断工具")
    print("=" * 60)
    
    # 1. USB摄像头
    print("\n1️⃣  USB摄像头 (lsusb):")
    print("-" * 60)
    usb_cameras = get_usb_cameras()
    if usb_cameras:
        for cam in usb_cameras:
            print(f"  {cam}")
    else:
        print("  未检测到USB摄像头")
    
    # 2. V4L2设备列表
    check_v4l2_devices()
    
    # 3. 测试所有索引
    available = test_camera_indices(max_index=10)
    
    # 4. 总结
    print("\n" + "=" * 60)
    print("📊 诊断总结:")
    print("=" * 60)
    print(f"✅ 可用摄像头: {len(available)} 个")
    if available:
        print(f"   索引: {available}")
        print(f"\n💡 建议配置:")
        print(f"   export CAMERAS={','.join(map(str, available))}")
        print(f"   或在 start_multicam.sh 中使用: --cameras {','.join(map(str, available))}")
    else:
        print("❌ 未检测到可用摄像头")
        print("\n🔧 故障排查:")
        print("   1. 检查USB连接")
        print("   2. 确认摄像头权限: ls -l /dev/video*")
        print("   3. 将用户加入video组: sudo usermod -aG video $USER")
        print("   4. 重新登录或重启")
    
    print("\n" + "=" * 60)

if __name__ == '__main__':
    main()
