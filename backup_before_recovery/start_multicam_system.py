#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
澶氭憚鍍忓ご闆嗘垚绯荤粺鍚�鍔ㄥ櫒
浣跨敤multi_camera_capture妯″潡锛岄厤鍚坕ntegrated_system.py鐨勬墍鏈夊姛鑳�
"""

import sys
import os

# 娣诲姞褰撳墠鐩�褰曞埌璺�寰�
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 瀵煎叆澶氭憚鍍忓ご妯″潡
from multi_camera_capture import MultiCameraCapture

# 鏇挎崲cv2.VideoCapture - 鍦ㄥ�煎叆integrated_system涔嬪墠
original_VideoCapture = __import__('cv2').VideoCapture

def patched_VideoCapture(index_or_file, *args, **kwargs):
    """
    琛ヤ竵鐗堟湰鐨刅ideoCapture
    濡傛灉妫€娴嬪埌澶氭憚鍍忓ご妯″紡锛岃繑鍥濵ultiCameraCapture
    """
    # 妫€鏌ユ槸鍚︿负澶氭憚鍍忓ご妯″紡
    if hasattr(sys, '_multicam_mode') and sys._multicam_mode:
        return sys._multicam_instance
    else:
        return original_VideoCapture(index_or_file, *args, **kwargs)

# 搴旂敤琛ヤ竵
import cv2
cv2.VideoCapture = patched_VideoCapture

print("馃帴 澶氭憚鍍忓ご妯″紡鍚�鍔ㄥ櫒")
print("=" * 60)

# 瑙ｆ瀽鍙傛暟
import argparse
parser = argparse.ArgumentParser(description='澶氭憚鍍忓ご闆嗘垚绯荤粺')
parser.add_argument('--cameras', type=str, default='0,2,4,6',
                   help='鎽勫儚澶寸储寮曪紝閫楀彿鍒嗛殧 (榛樿��: 0,2,4,6)')
parser.add_argument('--fps', type=int, default=60,
                   help='鐩�鏍囧抚鐜� (榛樿��: 60)')
parser.add_argument('--resolution', type=str, default='1920x1080',
                   help='姣忎釜鎽勫儚澶寸殑鍒嗚鲸鐜� (榛樿��: 1920x1080)')
parser.add_argument('--port', type=int, default=8083,
                   help='Web鏈嶅姟鍣ㄧ��鍙� (榛樿��: 8083)')
parser.add_argument('--test', action='store_true',
                   help='浠呮祴璇曟憚鍍忓ご鎷兼帴锛屼笉鍚�鍔ㄥ畬鏁寸郴缁�')
parser.add_argument('--record', action='store_true',
                   help='鍚�鐢ㄥ叏绋嬭�嗛�戝綍鍒�')
parser.add_argument('--record-dir', type=str, default='recordings',
                   help='褰曞埗鏂囦欢淇濆瓨鐩�褰� (榛樿��: recordings)')

args, remaining_args = parser.parse_known_args()

# 瑙ｆ瀽鎽勫儚澶寸储寮曪紙杩囨护绌哄瓧绗︿覆锛�
camera_indices = [int(x.strip()) for x in args.cameras.split(',') if x.strip()]

if not camera_indices:
    print("鉂� 閿欒��锛氭湭鎸囧畾鏈夋晥鐨勬憚鍍忓ご绱㈠紩")
    print("   璇疯緭鍏ュ��: 0,2,4,6 鎴� 0,1,2,3")
    sys.exit(1)

# 瑙ｆ瀽鍒嗚鲸鐜�
width, height = [int(x) for x in args.resolution.split('x')]

print(f"\n馃摴 閰嶇疆:")
print(f"  鎽勫儚澶�: {camera_indices}")
print(f"  姣忎釜鎽勫儚澶村垎杈ㄧ巼: {width}x{height}")
print(f"  鎷兼帴鍚庡垎杈ㄧ巼: {width*2}x{height*2}")
print(f"  鐩�鏍嘑PS: {args.fps}")
print(f"  Web绔�鍙�: {args.port}")
if args.record:
    print(f"  馃敶 鍏ㄧ▼褰曞埗: 鍚�鐢� 鈫� {args.record_dir}/")
print()

# 鍒涘缓澶氭憚鍍忓ご瀹炰緥
multicam = MultiCameraCapture(
    camera_indices=camera_indices,
    target_fps=args.fps,
    resolution_per_camera=(width, height),
    enable_recording=args.record,
    recording_dir=args.record_dir
)

# 鎵撳紑鎽勫儚澶�
if not multicam.open_cameras():
    print("鉂� 鏃犳硶鎵撳紑鎽勫儚澶达紝閫€鍑�")
    sys.exit(1)

# 鍚�鍔ㄦ崟鑾风嚎绋�
multicam.start_capture_threads()

# 濡傛灉鏄�娴嬭瘯妯″紡锛屽彧棰勮�堟嫾鎺ョ敾闈�
if args.test:
    print("馃И 娴嬭瘯妯″紡锛氶�勮�堟嫾鎺ョ敾闈� (鎸� 'q' 閫€鍑�)\n")
    
    import cv2
    import time
    
    frame_count = 0
    start_time = time.time()
    
    try:
        while True:
            ret, frame = multicam.read()
            
            if not ret:
                print("鈿狅笍  璇诲彇甯уけ璐�")
                break
            
            # 鏄剧ずFPS
            frame_count += 1
            elapsed = time.time() - start_time
            if elapsed > 0:
                fps = frame_count / elapsed
                cv2.putText(frame, f"FPS: {fps:.1f}", (30, 60), 
                           cv2.FONT_HERSHEY_SIMPLEX, 2, (0, 255, 0), 3)
            
            # 缂╁皬鏄剧ず
            display_frame = cv2.resize(frame, (1920, 1080))
            cv2.imshow('Multi-Camera Test', display_frame)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
    
    except KeyboardInterrupt:
        print("\n鈿狅笍  鐢ㄦ埛涓�鏂�")
    
    finally:
        multicam.release()
        cv2.destroyAllWindows()
        
        avg_fps = frame_count / elapsed if elapsed > 0 else 0
        print(f"\n馃搳 骞冲潎 FPS: {avg_fps:.1f}")
        print("鉁� 娴嬭瘯瀹屾垚")
        
        sys.exit(0)

# 姝ｅ父妯″紡锛氬惎鍔ㄥ畬鏁寸郴缁�
print("馃殌 鍚�鍔ㄥ畬鏁撮泦鎴愮郴缁�...\n")

# 璁剧疆澶氭憚鍍忓ご妯″紡鏍囧織
sys._multicam_mode = True
sys._multicam_instance = multicam

# 淇�鏀箂ys.argv浠ヤ紶閫掑弬鏁扮粰integrated_system.py
sys.argv = ['integrated_system.py', '--camera', '0']  # 铏氭嫙绱㈠紩锛屼細琚玬ulticam鏇夸唬

# 娣诲姞绔�鍙ｅ弬鏁�
if args.port:
    sys.argv.extend(['--port', str(args.port)])

# 娣诲姞鍓╀綑鍙傛暟
sys.argv.extend(remaining_args)

# 鐜板湪瀵煎叆骞惰繍琛宨ntegrated_system
print("馃摝 鍔犺浇integrated_system妯″潡...\n")

try:
    # 瀵煎叆涓荤郴缁�
    import integrated_system
    
    # 杩愯�屼富鍑芥暟
    integrated_system.main()
    
except KeyboardInterrupt:
    print("\n⚠️  用户中断 (请等待资源释放...)")
except Exception as e:
    print(f"\n❌ 错误: {e}")
    import traceback
    traceback.print_exc()
finally:
    # 临时屏蔽 KeyboardInterrupt，确保 release 过程能完整执行
    import signal
    try:
        original_sigint = signal.getsignal(signal.SIGINT)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
    except Exception:
        pass

    # 清理
    if hasattr(sys, '_multicam_instance'):
        try:
            sys._multicam_instance.release()
        except Exception as e:
            print(f"释放资源时出错: {e}")
            
    try:
         signal.signal(signal.SIGINT, original_sigint)
    except Exception:
        pass
    
    print("\n✅ 系统已关闭")
