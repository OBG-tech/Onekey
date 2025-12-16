# 🐧 Ubuntu 24.04 LTS 安装指南

## 📋 系统要求

- **操作系统**: Ubuntu 24.04 LTS (Noble Numbat)
- **Python**: 3.10+ (Ubuntu 24.04 自带 Python 3.12)
- **内存**: 最低 4GB RAM，推荐 8GB+
- **存储**: 至少 2GB 可用空间
- **摄像头**: USB 摄像头或内置摄像头（可选）

---

## 🚀 快速安装（推荐）

### 方法 1: 一键安装脚本

```bash
# 1. 下载或克隆项目
cd /path/to/magicrgb

# 2. 运行安装脚本
chmod +x install_ubuntu.sh
./install_ubuntu.sh

# 3. 重新登录以应用摄像头权限
logout
```

安装脚本会自动完成：
- ✅ 安装系统依赖（FFmpeg, PortAudio 等）
- ✅ 配置摄像头权限
- ✅ 创建 Python 虚拟环境
- ✅ 安装所需 Python 包
- ✅ 验证安装

---

## 📦 方法 2: 手动分步安装

### 步骤 1: 安装系统依赖

```bash
# 更新包索引
sudo apt update

# Python 开发环境
sudo apt install -y python3-pip python3-venv python3-dev

# 音频处理依赖
sudo apt install -y portaudio19-dev python3-pyaudio

# OpenCV 依赖
sudo apt install -y libgl1-mesa-glx libglib2.0-0 libsm6 libxext6 libxrender-dev

# 视频处理工具
sudo apt install -y ffmpeg

# 摄像头支持
sudo apt install -y v4l-utils
sudo usermod -a -G video $USER
```

### 步骤 2: 创建虚拟环境（推荐）

```bash
# 创建虚拟环境
python3 -m venv .venv

# 激活虚拟环境
source .venv/bin/activate

# 升级 pip
pip install --upgrade pip
```

### 步骤 3: 安装 Python 包

**选项 A: 基础安装（仅视频分析）**
```bash
pip install opencv-python numpy ultralytics
```

**选项 B: 完整安装 - Claude Haiku 4.5（推荐）**
```bash
pip install opencv-python numpy ultralytics anthropic PyAudio
```

**选项 C: 完整安装 - Qwen 通义千问**
```bash
pip install opencv-python numpy ultralytics openai dashscope PyAudio
```

**选项 D: 完整安装 - 同时支持两种 AI**
```bash
pip install opencv-python numpy ultralytics anthropic openai dashscope PyAudio
```

**可选: 添加人脸识别**
```bash
pip install insightface onnxruntime
```

### 步骤 4: 验证安装

```bash
# 检查核心库
python3 -c "import cv2; print(f'OpenCV: {cv2.__version__}')"
python3 -c "import numpy; print(f'NumPy: {numpy.__version__}')"
python3 -c "from ultralytics import YOLO; print('YOLO: OK')"

# 检查 AI 库
python3 -c "import anthropic; print('Claude: OK')"
python3 -c "import openai; print('OpenAI: OK')"

# 检查音频
python3 -c "import pyaudio; print('PyAudio: OK')"
```

---

## 🎥 配置摄像头

### 检查摄像头

```bash
# 列出所有摄像头
ls -l /dev/video*

# 测试摄像头（需要 ffplay）
ffplay /dev/video0

# 查看摄像头信息
v4l2-ctl --list-devices
```

### 权限问题解决

如果摄像头无法访问：

```bash
# 1. 添加用户到 video 组
sudo usermod -a -G video $USER

# 2. 重新登录系统（必须）
logout

# 3. 验证权限
groups | grep video
```

### 常见摄像头设备

- `/dev/video0` - 第一个摄像头（默认）
- `/dev/video1` - 第二个摄像头
- `/dev/video2` - 虚拟摄像头（OBS 等）

---

## ⚙️ 环境变量配置

### 使用 Claude Haiku 4.5

```bash
# 添加到 ~/.bashrc 或 ~/.zshrc
export LLM_PROVIDER="claude"
export ANTHROPIC_API_KEY="sk-ant-your-key-here"

# 可选: 指定模型
export LLM_MODEL="claude-3-5-haiku-20241022"
export VISION_MODEL="claude-3-5-haiku-20241022"

# 应用配置
source ~/.bashrc
```

### 使用 Qwen 通义千问

```bash
# 添加到 ~/.bashrc 或 ~/.zshrc
export LLM_PROVIDER="qwen"
export DASHSCOPE_API_KEY="sk-your-dashscope-key"

# 可选: 指定模型
export LLM_MODEL="qwen-max"
export VISION_MODEL="qwen-vl-max-latest"

# 应用配置
source ~/.bashrc
```

---

## 🚀 启动系统

### GUI 启动（推荐）

```bash
# 激活虚拟环境
source .venv/bin/activate

# 启动图形界面
python3 LAUNCH_GUI.py
```

### 命令行启动

```bash
# 摄像头模式
python3 integrated_system.py --camera 0

# 视频文件模式
python3 integrated_system.py --video /path/to/video.mp4

# 启用 AI 分析
python3 integrated_system.py --camera 0 --ai
```

---

## 🔧 常见问题排查

### 1. OpenCV 报错 `libGL.so.1` 缺失

```bash
sudo apt install -y libgl1-mesa-glx
```

### 2. PyAudio 安装失败

```bash
# 确保安装了依赖
sudo apt install -y portaudio19-dev python3-dev

# 重新安装
pip install --no-cache-dir PyAudio
```

### 3. 摄像头无法访问

```bash
# 检查权限
ls -l /dev/video0

# 添加到 video 组
sudo usermod -a -G video $USER

# 重新登录系统
logout && login
```

### 4. YOLO 模型下载缓慢

```bash
# 预下载模型
mkdir -p ~/.cache/ultralytics
cd ~/.cache/ultralytics
wget https://github.com/ultralytics/assets/releases/download/v0.0.0/yolov8n.pt
wget https://github.com/ultralytics/assets/releases/download/v0.0.0/yolo11n.pt
```

### 5. FFmpeg 视频合成失败

```bash
# 确保安装了完整的 FFmpeg
sudo apt install -y ffmpeg libavcodec-extra

# 验证
ffmpeg -version
```

### 6. GUI 无法启动（Tkinter）

```bash
# 安装 Tkinter
sudo apt install -y python3-tk

# 验证
python3 -c "import tkinter"
```

---

## 🔒 防火墙配置（可选）

如果需要远程访问 Web 界面：

```bash
# 允许端口 8080
sudo ufw allow 8080/tcp

# 查看状态
sudo ufw status
```

---

## 📊 性能优化

### GPU 加速（NVIDIA）

```bash
# 安装 CUDA Toolkit
sudo apt install -y nvidia-cuda-toolkit

# 安装 GPU 版 PyTorch
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu118
```

### 使用 OpenCV 优化版本

```bash
# 卸载标准版
pip uninstall opencv-python

# 安装优化版（包含 contrib 模块）
pip install opencv-contrib-python
```

---

## 📚 其他资源

- **项目文档**: [README.md](README.md)
- **使用说明**: [使用说明.md](使用说明.md)
- **API 文档**: [启动脚本说明.md](启动脚本说明.md)

---

## 🆘 获取帮助

如遇到问题：

1. 查看日志文件: `integrated_data/logs/`
2. 检查依赖版本: `pip list`
3. 验证系统信息: `uname -a && python3 --version`
4. 查看摄像头状态: `v4l2-ctl --list-devices`

---

**安装完成后，请重新登录系统以应用所有配置更改！**
