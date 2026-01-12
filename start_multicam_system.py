#!/usr/bin/env python3
"""
多摄像头集成系统启动器
使用multi_camera_capture模块，配合integrated_system.py的所有功能
"""

import sys
import os

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 导入多摄像头模块
from multi_camera_capture import MultiCameraCapture

# 替换cv2.VideoCapture - 在导入integrated_system之前
original_VideoCapture = __import__('cv2').VideoCapture

def patched_VideoCapture(index_or_file, *args, **kwargs):
    """
    补丁版本的VideoCapture
    如果检测到多摄像头模式，返回MultiCameraCapture
    """
    # 检查是否为多摄像头模式
    if hasattr(sys, '_multicam_mode') and sys._multicam_mode:
        return sys._multicam_instance
    else:
        return original_VideoCapture(index_or_file, *args, **kwargs)

# 应用补丁
import cv2
cv2.VideoCapture = patched_VideoCapture

print("🎥 多摄像头模式启动器")
print("=" * 60)

# 解析参数
import argparse
parser = argparse.ArgumentParser(description='多摄像头集成系统')
parser.add_argument('--cameras', type=str, default='',
                   help='摄像头索引，逗号分隔；留空则自动选择可用摄像头 (例如: 0,2,4,6)')
parser.add_argument('--camera-name', type=str, default='LRCP',
                   help='自动选择时按 V4L2 名称子串匹配 (默认: LRCP)')
parser.add_argument('--camera-vidpid', type=str, default='05a3:9230',
                   help='自动选择时按 USB vid:pid 过滤 (默认: 05a3:9230)')
parser.add_argument('--fps', type=int, default=30,
                   help='目标帧率 (默认: 30)')
parser.add_argument('--resolution', type=str, default='1280x720',
                   help='每个摄像头的分辨率 (默认: 1280x720)')
parser.add_argument('--port', type=int, default=8082,
                   help='Web服务器端口 (默认: 8082)')
parser.add_argument('--test', action='store_true',
                   help='仅测试摄像头拼接，不启动完整系统')
parser.add_argument('--record', action='store_true',
                   help='启用全程视频录制')
parser.add_argument('--record-dir', type=str, default='recordings',
                   help='录制文件保存目录 (默认: recordings)')

args, remaining_args = parser.parse_known_args()

# 解析摄像头索引（允许留空=自动选择）
camera_indices = [int(x.strip()) for x in (args.cameras or '').split(',') if x.strip()]

if not camera_indices:
    # 自动选择：优先选择“能被 OpenCV 打开的 capture 节点”，避免选到 1/3/5/7 这类子节点
    try:
        import json, subprocess
        out = subprocess.check_output(
            [sys.executable, 'camera_autoselect.py', '--name', args.camera_name, '--vidpid', args.camera_vidpid, '--limit', '4'],
            text=True,
        )
        data = json.loads(out)
        camera_indices = [int(d['index']) for d in data.get('devices', [])]
    except Exception:
        camera_indices = []

if not camera_indices:
    print("❌ 错误：未找到可用摄像头")
    print(f"   自动选择条件: name~{args.camera_name!r}, vidpid={args.camera_vidpid!r}")
    print("   提示：可用节点通常类似 0,2,4,6（避免 1,3,5,7）")
    sys.exit(1)

# 解析分辨率
width, height = [int(x) for x in args.resolution.split('x')]

print(f"\n📹 配置:")
print(f"  摄像头: {camera_indices}")
print(f"  每个摄像头分辨率: {width}x{height}")
print(f"  拼接后分辨率: {width*2}x{height*2}")
print(f"  目标FPS: {args.fps}")
print(f"  Web端口: {args.port}")
if args.record:
    print(f"  🔴 全程录制: 启用 → {args.record_dir}/")
print()

# 创建多摄像头实例
multicam = MultiCameraCapture(
    camera_indices=camera_indices,
    target_fps=args.fps,
    resolution_per_camera=(width, height),
    enable_recording=args.record,
    recording_dir=args.record_dir
)

# 打开摄像头
if not multicam.open_cameras():
    print("❌ 无法打开摄像头，退出")
    sys.exit(1)

# 启动捕获线程
multicam.start_capture_threads()

# 如果是测试模式，只预览拼接画面
if args.test:
    print("🧪 测试模式：预览拼接画面 (按 'q' 退出)\n")
    
    import cv2
    import time
    
    frame_count = 0
    start_time = time.time()
    
    try:
        while True:
            ret, frame = multicam.read()
            
            if not ret:
                print("⚠️  读取帧失败")
                break
            
            # 显示FPS
            frame_count += 1
            elapsed = time.time() - start_time
            if elapsed > 0:
                fps = frame_count / elapsed
                cv2.putText(frame, f"FPS: {fps:.1f}", (30, 60), 
                           cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 255, 0), 3)
            
            # 缩小显示
            display_frame = cv2.resize(frame, (1920, 1080))
            cv2.imshow('Multi-Camera Test', display_frame)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    
    except KeyboardInterrupt:
        print("\n⚠️  用户中断")
    
    finally:
        multicam.release()
        cv2.destroyAllWindows()
        
        avg_fps = frame_count / elapsed if elapsed > 0 else 0
        print(f"\n📊 平均 FPS: {avg_fps:.1f}")
        print("✅ 测试完成")
        
        sys.exit(0)

# 正常模式：启动完整系统
print("🚀 启动完整集成系统...\n")

# 设置多摄像头模式标志
sys._multicam_mode = True
sys._multicam_instance = multicam

# 修改sys.argv以传递参数给integrated_system.py
sys.argv = ['integrated_system.py', '--camera', '0']  # 虚拟索引，会被multicam替代

# 添加端口参数
if args.port:
    sys.argv.extend(['--port', str(args.port)])

# 添加剩余参数
sys.argv.extend(remaining_args)

# 现在导入并运行integrated_system
print("📦 加载integrated_system模块...\n")

try:
    # 导入主系统
    import integrated_system
    
    # 运行主函数
    integrated_system.main()
    
except KeyboardInterrupt:
    print("\n⚠️  用户中断")
except Exception as e:
    print(f"\n❌ 错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    # 清理
    if hasattr(sys, '_multicam_instance'):
        sys._multicam_instance.release()
    
    print("\n✅ 系统已关闭")
