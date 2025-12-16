#!/bin/bash

# 脚本功能:
# 监听所有输入设备的按键"1"（KEY_1, code 2）
# 按下时向 /dev/ttyACM0 发送 "123456789"
# 释放1秒后发送 "54321"

# 配置变量
SERIAL_PORT="/dev/ttyACM0"
BAUD_RATE="9600"
PRESSED_MSG="123456789"
UNPRESSED_MSG="54321"

# 检查串口是否存在
if [ ! -e "$SERIAL_PORT" ]; then
    echo "错误: 串口设备 $SERIAL_PORT 不存在"
    exit 1
fi

# 配置串口
stty -F $SERIAL_PORT $BAUD_RATE cs8 -cstopb -parenb

echo "=========================================="
echo "通用按键'1'监听已启动"
echo "监听按键: KEY_1 (键盘上的数字'1')"
echo "串口: $SERIAL_PORT @ $BAUD_RATE"
echo "=========================================="

# 清理函数
cleanup() {
    echo -e "\n正在清理..."
    rm -f "$EVENT_FIFO"
    jobs -p | xargs -r kill 2>/dev/null
    exit 0
}

trap cleanup SIGINT SIGTERM EXIT

# 发送初始状态
echo -n "$UNPRESSED_MSG" > $SERIAL_PORT

# 创建临时文件用于进程间通信
EVENT_FIFO="/tmp/keyboard_event_$$"
mkfifo "$EVENT_FIFO"

# 使用 Python 监听所有设备的 KEY_1 事件
python3 -u > "$EVENT_FIFO" <<'PYTHON_SCRIPT' &
import sys
import time
import select

try:
    from evdev import InputDevice, ecodes, list_devices
except ImportError:
    print("ERROR:evdev库未安装", flush=True)
    print("ERROR:请运行: pip3 install evdev", flush=True)
    sys.exit(1)

KEY_1_CODE = 2  # KEY_1 的扫描码
devices = []

# 扫描所有输入设备
print(f"INFO:正在扫描输入设备...", flush=True)

for device_path in list_devices():
    try:
        dev = InputDevice(device_path)
        caps = dev.capabilities()
        
        # 检查是否支持键盘事件和 KEY_1
        if ecodes.EV_KEY in caps and KEY_1_CODE in caps[ecodes.EV_KEY]:
            devices.append(dev)
            print(f"INFO:监听设备 {device_path}: {dev.name}", flush=True)
    except Exception as e:
        continue

if not devices:
    print("ERROR:未找到支持KEY_1的设备", flush=True)
    print("ERROR:请使用sudo运行或添加用户到input组", flush=True)
    sys.exit(1)

print(f"INFO:成功监听 {len(devices)} 个设备", flush=True)

# 使用 select 监听所有设备
fd_to_device = {dev.fd: dev for dev in devices}

while True:
    try:
        r, w, x = select.select(fd_to_device, [], [])
        for fd in r:
            dev = fd_to_device[fd]
            for event in dev.read():
                if event.type == ecodes.EV_KEY and event.code == KEY_1_CODE:
                    if event.value == 1:  # 按下
                        print("PRESSED", flush=True)
                    elif event.value == 0:  # 释放
                        print("RELEASED", flush=True)
    except Exception as e:
        print(f"ERROR:{e}", flush=True)
        continue

PYTHON_SCRIPT

PYTHON_PID=$!

# 主循环: 读取事件并控制串口
echo ""
echo "监听已启动，按 Ctrl+C 停止"
echo "----------------------------------------"

while read event_type; do
    if [[ "$event_type" == INFO:* ]]; then
        echo "$event_type"
        
    elif [[ "$event_type" == ERROR:* ]]; then
        echo "$event_type" >&2
        
    elif [ "$event_type" == "PRESSED" ]; then
        echo "[$(date '+%H:%M:%S')] 按键'1'按下 -> 发送: $PRESSED_MSG (持续100ms)"
        echo -n "$PRESSED_MSG" > $SERIAL_PORT
        # 持续100ms
        sleep 0.1
        echo "[$(date '+%H:%M:%S')] 100ms后 -> 发送: $UNPRESSED_MSG"
        echo -n "$UNPRESSED_MSG" > $SERIAL_PORT
        
    elif [ "$event_type" == "RELEASED" ]; then
        # 按键释放事件（不需要处理，因为已在按下时发送过UNPRESSED_MSG）
        echo "[$(date '+%H:%M:%S')] 按键'1'释放"
    fi
done < "$EVENT_FIFO"

