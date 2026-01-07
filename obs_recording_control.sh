#!/bin/bash
# OBS自动录制辅助脚本
# 使用obs-websocket-py控制OBS录制

PORT=${1:-4455}  # OBS WebSocket默认端口

echo "🎬 OBS录制控制脚本"
echo ""

# 检查是否安装了obs-websocket-py
if ! python3 -c "import obsws_python" 2>/dev/null; then
    echo "❌ 未安装 obs-websocket-py"
    echo ""
    echo "安装方法："
    echo "  pip install obs-websocket-py"
    echo ""
    exit 1
fi

# Python脚本控制OBS录制
python3 - <<EOF
import sys
try:
    from obsws_python import ReqClient
    
    print("🔌 连接到 OBS WebSocket...")
    try:
        # 尝试连接（无密码）
        client = ReqClient(host='localhost', port=${PORT}, password='')
    except:
        try:
            # 如果失败，尝试默认密码
            client = ReqClient(host='localhost', port=${PORT}, password='secret')
        except Exception as e:
            print(f"❌ 连接失败: {e}")
            print("")
            print("请检查：")
            print("  1. OBS是否正在运行")
            print("  2. WebSocket服务器是否已启用")
            print("  3. WebSocket端口是否正确（默认4455）")
            print("")
            print("在OBS中启用WebSocket：")
            print("  工具 → obs-websocket设置 → 启用WebSocket服务器")
            sys.exit(1)
    
    print("✅ 已连接到 OBS")
    
    # 检查当前录制状态
    try:
        status = client.get_record_status()
        is_recording = status.output_active
        
        if is_recording:
            print("⏺️  OBS当前正在录制")
            print("")
            response = input("是否停止录制？[y/N]: ")
            if response.lower() == 'y':
                client.stop_record()
                print("⏹️  已停止录制")
            else:
                print("▶️  继续录制")
        else:
            print("⏸️  OBS当前未在录制")
            print("")
            response = input("是否开始录制？[Y/n]: ")
            if response.lower() != 'n':
                client.start_record()
                print("🔴 录制已开始！")
                print("")
                print("💾 录制文件保存位置请在OBS设置中查看：")
                print("   文件 → 设置 → 输出 → 录像")
            else:
                print("✋ 取消操作")
    
    except Exception as e:
        print(f"❌ 操作失败: {e}")
        sys.exit(1)
    
except ImportError:
    print("❌ 无法导入 obsws_python")
    print("请运行: pip install obs-websocket-py")
    sys.exit(1)
except Exception as e:
    print(f"❌ 发生错误: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
EOF

echo ""
echo "✅ 操作完成"
