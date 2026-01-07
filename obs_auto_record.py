#!/usr/bin/env python3
"""
OBS自动录制控制脚本
通过obs-websocket控制OBS自动开始/停止录制
"""

import sys
import time
import argparse

try:
    from obswebsocket import obsws, requests as obs_requests
    OBSWS_AVAILABLE = True
except ImportError:
    OBSWS_AVAILABLE = False
    print("❌ 未安装 obs-websocket-py")
    print("安装命令: pip install obs-websocket-py")
    sys.exit(1)


def connect_obs(host='localhost', port=4455, password=''):
    """连接到OBS WebSocket"""
    try:
        print(f"🔌 连接到 OBS WebSocket ({host}:{port})...")
        client = obsws(host=host, port=port, password=password)
        client.connect()
        print("✅ 已连接到 OBS")
        return client
    except Exception as e:
        print(f"❌ 连接失败: {e}")
        print("\n请检查：")
        print("  1. OBS是否正在运行")
        print("  2. WebSocket服务器是否已启用")
        print("     (工具 → obs-websocket设置 → 启用WebSocket服务器)")
        print(f"  3. WebSocket端口是否为 {port}")
        print(f"  4. 密码是否正确")
        return None


def start_recording(client, wait_seconds=2):
    """启动OBS录制"""
    try:
        # 检查当前状态
        status = client.call(obs_requests.GetRecordStatus())
        if status.datain.get('outputActive'):
            print("⏺️  OBS已在录制中")
            return True
        
        # 启动录制
        print("🔴 启动OBS录制...")
        client.call(obs_requests.StartRecord())
        
        # 等待录制启动
        time.sleep(wait_seconds)
        
        # 验证录制状态
        status = client.call(obs_requests.GetRecordStatus())
        if status.datain.get('outputActive'):
            print("✅ OBS录制已启动")
            duration = status.datain.get('outputDuration', 0)
            print(f"💾 录制时长: {duration / 1000:.1f}秒")
            return True
        else:
            print("❌ 录制启动失败")
            return False
            
    except Exception as e:
        print(f"❌ 启动录制失败: {e}")
        return False


def stop_recording(client, wait_seconds=2):
    """停止OBS录制"""
    try:
        # 检查当前状态
        status = client.call(obs_requests.GetRecordStatus())
        if not status.datain.get('outputActive'):
            print("⏸️  OBS当前未在录制")
            return True
        
        # 停止录制
        print("⏹️  停止OBS录制...")
        duration = status.datain.get('outputDuration', 0) / 1000
        client.call(obs_requests.StopRecord())
        
        # 等待录制停止
        time.sleep(wait_seconds)
        
        print(f"✅ OBS录制已停止 (录制时长: {duration:.1f}秒)")
        return True
            
    except Exception as e:
        print(f"❌ 停止录制失败: {e}")
        return False


def get_status(client):
    """获取录制状态"""
    try:
        status = client.call(obs_requests.GetRecordStatus())
        
        print("📊 OBS录制状态:")
        is_active = status.datain.get('outputActive', False)
        print(f"  • 录制中: {'是' if is_active else '否'}")
        
        if is_active:
            duration = status.datain.get('outputDuration', 0) / 1000
            hours = int(duration // 3600)
            minutes = int((duration % 3600) // 60)
            seconds = int(duration % 60)
            print(f"  • 录制时长: {hours:02d}:{minutes:02d}:{seconds:02d}")
            output_bytes = status.datain.get('outputBytes', 0)
            print(f"  • 录制字节: {output_bytes:,} bytes")
        
        return is_active
        
    except Exception as e:
        print(f"❌ 获取状态失败: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='OBS自动录制控制')
    parser.add_argument('action', choices=['start', 'stop', 'status'],
                       help='操作: start=开始录制, stop=停止录制, status=查看状态')
    parser.add_argument('--host', default='localhost', help='OBS主机地址')
    parser.add_argument('--port', type=int, default=4455, help='WebSocket端口')
    parser.add_argument('--password', default='', help='WebSocket密码')
    parser.add_argument('--wait', type=int, default=2, help='等待时间(秒)')
    
    args = parser.parse_args()
    
    # 连接OBS
    client = connect_obs(args.host, args.port, args.password)
    if not client:
        sys.exit(1)
    
    # 执行操作
    success = False
    try:
        if args.action == 'start':
            success = start_recording(client, args.wait)
        elif args.action == 'stop':
            success = stop_recording(client, args.wait)
        elif args.action == 'status':
            success = get_status(client)
    finally:
        client.disconnect()
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
