# 🎬 OneKey 智能视频分析整合系统

OneKey 是一个面向 Hackathon / 创客活动场景的智能视频分析系统，支持单摄像头、OBS 虚拟摄像头、多摄像头采集，集成人物追踪、人脸识别、实时 ASR、关键时刻管理、AI 分析与网页可视化。

---

## 1) 快速开始

### Ubuntu（推荐）
```bash
chmod +x install_ubuntu.sh
./install_ubuntu.sh
logout
```

重新登录后：
```bash
python3 integrated_system.py --camera auto --camera-usb 05a3:9230
```

### 常用一键脚本
```bash
./start.sh                    # 标准启动（交互选择模式）
./start_live.sh               # 直播模式（后台+直播页）
./start_multicam.sh           # 多摄像头模式（默认 0,2,4,6）
./start_auto_recording.sh     # 自动启动 ASR
./start_with_full_recording.sh # 启动并控制 OBS 全程录制
```

---

## 2) 项目结构（核心）

```text
Onekey/
├── integrated_system.py
├── start_multicam_system.py
├── multi_camera_capture.py
├── multi_camera_recording.py
├── key_moments_manager.py
├── key_moments_viewer.py
├── realtime_asr.py
├── audio_manager.py
├── microphone_recorder.py
├── ai_live_commentary.py
├── camera_utils.py
├── esp32_server.py
├── archive_data.py
├── LAUNCH_GUI.py
├── web_viewer.py
├── obs_auto_record.py
├── start.sh / start_live.sh / start_multicam.sh
├── start_auto_recording.sh / start_with_full_recording.sh / stop_with_full_recording.sh
├── install_ubuntu.sh
├── .env.local.example
├── requirements.txt
├── FireRedASR/
├── MagicLLM/
├── web/
│   ├── integrated.html
│   ├── integrated_v2.html
│   └── 启动中心.html
├── integrated final.html
├── integrated_final_live.html
└── integrated_data/ (运行后自动生成)
```

---

## 3) 核心功能

- 多摄像头支持（ARC 摄像头，推荐索引 `0,2,4,6`）
- 人物追踪（YOLOv11n + ByteTrack）
- 人脸识别（InsightFace，阈值约 0.40）
- 关键时刻双轨检测（用户触发 + AI 多模态触发）
- 实时语音识别（DashScope paraformer / FireRedASR）
- AI 分析（Qwen / Claude）
- 复古 Macintosh 风格 Web 界面
- OBS 虚拟摄像头与 WebSocket 录制控制
- ESP32 硬件按钮触发（TCP 服务）
- 数据归档（按日期组织）

---

## 4) 启动模式

### OBS 模式
```bash
python3 integrated_system.py --obs
```

### 单摄像头模式
```bash
python3 integrated_system.py --camera auto --camera-usb 05a3:9230
```

### 视频文件模式
```bash
python3 integrated_system.py --video file.mp4
```

### 多摄像头模式
```bash
python3 start_multicam_system.py --cameras 0,2,4,6 --fps 30 --resolution 1280x720
```

### 常用附加参数
```bash
--ai        # 启用 AI 分析
--no-face   # 关闭人脸识别
```

---

## 5) AI 与环境变量配置

复制模板并填写：
```bash
cp .env.local.example .env.local
```

关键变量：
- `LLM_PROVIDER=qwen|claude`
- `DASHSCOPE_API_KEY`
- `ANTHROPIC_API_KEY` / `CLAUDE_API_KEY`
- `LLM_MODEL`（如 `qwen-max`）
- `VISION_MODEL`（如 `qwen-vl-max-latest`）
- `VISION_MODEL_FAST`（如 `qwen-vl-plus`）
- `ASR_PROVIDER=qwen|fireredasr`
- `CAMERA_USB_VIDPID=05a3:9230`
- `AUDIO_BACKEND=pulse|alsa`
- `AUDIO_INPUT=default`
- `WEB_STREAM_FPS=1~30`

---

## 6) 摄像头配置（Ubuntu）

ARC 摄像头通常每个物理设备会产生两个节点：偶数索引用于视频采集，奇数索引多为元数据节点。  
建议使用：`0,2,4,6`。

为保证色彩与帧率，使用 MJPEG 并优先设置 FOURCC：
```python
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc('M','J','P','G'))
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
cap.set(cv2.CAP_PROP_FPS, 30)
```

---

## 7) OBS 配置

### Ubuntu 虚拟摄像头
```bash
sudo modprobe v4l2loopback devices=1 video_nr=8 card_label="OBS Virtual Camera" exclusive_caps=1
```

### OBS WebSocket（录制控制）
- 默认端口：`4455`
- 通过 `obs_auto_record.py` / `obs_recording_control.sh` 控制录制状态

---

## 8) 多摄像头建议

推荐配置：
- 摄像头：`0,2,4,6`
- 分辨率：`1280x720`
- 帧率：`30`
- 编码格式：`MJPEG`

启动：
```bash
./start_multicam.sh
```

---

## 9) 硬件集成

### ESP32 按钮
```bash
python3 esp32_server.py
```
- 默认 TCP 端口：`5000`
- 可用于触发关键时刻标记

### RGB 灯条（Linux）
```bash
./rgb.sh
```
- 依赖 Linux 输入设备能力（evdev）

---

## 10) 关键时刻系统

关键时刻来源：
1. 用户触发：空格键 / ESP32 按钮  
2. AI 触发：语义候选 + 帧对齐 + 多模态验证

每个关键时刻可包含：
- 视频片段（`.mp4`）
- 关键帧（`.jpg`）
- 元数据（`.json`，含描述/转写/分析）

查看器：
- 主系统：`http://localhost:8082`
- 关键时刻查看器：`http://localhost:8086`

---

## 11) 数据管理

运行后常见目录：
- `integrated_data/key_moments/`
- `integrated_data/audio/`
- `integrated_data/transcripts/`
- `integrated_data/face_database/`
- `integrated_data/snapshots/`
- `integrated_data/logs/`
- `archives/`

归档：
```bash
python3 archive_data.py
python3 archive_data.py --dry-run
```

---

## 12) 平台说明

### Ubuntu 22.04 / 24.04
- 本分支仅支持 Ubuntu 平台
- 推荐用于完整功能（多摄像头、OBS、硬件联动）

---

## 13) 常见问题

### 摄像头打不开
```bash
ls -la /dev/video*
v4l2-ctl --list-devices
```
确认用户已加入 `video` 组并重新登录。

### OBS 虚拟摄像头不可用
```bash
lsmod | grep v4l2loopback
```
确认内核模块已加载并在 OBS 内启动虚拟摄像头。

### 端口占用
检查 8082 / 8086 / 5000 / 4455 是否被占用，调整启动参数或结束冲突进程。

---

## 14) 性能建议

- 多摄像头优先 `1280x720 @ 30fps`
- Web 低延迟可下调 `WEB_STREAM_FPS`
- 资源紧张时可关闭人脸识别（`--no-face`）
- 长时间运行可使用：
```bash
./auto_restart.sh 2
```

---

## 15) 版本记录

### v2.3
- 整合多模式视频输入、关键时刻管理、AI 分析与 Web 可视化
- 增强多摄像头与 OBS 联动能力
- 完善自动录音录像与数据归档流程

