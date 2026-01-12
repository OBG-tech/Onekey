# 🐧 Ubuntu 22.04 快速启动指南

## 📷 摄像头自动检测

系统已适配 Ubuntu 22.04，支持自动检测您的 4 个 ARC International 摄像头。

### 快速启动

```bash
# 1. 自动选择任意可用摄像头
python3 integrated_system.py --camera auto

# 2. 优先选择 ARC 摄像头 (VID:PID = 05a3:9230)
python3 integrated_system.py --camera auto --camera-usb 05a3:9230

# 3. 使用环境变量
export CAMERA_USB_VIDPID=05a3:9230
python3 integrated_system.py --camera auto

# 4. 手动指定索引（如果知道）
python3 integrated_system.py --camera 0
```

### 查看可用摄像头

```bash
# 列出所有视频设备
ls -la /dev/video*

# 查看 USB 摄像头
lsusb | grep Camera

# 使用 v4l2 工具查看详细信息
v4l2-ctl --list-devices
```

## 🎤 音频配置

Ubuntu 默认使用 PulseAudio，系统已自动适配。

```bash
# 查看可用音频输入设备
pactl list short sources

# 设置特定音频设备（可选）
export AUDIO_BACKEND=pulse
export AUDIO_INPUT=alsa_input.usb-0000_USB_Audio-00.analog-stereo
```

### ALSA 模式（可选）

```bash
# 列出 ALSA 设备
arecord -l

# 使用 ALSA
export AUDIO_BACKEND=alsa
export AUDIO_INPUT=hw:0
python3 integrated_system.py --camera auto
```

## 📹 OBS 虚拟相机设置

```bash
# 1. 安装 v4l2loopback（如未安装）
sudo apt install v4l2loopback-dkms

# 2. 加载内核模块
sudo modprobe v4l2loopback devices=1 video_nr=8 card_label="OBS Virtual Camera" exclusive_caps=1

# 3. 验证模块已加载
lsmod | grep v4l2loopback
ls -la /dev/video8

# 4. 启动 OBS
obs

# 5. 在 OBS 中启动虚拟相机
# 工具 → 虚拟相机 → 启动

# 6. 启动系统
python3 integrated_system.py --obs
```

### 开机自动加载 v4l2loopback

```bash
# 创建配置文件
echo "v4l2loopback" | sudo tee /etc/modules-load.d/v4l2loopback.conf

# 设置模块参数
echo "options v4l2loopback devices=1 video_nr=8 card_label=\"OBS Virtual Camera\" exclusive_caps=1" | \
  sudo tee /etc/modprobe.d/v4l2loopback.conf

# 重启生效
sudo reboot
```

## 🚀 完整启动流程

### 方式一：使用启动脚本

```bash
cd ~/onekey
./start.sh
```

选择选项：
- `1` - OBS虚拟摄像头模式
- `2` - 摄像头模式（自动检测）
- `3` - 视频文件模式

### 方式二：使用图形界面

```bash
python3 LAUNCH_GUI.py
```

### 方式三：命令行直接启动

```bash
# 摄像头模式（自动检测 ARC 摄像头）
export CAMERA_USB_VIDPID=05a3:9230
python3 integrated_system.py --camera auto

# OBS 模式
python3 integrated_system.py --obs

# 视频文件模式
python3 integrated_system.py --video /path/to/video.mp4
```

## 🔧 常见问题

### Q: 摄像头权限问题

```bash
# 将用户添加到 video 组
sudo usermod -a -G video $USER

# 重新登录生效
logout
```

### Q: OBS 虚拟相机不工作

```bash
# 检查模块状态
lsmod | grep v4l2loopback

# 重新加载模块
sudo modprobe -r v4l2loopback
sudo modprobe v4l2loopback devices=1 video_nr=8 card_label="OBS Virtual Camera" exclusive_caps=1

# 检查设备
ls -la /dev/video8
```

### Q: 音频录制失败

```bash
# 检查 PulseAudio
pactl info

# 测试音频录制
arecord -f cd -d 5 test.wav
aplay test.wav

# 如果 PulseAudio 有问题，尝试 ALSA
export AUDIO_BACKEND=alsa
export AUDIO_INPUT=hw:0
```

### Q: 找不到 ARC 摄像头

```bash
# 检查 USB 连接
lsusb | grep "05a3:9230"

# 应该看到 4 个设备：
# Bus 001 Device 005: ID 05a3:9230 ARC International Camera
# Bus 001 Device 006: ID 05a3:9230 ARC International Camera
# Bus 007 Device 004: ID 05a3:9230 ARC International Camera
# Bus 007 Device 003: ID 05a3:9230 ARC International Camera

# 检查对应的视频设备
for d in /dev/video*; do
  udevadm info --query=property --name=$d | grep -E "ID_VENDOR_ID|ID_MODEL_ID"
done
```

## 📊 性能优化

### 降低 CPU 使用率

```bash
# 降低 Web 视频流帧率
export WEB_STREAM_FPS=8
python3 integrated_system.py --camera auto

# 禁用本地窗口
python3 integrated_system.py --camera auto --no-window
```

### 多摄像头同时使用

```bash
# 使用 start_multicam_system.py
python3 start_multicam_system.py --cameras 0,1,2,3
```

## 🌐 环境变量完整列表

```bash
# 摄像头
export CAMERA_USB_VIDPID=05a3:9230          # USB VID:PID 过滤

# 音频
export AUDIO_BACKEND=pulse                   # pulse | alsa
export AUDIO_INPUT=default                   # 设备名

# AI 功能
export LLM_PROVIDER=qwen                     # qwen | claude
export DASHSCOPE_API_KEY=sk-xxx              # Qwen API Key
export ANTHROPIC_API_KEY=sk-ant-xxx          # Claude API Key

# ASR 语音识别
export ASR_PROVIDER=qwen                     # qwen | fireredasr

# Web 界面
export WEB_STREAM_FPS=12                     # 视频流帧率 (1-30)

# 关键时刻
export KEY_MOMENT_CONTEXT_WINDOW_MINUTES=20  # 上下文窗口（分钟）
export AI_MOMENT_MIN_IMPORTANCE=0.3          # 最低重要性阈值
```

## 📝 完整启动示例

```bash
#!/bin/bash
# my_start.sh - 个性化启动脚本

# 进入项目目录
cd ~/onekey

# 激活虚拟环境
source .venv/bin/activate

# 设置环境变量
export CAMERA_USB_VIDPID=05a3:9230
export AUDIO_BACKEND=pulse
export AUDIO_INPUT=default
export DASHSCOPE_API_KEY=sk-your-key-here
export WEB_STREAM_FPS=12

# 启动系统
python3 integrated_system.py \
  --camera auto \
  --ai \
  --port 8080 \
  --no-window

# 或使用 OBS 模式
# python3 integrated_system.py --obs --ai
```

## 🎯 下一步

1. 测试摄像头自动检测：`python3 integrated_system.py --camera auto`
2. 配置 AI 功能：设置 `DASHSCOPE_API_KEY` 环境变量
3. 设置 OBS 虚拟相机：按上述步骤配置 v4l2loopback
4. 浏览 Web 界面：`http://localhost:8080/integrated%20final.html`

**享受智能视频分析！** 🚀
