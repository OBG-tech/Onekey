# 🎤 语音识别(ASR)优化说明

## 📋 问题诊断

### 原有问题
1. **Transcription.async_call** 使用本地文件URL (`file://`) 导致 `DECODE_ERROR`
2. 多个ASR模型均返回 `Model not found` 错误
3. `qwen2-audio-instruct` 不支持 OpenAI 兼容模式 (404错误)

### 根本原因
- **实时ASR模块**使用 `Recognition.call()` **同步API** ✅ 成功
- **关键时刻模块**使用 `Transcription.async_call()` **异步API** ❌ 失败

## 🔧 优化方案

### 实施策略
参考 `realtime_asr.py` 的成功实现,统一使用 **Recognition.call()** 同步API

### 代码改动

#### 修改文件: `key_moments_manager.py`

**方法**: `_transcribe_audio()`

**改动内容**:
1. 移除 `Transcription.async_call` 异步方式
2. 采用 `Recognition.call()` 同步方式(与实时ASR一致)
3. 优化模型尝试顺序:
   ```python
   models_to_try = [
       'paraformer-realtime-v2',      # ✅ 实时ASR使用的模型 (推荐)
       'paraformer-v2',               # 批量转录模型
       'paraformer-realtime-8k-v2',   # 8k采样率版本
   ]
   ```

#### 核心改进
```python
# ✅ 新方式: 同步API (参考 realtime_asr.py)
recognition = Recognition(
    model='paraformer-realtime-v2',
    format='wav',       # 文件格式
    sample_rate=16000,  # 采样率
    callback=None       # 同步调用不需要回调
)

# 直接传入文件路径
result = recognition.call(str(audio_path))
```

```python
# ❌ 旧方式: 异步API (有DECODE_ERROR问题)
task = Transcription.async_call(
    model='paraformer-v2',
    file_urls=[file_url],  # 本地文件URL有问题
    language_hints=['zh', 'en']
)
result = Transcription.wait(task, timeout=60)
```

## 🎯 优化流程

### 新的工作流程
```
用户标记关键时刻
    ↓
录制10秒视频片段 (前后各10秒)
    ↓
合成完整视频 (19.6秒)
    ↓
添加麦克风音频
    ↓
提取音频文件 (WAV, 16kHz, mono)
    ↓
🎤 ASR 语音转文字 (Recognition.call 同步API)
    ↓
🤖 LLM 多模态分析 (视频画面 + 语音文本)
    ↓
生成关键时刻描述
```

### 技术优势
- ✅ **同步调用**: 直接读取本地文件,避免URL编码问题
- ✅ **模型兼容**: 与实时ASR使用相同模型,确保可用性
- ✅ **错误处理**: 优雅降级,ASR失败时仍可进行纯视觉分析
- ✅ **统一接口**: 两个ASR场景使用相同的API方式

## 🧪 测试方法

### 1. 重启系统
```bash
cd /Users/nucleus/Desktop/magicrgb
source .venv/bin/activate
python3 integrated_system.py --camera 0
```

### 2. 标记关键时刻
- 在Web界面点击"标记关键时刻"按钮
- 等待10秒让系统录制完整视频

### 3. 观察日志
期望看到:
```
🎤 正在进行语音转文字 (文件大小: 608334 bytes)...
🔄 尝试模型: paraformer-realtime-v2
✅ 模型 paraformer-realtime-v2 识别成功
✅ 语音转文字成功: 45 字
📝 识别内容: 大家好,今天我们来讨论一下智能视频分析系统...
```

### 4. 检查API权限 (如果仍失败)
访问 https://dashscope.console.aliyun.com/
- 确认已开通 "语音识别" 服务
- 检查 API Key 是否有语音识别权限
- 查看配额使用情况

## 📊 预期效果

### 成功场景
```
✅ 语音转文字成功: 120 字
📝 识别内容: 本次会议主要讨论了项目进度和技术难点。首先是...
🤖 开始多模态AI分析...
✅ AI 分析完成: anchor_1765458392_609
   1. 会议场景,多人协作讨论
   2. 主讲人正在介绍项目方案
   3. 团队成员积极参与交流,展现良好协作氛围
```

### 降级场景 (ASR失败)
```
⚠️ Recognition API 返回空结果
💡 建议: 检查 DashScope API 密钥权限或模型可用性
🔄 系统将使用纯视觉 AI 分析
🤖 开始纯视觉AI分析...
✅ AI 分析完成 (仅视觉)
   1. 室内办公环境,书架背景
   2. 一名学生面对镜头,专注倾听
   3. 学习者准备参与协作讨论
```

## 🔍 技术细节

### Recognition API vs Transcription API

| 特性     | Recognition.call() | Transcription.async_call() |
| -------- | ------------------ | -------------------------- |
| 调用方式 | 同步               | 异步                       |
| 文件传递 | 直接路径           | URL (有编码问题)           |
| 适用场景 | 短音频 (<1分钟)    | 长音频 (>1分钟)            |
| 成功率   | ✅ 高               | ❌ 低 (本地文件)            |
| 实时ASR  | ✅ 使用             | ❌ 不使用                   |

### 音频参数要求
- **格式**: WAV (PCM)
- **采样率**: 16000 Hz
- **声道**: 单声道 (mono)
- **位深度**: 16-bit
- **时长**: 建议 <60秒

### 模型选择策略
1. **paraformer-realtime-v2**: 实时模型,通用场景,响应快
2. **paraformer-v2**: 批量模型,准确度高
3. **paraformer-realtime-8k-v2**: 电话/低质量音频

## 💡 故障排除

### Q1: 仍然返回 "Model not found"
**A**: 检查 DashScope 控制台是否开通了语音识别服务

### Q2: API 配额不足
**A**: 升级 DashScope 套餐或等待配额重置

### Q3: 音频文件过大
**A**: 当前系统限制20秒视频,音频文件约640KB,符合要求

### Q4: 想切换到 Claude 进行音视频分析
**A**: Claude 支持原生音视频输入,可直接发送视频文件:
```bash
export LLM_PROVIDER=claude
export ANTHROPIC_API_KEY=your_api_key
```

## 📚 参考资料

- [阿里云 DashScope 语音识别文档](https://help.aliyun.com/zh/model-studio/developer-reference/paraformer)
- [实时ASR实现](realtime_asr.py) - 参考成功案例
- [关键时刻管理器](key_moments_manager.py) - 本次优化文件

---

**修改日期**: 2025年12月11日  
**修改人**: GitHub Copilot  
**测试状态**: 待验证
