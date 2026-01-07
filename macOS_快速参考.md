# 🍎 macOS M2 移植快速参考卡片

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  OneKey 智能视频分析系统 - macOS M2 快速参考          ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```

## 📦 一键移植流程 (5步)

### 在 Linux 系统上:
```bash
cd /home/nucleus/onekey
./package_for_macos.sh 10
scp ~/onekey_macos_*.tar.gz your-mac:~/
```

### 在 macOS M2 上:
```bash
# 1. 安装依赖
brew install portaudio ffmpeg python@3.11

# 2. 解压
tar -xzvf ~/onekey_macos_*.tar.gz
cd ~/onekey_macos

# 3. 安装
./install_macos.sh

# 4. 配置 (编辑 .env.local)
nano .env.local

# 5. 启动
./start_macos.sh
```

---

## ⚡ 常用命令

### 环境检查
```bash
./check_macos_env.sh                    # 检测系统环境
python3 detect_cameras_macos.py         # 检测相机
python3 detect_cameras_macos.py --test 0 # 测试相机0
```

### 启动系统
```bash
source .venv/bin/activate                          # 激活环境
./start_macos.sh                                   # 标准启动
python3 integrated_system.py --camera 0 --ai       # 完整功能
python3 integrated_system.py --camera 0 --no-face  # 禁用人脸识别
python3 integrated_system.py --obs --ai            # OBS虚拟相机
```

### 管理会话
```bash
./clear_session_macos.sh               # 清理并归档当前会话
ls archives/                           # 查看历史归档
```

### ESP32 按钮
```bash
python3 esp32_server.py                # 启动按钮服务器
ls /dev/cu.usbmodem*                   # 查找串口设备
```

---

## ✅ 移植检查清单

### 系统环境
- [ ] macOS 版本 >= 11.0 (Big Sur)
- [ ] Apple Silicon (M1/M2/M3) 或 Intel
- [ ] 已安装 Homebrew
- [ ] 已安装 Python 3.8+
- [ ] 已安装 FFmpeg
- [ ] 已安装 PortAudio

### 权限设置
- [ ] 相机访问权限 (系统偏好设置 → 安全性与隐私 → 相机)
- [ ] 麦克风访问权限 (系统偏好设置 → 安全性与隐私 → 麦克风)
- [ ] 网络访问权限 (防火墙设置)

### 配置文件
- [ ] .env.local 已创建
- [ ] DASHSCOPE_API_KEY 或 ANTHROPIC_API_KEY 已配置
- [ ] ASR_PROVIDER 已设置 (qwen/fireredasr)

### 功能测试
- [ ] 相机可以打开 (OpenCV)
- [ ] YOLO 模型加载正常
- [ ] AI API 可以调用
- [ ] 音频录制可用 (PyAudio)
- [ ] Web 界面可以访问 (http://localhost:8080)

---

## 🔧 快速问题排查

| 问题 | 快速检查 | 解决方案 |
|-----|---------|---------|
| **相机打不开** | `python3 detect_cameras_macos.py` | 检查系统权限设置 |
| **PyAudio 错误** | `brew list portaudio` | `brew install portaudio` |
| **FFmpeg 找不到** | `which ffmpeg` | `brew install ffmpeg` |
| **API 调用失败** | 检查 .env.local | 确认 API Key 正确 |
| **端口被占用** | `lsof -i :8080` | 更改端口或结束占用进程 |
| **虚拟环境问题** | `which python3` | `source .venv/bin/activate` |

---

## 📁 关键文件路径

```
~/onekey_macos/
├── .env.local                      # ⚙️ 配置文件 (必须手动编辑)
├── install_macos.sh                # 📦 自动安装脚本
├── start_macos.sh                  # 🚀 启动脚本
├── check_macos_env.sh              # 🔍 环境检查工具
├── detect_cameras_macos.py         # 📹 相机检测工具
├── clear_session_macos.sh          # 🗑️ 会话清理工具
│
├── integrated_system.py            # 🎯 主程序
├── key_moments_manager.py          # ⏱️ 关键时刻管理器
├── esp32_server.py                 # 🔘 ESP32 服务器
│
├── integrated_data/                # 💾 数据目录
│   ├── key_moments/                #    - 关键时刻
│   ├── audio/                      #    - 音频录音
│   ├── transcripts/                #    - 语音转写
│   └── logs/                       #    - 日志文件
│
└── archives/                       # 📦 历史归档
    └── session_YYYYMMDD_HHMMSS/
```

---

## 🌐 Web 界面

### 访问地址
```
http://localhost:8080               # 本地访问
http://your-mac-ip:8080             # 局域网访问
```

### API 端点
```
GET  /api/stats                     # 系统状态
GET  /api/moments                   # 关键时刻列表
POST /api/mark_moment               # 标记关键时刻
POST /api/transcribe                # 语音转写
```

---

## 🎮 启动模式对比

| 模式 | 命令 | 用途 |
|-----|------|------|
| **摄像头模式** | `--camera 0` | 使用内置/外接相机 |
| **视频文件模式** | `--video file.mp4` | 分析本地视频 |
| **OBS虚拟相机** | `--obs` | 接入 OBS 直播流 |
| **启用AI** | `--ai` | 开启多模态AI分析 |
| **禁用人脸** | `--no-face` | 仅追踪,不识别人脸 |
| **调试模式** | `--verbose` | 显示详细日志 |

---

## 🔌 硬件连接

### ESP32 按钮
```bash
# 1. 连接 ESP32 到 Mac (USB)
ls /dev/cu.usbmodem*

# 2. 启动服务器
python3 esp32_server.py

# 3. ESP32 配置 WiFi
#    连接到 Mac 同一网络或 Mac 创建的热点
#    服务器地址: Mac的IP:5000
```

### RGB 灯条 (可选)
```bash
# macOS 上不支持 evdev,可以:
# 选项1: 禁用功能
# 选项2: 通过网络按钮触发 (ESP32)
# 选项3: 使用串口直接控制
```

---

## 🆘 紧急救援

### 完全重置
```bash
# 1. 停止所有进程
pkill -f integrated_system.py

# 2. 删除虚拟环境
rm -rf .venv

# 3. 重新安装
./install_macos.sh
```

### 查看日志
```bash
# 系统日志
tail -f integrated_data/logs/analysis.log

# 按钮日志
tail -f button_log.txt

# Python 错误
python3 integrated_system.py --verbose
```

### 测试单个组件
```bash
# OpenCV
python3 -c "import cv2; print(cv2.__version__)"

# YOLO
python3 -c "from ultralytics import YOLO; YOLO('yolo11n.pt')"

# API
python3 -c "
import os
from openai import OpenAI
print(OpenAI(api_key=os.environ['DASHSCOPE_API_KEY']))
"

# 音频
python3 -c "import pyaudio; print(pyaudio.PyAudio().get_device_count())"
```

---

## 📚 文档索引

| 文档 | 用途 |
|-----|------|
| [macOS_M2_移植指南.md](macOS_M2_移植指南.md) | 完整移植指南 ⭐ |
| [README.md](README.md) | 项目概述 |
| [INSTALL_UBUNTU.md](INSTALL_UBUNTU.md) | Ubuntu 安装参考 |
| [📚 重要操作指令汇总.md](📚 重要操作指令汇总.md) | 所有命令参考 |

---

## 🎯 最佳实践

1. **首次运行前**
   - 运行 `./check_macos_env.sh` 检查环境
   - 运行 `python3 detect_cameras_macos.py` 检测相机
   - 确认 `.env.local` 配置正确

2. **日常使用**
   - 使用 `./start_macos.sh` 启动
   - 定期运行 `./clear_session_macos.sh` 归档数据
   - 查看 `integrated_data/logs/` 了解系统状态

3. **性能优化**
   - M2 芯片性能优秀,无需特殊优化
   - 如需更快速度,可禁用人脸识别 `--no-face`
   - 使用 SSD 存储数据以提高 I/O 性能

---

## 💡 提示与技巧

- **快速启动**: 将 `start_macos.sh` 拖到 Dock 以便快速访问
- **后台运行**: 使用 `screen` 或 `tmux` 在后台运行服务
- **自动启动**: 使用 macOS launchd 实现开机自启
- **远程访问**: 配置端口转发以从外网访问 Web 界面
- **数据备份**: 定期备份 `integrated_data/` 和 `archives/`

---

```
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  🎉 享受在 macOS M2 上的高性能体验!                    ┃
┃  完整文档: macOS_M2_移植指南.md                        ┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛
```
