# 🎬 智能视频分析整合系统

> **一键启动，智能分析，实时追踪**  
> 整合 multi_person_tracker + ONE_KEY + OBS支持

![Version](https://img.shields.io/badge/version-2.3-blue)
![Python](https://img.shields.io/badge/python-3.8+-green)
![License](https://img.shields.io/badge/license-MIT-orange)

---

## 外围设备连接
### 1、设备热点开启
在主目录下运行
```bash
./build_virtual_network.sh #热点开启脚本
```

如果输出如下所示：
```bash
RTNETLINK answers: Operation not supported
nohup: 忽略输入并把输出追加到 'nohup.out'
```

则需要重新运行热点开启脚本

如果输出如下所示：
```bash
nohup: 忽略输入并把输出追加到 'nohup.out'
```
则说明热点开启成功

如果想要在ubuntu后台开启服务且不想要绑定终端，可以运行：
```bash
tmux new -t nohup #新建后台进程，电脑重启时运行
```
或：
```bash
tmux a -t nohup #打开后台进程，新建以后运行
```
退出tmux服务时可使用以下操作退出：
```bash
Ctrl+b d
```
### 2、开启按钮数据接收服务
可使用以下命令开启按钮数据接收服务
```bash
cd ~/onekey
python3 esp32_server.py
```

当输出：
```bash
服务器启动，监听端口 5000 ...
等待 ESP32 连接（可以先启动服务器，ESP32 连接 WiFi 后会自动连接）...
```
时说明服务已正常开启，可以在终端实时查看哪些按钮已连接。
log文件会保存在`~/onekey/button_log.txt`中

### 3、开启摄像头灯条刷新
运行以下命令：
```bash
cd ~/MagicLLM
./rgb.sh
```
当输出：
```bash
==========================================
通用按键'1'监听已启动
监听按键: KEY_1 (键盘上的数字'1')
串口: /dev/ttyACM0 @ 9600
==========================================

监听已启动，按 Ctrl+C 停止
----------------------------------------
INFO:正在扫描输入设备...
INFO:监听设备 /dev/input/event18: Knight22 USB DEVICE
INFO:监听设备 /dev/input/event14: input-remapper keyboard
INFO:监听设备 /dev/input/event3: AT Translated Set 2 keyboard
INFO:成功监听 3 个设备
```
时，说明服务已成功开启，可以在`~/MagicLLM/log.txt`中查看日志

### 4、开启视频分析系统
运行以下命令：
```bash
cd ~/onekey
./start.sh
```

## 视频分析系统
### 🚀 快速开始（30秒上手）

#### 最简单的方式

```bash
# 在Finder中双击这个文件：
🎬 启动整合系统.command
```

就这么简单！图形界面会自动打开，点击按钮选择功能即可。

#### 或者使用命令行

```bash
# 1. 进入项目目录
cd ~/onekey

# 2. 激活虚拟环境
source .venv/bin/activate

# 3. 启动（任选一种）
python3 LAUNCH_GUI.py              # 图形界面
./START_INTEGRATED_SYSTEM.command   # 命令行菜单
./快速测试_摄像头.command            # 快速测试
```

---

### 📦 项目结构

```
毕设/
│
├── 🎬 启动整合系统.command         ⭐ 主启动器（图形界面）
├── LAUNCH_GUI.py                  图形界面启动器
├── START_INTEGRATED_SYSTEM.command 命令行菜单
├── 快速测试_摄像头.command          快速测试
│
├── integrated_system.py           整合系统核心 (777行)
├── web/
│   ├── integrated.html            复古风格Web界面
│   └── 启动中心.html               启动中心页面
│
├── multi_person_tracker/          原多人追踪系统
├── ONE_KEY/                       原AI分析系统
│
└── 📚 文档
    ├── README_INTEGRATED.md       完整使用指南 ⭐
    ├── 启动方式总览.md             启动方式对比
    ├── 快速启动卡片.txt            快速参考
    └── 整合完成总结.md             系统整合说明
```

---

### ✨ 核心功能

#### 🎯 1. 实时人物追踪

* YOLOv11n高效检测
* ByteTrack持久化追踪
* 10色彩虹轨迹
* 30点历史记录

#### 👤 2. 人脸识别

* InsightFace高精度识别
* 0.40阈值智能匹配
* 自动人脸数据库
* 时间线快照记录

#### 🔴 3. OBS流媒体支持

* 虚拟相机自动检测
* RTMP流支持
* 实时流处理

#### 🎨 4. Web可视化

* Macintosh System 7.0复古风格
* 实时统计展示
* 人物识别卡片
* 时间线查看

#### 🤖 5. AI智能分析（可选）

* 场景识别
* 关键帧提取
* 智能描述
* **支持提供者：** Qwen 和 Claude Haiku 4.5

---

### 🎮 使用模式

#### 模式1: 📹 摄像头模式

实时分析本地摄像头画面

```bash
python3 integrated_system.py --camera 0
```

#### 模式2: 📁 视频文件模式

分析本地视频文件

```bash
python3 integrated_system.py --video "path/to/video.mp4"
```

#### 模式3: 🔴 OBS实时流模式

接入OBS虚拟相机或RTMP流

```bash
# OBS虚拟相机
python3 integrated_system.py --obs

# RTMP流
python3 integrated_system.py --obs --obs-url "rtmp://localhost/live"
```

#### 高级选项

```bash
# 启用AI分析
python3 integrated_system.py --camera 0 --ai

# 禁用人脸识别（仅追踪）
python3 integrated_system.py --camera 0 --no-face

# 组合使用
python3 integrated_system.py --video file.mp4 --ai
```

---

### 🤖 AI 配置（可选）

系统支持两种 AI 提供者：

#### 方案 1：阿里云 Qwen（默认）

```bash
export DASHSCOPE_API_KEY="sk-your-dashscope-key"
# 可选：指定模型
export LLM_MODEL="qwen-max"              # 文本生成
export VISION_MODEL="qwen-vl-max-latest"  # 视觉分析
```

**支持的 Qwen 模型：**

* 文本：`qwen-max`, `qwen-plus`, `qwen-turbo`
* 视觉：`qwen-vl-max-latest`, `qwen-vl-plus`

#### 方案 2：Claude Haiku 4.5 ⚡

```bash
export LLM_PROVIDER="claude"
export ANTHROPIC_API_KEY="sk-ant-your-key"
# 或使用
export CLAUDE_API_KEY="sk-ant-your-key"

# 可选：指定模型
export LLM_MODEL="claude-3-5-haiku-20241022"
export VISION_MODEL="claude-3-5-haiku-20241022"
```

**Claude Haiku 4.5 优势：**

* ⚡ 极速响应（与 Qwen 相当）
* 💰 成本低廉（比 GPT-4o mini 便宜 3倍）
* 🎯 高质量输出（Claude 3.5 家族）
* 🖼️ 多模态支持（文本+图像）

#### 环境变量完整列表

| 变量名                 | 默认值    | 说明                |
| ------------------- | ------ | ----------------- |
| `LLM_PROVIDER`      | `qwen` | `qwen` 或 `claude` |
| `DASHSCOPE_API_KEY` | -      | Qwen API 密钥       |
| `ANTHROPIC_API_KEY` | -      | Claude API 密钥     |
| `CLAUDE_API_KEY`    | -      | Claude API 密钥（别名） |
| `LLM_MODEL`         | 自动     | 文本模型名             |
| `VISION_MODEL`      | 自动     | 视觉模型名             |
| `VISION_MODEL_FAST` | 自动     | 快速视觉模型            |

---

### 🔧 系统要求

#### 必需

* Python 3.8+
* opencv-python >= 4.8.0
* ultralytics >= 8.0.0
* numpy >= 1.24.0

#### 可选

* insightface >= 0.7.3 （人脸识别）
* openai >= 1.0.0 （Qwen AI分析）
* anthropic >= 0.18.0 （Claude AI分析）

#### 硬件

* CPU: Intel i5+ (推荐i7+)
* RAM: 4GB+ (推荐8GB+)
* 摄像头: 640x480+ 分辨率
* OBS: 26.0+ 版本

---

### 📺 OBS设置

#### 启用虚拟相机

1. 打开 OBS Studio
2. 工具(Tools) → 虚拟相机(Virtual Camera)
3. 点击"启动(Start)"
4. 启动本系统，选择"OBS实时流模式"

#### RTMP流配置（高级）

详见 `README_INTEGRATED.md` 完整说明

---

### 🌐 Web界面

启动后自动打开：

* 本地: `file:///home/$USER/onekey/web/integrated.html`
* 服务: `http://localhost:8080`

**功能**:

* 📊 实时统计（FPS/人数/帧数）
* 👥 人物识别卡片
* 🎯 Active Tracks显示
* ⏱️ 时间线查看
* 🎨 复古像素风格

---

### 🎯 典型应用场景

#### 场景1: 课堂互动分析

OBS + 虚拟相机 → 实时分析学生参与度

#### 场景2: 视频资料分析

视频文件 + AI分析 → 提取关键帧和描述

#### 场景3: 实验观察

摄像头 + 人脸识别 → 追踪受试者行为

---

### 📚 文档导航

| 文档                                           | 内容             | 适合     |
| -------------------------------------------- | -------------- | ------ |
| [快速启动卡片.txt](快速启动卡片.txt)                     | ASCII艺术界面，快速上手 | 所有用户 ⭐ |
| [README_INTEGRATED.md](README_INTEGRATED.md) | 完整使用指南         | 深入学习   |
| [启动方式总览.md](启动方式总览.md)                       | 启动方式对比         | 选择最佳方式 |
| [整合完成总结.md](整合完成总结.md)                       | 系统整合说明         | 了解项目   |

---

### 🐛 常见问题

#### Q: 双击.command文件没反应？

```bash
chmod +x "🎬 启动整合系统.command"
```

#### Q: OBS虚拟相机连接不上？

确保OBS虚拟相机已启动，重启OBS试试

#### Q: 人脸识别不工作？

```bash
pip install insightface
```

#### Q: 端口8080被占用？

```bash
lsof -i :8080
kill -9 <PID>
```

更多问题请查看 `README_INTEGRATED.md`

---

### 🎨 界面预览

#### 图形化启动器

```
┌─────────────────────────────────────┐
│  🎬 智能视频分析整合系统             │
├─────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐        │
│  │📹 摄像头 │  │📁 视频   │        │
│  └──────────┘  └──────────┘        │
│  ┌──────────┐  ┌──────────┐        │
│  │🔴 OBS流  │  │🎯 旧版   │        │
│  └──────────┘  └──────────┘        │
└─────────────────────────────────────┘
```

#### Web界面

复古Macintosh System 7.0风格，实时显示统计、人物卡片、时间线

---

### 📊 性能指标

* **追踪速度**: 25-30 FPS (Intel i7)
* **人脸识别**: <100ms/人
* **内存占用**: ~500MB
* **支持人数**: 10+ 同时追踪

---

### 🔄 版本历史

#### v2.3 (2025-12-01) - 整合版 ⭐

* ✅ 整合multi_person_tracker + ONE_KEY
* ✅ 新增OBS虚拟相机支持
* ✅ 图形化启动器LAUNCH_GUI.py
* ✅ 三种一键启动方式
* ✅ 复古像素风格Web界面
* ✅ 完整文档系统

#### v2.2 (之前)

* ✅ 多色追踪系统
* ✅ 人脸识别阈值优化
* ✅ 非阻塞显示

---

### 🤝 贡献

欢迎提Issue和PR！

---

### 📄 许可证

本项目整合了多个开源组件：

* YOLOv11 (AGPL-3.0)
* InsightFace (MIT)
* OpenCV (Apache 2.0)

---

### 🆘 获取帮助

#### 查看帮助

```bash
python3 integrated_system.py --help
```

#### 启用调试模式

```bash
python3 integrated_system.py --camera 0 --verbose
```

#### 联系方式

* 项目位置: `~/onekey`
* 启动中心: `web/启动中心.html`

---

### 🎉 开始使用

**推荐新手**:

```bash
双击: 🎬 启动整合系统.command
→ 选择"📹 摄像头模式"
```

**推荐进阶**:

```bash
双击: 🎬 启动整合系统.command
→ 选择"🔴 OBS实时流模式"
→ 勾选"启用AI分析"
```

**推荐开发**:

```bash
python3 integrated_system.py --help
```

---

<div align="center">

**🎬 享受智能视频分析的乐趣！**

Made with ❤️ by ZZH

</div>

