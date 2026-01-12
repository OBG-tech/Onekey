#!/usr/bin/env python3
"""
摄像头测试工具 - 测试MJPEG格式和FPS性能
"""

import cv2
import numpy as np
import time
import sys

def test_camera_formats(camera_idx=0):
    """测试不同的像素格式"""
    print(f"\n{'='*60}")
    print(f"🔍 测试摄像头 #{camera_idx} - 不同格式")
    print(f"{'='*60}\n")
    
    formats = [
        ('MJPG', cv2.VideoWriter_fourcc('M','J','P','G')),
        ('YUYV', cv2.VideoWriter_fourcc('Y','U','Y','V')),
    ]
    
    for format_name, fourcc in formats:
        print(f"\n📹 测试格式: {format_name}")
        print("-" * 40)
        
        cap = cv2.VideoCapture(camera_idx, cv2.CAP_V4L2)
        
        if not cap.isOpened():
            print(f"❌ 无法打开摄像头")
            continue
        
        # 设置格式
        cap.set(cv2.CAP_PROP_FOURCC, fourcc)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        # 读取实际设置
        actual_fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
        actual_fourcc_str = "".join([chr((actual_fourcc >> 8 * i) & 0xFF) for i in range(4)])
        actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fps_prop = cap.get(cv2.CAP_PROP_FPS)
        
        print(f"  实际格式: {actual_fourcc_str}")
        print(f"  实际分辨率: {actual_width}x{actual_height}")
        print(f"  实际FPS属性: {actual_fps_prop:.1f}")
        
        # 测试实际帧率
        frame_count = 0
        start_time = time.time()
        test_duration = 3.0  # 测试3秒
        
        color_issue = False
        
        while time.time() - start_time < test_duration:
            ret, frame = cap.read()
            if ret:
                frame_count += 1
                
                # 检查颜色是否正常（检测是否有紫色/洋红色问题）
                if frame_count == 1:
                    # 计算平均色彩通道
                    b, g, r = cv2.split(frame)
                    b_mean = np.mean(b)
                    g_mean = np.mean(g)
                    r_mean = np.mean(r)
                    
                    # 如果蓝色和红色都很高但绿色很低，可能是颜色问题
                    if (b_mean > 100 and r_mean > 100 and g_mean < 80):
                        color_issue = True
                        print(f"  ⚠️  检测到可能的颜色问题 (BGR均值: {b_mean:.1f}, {g_mean:.1f}, {r_mean:.1f})")
        
        elapsed = time.time() - start_time
        measured_fps = frame_count / elapsed
        
        print(f"  实测FPS: {measured_fps:.1f} ({frame_count} 帧 / {elapsed:.1f}秒)")
        
        if color_issue:
            print(f"  🎨 颜色状态: ⚠️  可能异常（紫色/洋红色）")
        else:
            print(f"  🎨 颜色状态: ✅ 正常")
        
        # 性能评估
        if measured_fps >= 28:
            print(f"  ⭐ 性能: 优秀")
        elif measured_fps >= 20:
            print(f"  ✅ 性能: 良好")
        elif measured_fps >= 15:
            print(f"  ⚠️  性能: 一般")
        else:
            print(f"  ❌ 性能: 较差")
        
        cap.release()
    
    print(f"\n{'='*60}\n")

def test_resolution_fps(camera_idx=0):
    """测试不同分辨率下的FPS"""
    print(f"\n{'='*60}")
    print(f"🎯 测试摄像头 #{camera_idx} - 分辨率与FPS")
    print(f"{'='*60}\n")
    
    resolutions = [
        (640, 480, "VGA"),
        (1280, 720, "720p"),
        (1920, 1080, "1080p"),
    ]
    
    for width, height, name in resolutions:
        print(f"\n📐 测试分辨率: {name} ({width}x{height})")
        print("-" * 40)
        
        cap = cv2.VideoCapture(camera_idx, cv2.CAP_V4L2)
        
        if not cap.isOpened():
            print(f"❌ 无法打开摄像头")
            break
        
        # 使用MJPEG格式
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M','J','P','G'))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        if actual_width != width or actual_height != height:
            print(f"  ⚠️  实际分辨率: {actual_width}x{actual_height}")
        
        # 测试FPS
        frame_count = 0
        start_time = time.time()
        test_duration = 3.0
        
        while time.time() - start_time < test_duration:
            ret, frame = cap.read()
            if ret:
                frame_count += 1
        
        elapsed = time.time() - start_time
        measured_fps = frame_count / elapsed
        
        print(f"  实测FPS: {measured_fps:.1f}")
        
        if measured_fps >= 28:
            print(f"  推荐: ✅ 适合实时分析")
        elif measured_fps >= 20:
            print(f"  推荐: ⚠️  可用但可能有延迟")
        else:
            print(f"  推荐: ❌ 不推荐，性能不足")
        
        cap.release()
    
    print(f"\n{'='*60}\n")

def test_multi_camera_fps(camera_indices=[0, 2, 4, 6]):
    """测试多摄像头同时运行的FPS"""
    print(f"\n{'='*60}")
    print(f"🎥 测试多摄像头性能")
    print(f"摄像头索引: {camera_indices}")
    print(f"{'='*60}\n")
    
    caps = []
    
    # 打开所有摄像头
    print("🔌 打开摄像头...")
    for idx in camera_indices:
        cap = cv2.VideoCapture(idx, cv2.CAP_V4L2)
        
        if cap.isOpened():
            cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M','J','P','G'))
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            cap.set(cv2.CAP_PROP_FPS, 30)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            caps.append((idx, cap))
            print(f"  ✅ 摄像头 #{idx} 已打开")
        else:
            print(f"  ❌ 摄像头 #{idx} 打开失败")
    
    if len(caps) == 0:
        print("\n❌ 没有可用的摄像头")
        return
    
    print(f"\n📊 测试 {len(caps)} 个摄像头同时捕获...")
    print("-" * 40)
    
    # 测试循环读取
    frame_count = 0
    start_time = time.time()
    test_duration = 5.0
    
    while time.time() - start_time < test_duration:
        all_success = True
        for idx, cap in caps:
            ret, frame = cap.read()
            if not ret:
                all_success = False
        
        if all_success:
            frame_count += 1
    
    elapsed = time.time() - start_time
    measured_fps = frame_count / elapsed
    
    print(f"\n结果:")
    print(f"  读取帧数: {frame_count} 帧")
    print(f"  测试时长: {elapsed:.1f} 秒")
    print(f"  整体FPS: {measured_fps:.1f}")
    print(f"  每个摄像头平均: {measured_fps:.1f} FPS")
    
    if measured_fps >= 25:
        print(f"  评估: ✅ 优秀 - 适合实时多摄像头分析")
    elif measured_fps >= 20:
        print(f"  评估: ✅ 良好 - 可用")
    elif measured_fps >= 15:
        print(f"  评估: ⚠️  一般 - 可能有延迟")
    else:
        print(f"  评估: ❌ 较差 - 建议降低分辨率")
    
    # 释放摄像头
    for idx, cap in caps:
        cap.release()
    
    print(f"\n{'='*60}\n")

def main():
    print("\n" + "="*60)
    print("🎬 摄像头性能测试工具")
    print("="*60)
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "--multi":
            # 测试多摄像头
            indices = [0, 2, 4, 6]
            if len(sys.argv) > 2:
                indices = [int(x.strip()) for x in sys.argv[2].split(',')]
            test_multi_camera_fps(indices)
        else:
            # 测试单个摄像头
            camera_idx = int(sys.argv[1])
            test_camera_formats(camera_idx)
            test_resolution_fps(camera_idx)
    else:
        # 默认测试摄像头0
        test_camera_formats(0)
        test_resolution_fps(0)
    
    print("\n💡 建议:")
    print("  - 使用 MJPEG 格式以获得最佳性能和颜色")
    print("  - 720p @ 30 FPS 是性能和质量的最佳平衡")
    print("  - 多摄像头时，确保每个都能稳定达到 25+ FPS")
    print("\n✅ 测试完成！\n")

if __name__ == '__main__':
    main()
