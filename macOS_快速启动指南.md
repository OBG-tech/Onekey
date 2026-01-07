# 🍎 OneKey macOS 快速启动指南

## 📋 准备工作

### 1. 配置 API Keys

编辑环境变量配置文件：

```bash
nano .env.local
```

**必需配置**（至少配置一个）：

- **阿里云 Qwen**：修改 `DASHSCOPE_API_KEY`
- **Anthropic Claude**：修改 `ANTHROPIC_API_KEY`

获取 API Key：
- Qwen: https://dashscope.console.aliyun.com/apiKey
- Claude: https://console.anthropic.com/settings/keys

### 2. 选择 AI 提供商

**默认使用 Qwen**，无需额外配置。

**使用 Claude**，取消 `.env.local` 中的注释：
```bash
export LLM_PROVIDER="claude"
```

## 🚀 启动系统

### 方式 1: 使用启动脚本（推荐）

```bash
./start_macos.sh
```

脚本会自动：
- ✅ 激活虚拟环境
- ✅ 加载环境变量
- ✅ 检查配置
- ✅ 启动系统

### 方式 2: 手动启动

```bash
# 1. 激活虚拟环境
source .venv/bin/activate

# 2. 加载环境变量
source .env.local

# 3. 启动系统
python integrated_system.py
```

## 📹 系统功能

启动后可使用：

1. **Web 界面**: 浏览器访问 `http://localhost:8000/integrated_final_live.html`
2. **实时视频分析**: 自动检测和追踪人物
3. **AI 解说**: 实时生成场景解说
4. **关键时刻标记**: 空格键手动标记 + AI 自动检测
5. **ESP32 按钮**: 硬件按钮标记（需连接设备）

## 🎤 音频功能

系统支持实时语音识别，启动后会自动：
- 录制麦克风音频
- 实时转写成文字
- 集成到 AI 分析中

## 🛑 停止系统

在终端按 `Ctrl + C`

## 🔍 故障排除

### API Key 错误
```bash
# 检查环境变量
echo $DASHSCOPE_API_KEY
echo $ANTHROPIC_API_KEY

# 重新加载配置
source .env.local
```

### 摄像头无法访问
```bash
# 检查摄像头
python -c "import cv2; cap = cv2.VideoCapture(0); print('OK' if cap.isOpened() else 'Failed')"
```

### 虚拟环境问题
```bash
# 重新创建虚拟环境
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements_no_audio.txt
pip install PyAudio
```

## 📝 日志查看

系统日志保存在：
- `integrated_data/logs/` - 系统日志
- `integrated_data/key_moments/` - 关键时刻记录
- `integrated_data/transcripts/` - 语音转写文本

## 🎯 高级配置

在 `.env.local` 中可配置：

```bash
# 模型选择
export YOLO_MODEL="yolo11n.pt"

# 人脸识别（需要额外安装）
export FACE_RECOGNITION="false"

# 自动录制
export AUTO_RECORDING="true"

# 调试模式
export DEBUG="true"
export LOG_LEVEL="INFO"
```

## 💡 提示

- 首次运行会下载 YOLO 模型（约 6MB），请耐心等待
- 确保摄像头权限已授予终端应用
- 使用 OBS Virtual Camera 可以共享摄像头给多个应用
- 系统会自动保存关键时刻的视频片段和截图

---

**需要帮助？** 查看完整文档：
- `README.md` - 系统总览
- `macOS_M2_移植指南.md` - macOS 特定说明
- `使用说明.md` - 详细功能说明
