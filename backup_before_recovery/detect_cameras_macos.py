#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
macOS 相机检测和配置工具
用于检测可用相机并生成配置建议
"""

import cv2
import sys
from typing import List, Dict, Optional

def detect_cameras(max_index: int = 10) -> List[Dict]:
    """
    检测所有可用的相机设备
    
    Args:
        max_index: 最大检测索引
        
    Returns:
        相机信息列表
    """
    cameras = []
    
    print("🔍 正在扫描相机设备...")
    print("-" * 60)
    
    for idx in range(max_index):
        cap = cv2.VideoCapture(idx)
        
        if cap.isOpened():
            # 尝试读取一帧
            ret, frame = cap.read()
            
            if ret and frame is not None:
                # 获取相机属性
                width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                fps = int(cap.get(cv2.CAP_PROP_FPS)) or 30
                backend = cap.getBackendName()
                
                camera_info = {
                    'index': idx,
                    'width': width,
                    'height': height,
                    'fps': fps,
                    'backend': backend,
                    'is_virtual': _is_virtual_camera(width, height)
                }
                
                cameras.append(camera_info)
                
                # 显示信息
                print(f"✓ 相机 {idx}:")
                print(f"  分辨率: {width}x{height}")
                print(f"  帧率: {fps} FPS")
                print(f"  后端: {backend}")
                
                if camera_info['is_virtual']:
                    print(f"  类型: 🎥 虚拟相机 (可能是 OBS)")
                else:
                    print(f"  类型: 📹 物理相机")
                print()
            
            cap.release()
    
    print("-" * 60)
    return cameras

def _is_virtual_camera(width: int, height: int) -> bool:
    """
    判断是否为虚拟相机
    OBS 虚拟相机通常是 1920x1080 或 1280x720
    """
    virtual_resolutions = [
        (1920, 1080),
        (1280, 720),
        (2560, 1440),
        (3840, 2160)
    ]
    return (width, height) in virtual_resolutions

def find_best_camera(cameras: List[Dict], prefer_virtual: bool = False) -> Optional[int]:
    """
    找到最佳相机索引
    
    Args:
        cameras: 相机列表
        prefer_virtual: 是否优先选择虚拟相机
        
    Returns:
        推荐的相机索引
    """
    if not cameras:
        return None
    
    if prefer_virtual:
        # 查找虚拟相机
        virtual_cameras = [c for c in cameras if c['is_virtual']]
        if virtual_cameras:
            return virtual_cameras[0]['index']
    
    # 返回第一个相机
    return cameras[0]['index']

def generate_config_recommendation(cameras: List[Dict]):
    """生成配置建议"""
    print("\n" + "=" * 60)
    print("📝 配置建议")
    print("=" * 60)
    
    if not cameras:
        print("❌ 未检测到可用相机!")
        print("\n请检查:")
        print("  1. 相机是否已连接")
        print("  2. 系统权限设置:")
        print("     系统偏好设置 → 安全性与隐私 → 相机")
        print("     确保允许 Terminal/iTerm 访问相机")
        return
    
    print(f"\n✅ 检测到 {len(cameras)} 个相机设备\n")
    
    # 物理相机
    physical_cameras = [c for c in cameras if not c['is_virtual']]
    if physical_cameras:
        print("📹 物理相机:")
        for cam in physical_cameras:
            print(f"  - 索引 {cam['index']}: {cam['width']}x{cam['height']}")
    
    # 虚拟相机
    virtual_cameras = [c for c in cameras if c['is_virtual']]
    if virtual_cameras:
        print("\n🎥 虚拟相机 (OBS):")
        for cam in virtual_cameras:
            print(f"  - 索引 {cam['index']}: {cam['width']}x{cam['height']}")
    
    # 推荐配置
    print("\n" + "-" * 60)
    print("推荐启动命令:")
    print("-" * 60)
    
    if physical_cameras:
        idx = physical_cameras[0]['index']
        print(f"\n# 使用物理相机 (内置/外接):")
        print(f"python3 integrated_system.py --camera {idx}")
        print(f"python3 integrated_system.py --camera {idx} --ai")
    
    if virtual_cameras:
        idx = virtual_cameras[0]['index']
        print(f"\n# 使用 OBS 虚拟相机:")
        print(f"python3 integrated_system.py --camera {idx}")
        print(f"python3 integrated_system.py --obs  # 自动检测")
    
    # .env.local 建议
    print("\n" + "-" * 60)
    print(".env.local 配置建议:")
    print("-" * 60)
    
    primary_camera = cameras[0]['index']
    print(f"\nDEFAULT_CAMERA_INDEX={primary_camera}")
    
    if virtual_cameras:
        print(f"OBS_CAMERA_INDEX={virtual_cameras[0]['index']}")
    
    print("\n" + "=" * 60)

def test_camera(index: int, duration: int = 5):
    """
    测试指定相机
    
    Args:
        index: 相机索引
        duration: 测试时长(秒)
    """
    print(f"\n📹 测试相机 {index} ({duration}秒)...")
    print("按 'q' 提前退出\n")
    
    cap = cv2.VideoCapture(index)
    
    if not cap.isOpened():
        print(f"❌ 无法打开相机 {index}")
        return
    
    import time
    start_time = time.time()
    frame_count = 0
    
    while True:
        ret, frame = cap.read()
        
        if not ret:
            print("❌ 读取帧失败")
            break
        
        frame_count += 1
        
        # 显示帧
        cv2.imshow(f'Camera {index} Test', frame)
        
        # 检查退出
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
        
        # 检查时长
        if time.time() - start_time >= duration:
            break
    
    cap.release()
    cv2.destroyAllWindows()
    
    elapsed = time.time() - start_time
    actual_fps = frame_count / elapsed
    
    print(f"\n✅ 测试完成:")
    print(f"   时长: {elapsed:.1f}秒")
    print(f"   帧数: {frame_count}")
    print(f"   实际帧率: {actual_fps:.1f} FPS")

def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='macOS 相机检测和配置工具'
    )
    parser.add_argument(
        '--test',
        type=int,
        metavar='INDEX',
        help='测试指定索引的相机'
    )
    parser.add_argument(
        '--duration',
        type=int,
        default=5,
        help='测试持续时间(秒), 默认5秒'
    )
    parser.add_argument(
        '--max-index',
        type=int,
        default=10,
        help='最大扫描索引, 默认10'
    )
    
    args = parser.parse_args()
    
    if args.test is not None:
        # 测试模式
        test_camera(args.test, args.duration)
    else:
        # 检测模式
        cameras = detect_cameras(args.max_index)
        generate_config_recommendation(cameras)
        
        if cameras:
            print("\n提示: 使用 --test INDEX 测试指定相机")
            print(f"例如: python3 {sys.argv[0]} --test {cameras[0]['index']}\n")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  用户中断")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
