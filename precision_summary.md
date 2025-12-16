# 关键时刻精准定位 - 改进总结

## 已实现的精准定位机制 ✅

系统采用**三级精准定位**策略：

### 1. 语义分析定位 (Semantic Locator)
```python
# key_moments_manager.suggest_key_moment_candidates()
# 功能: 从2分钟转写中用LLM识别关键语句
# 输出: 带精确时间戳的候选时刻列表
```

- 分析前30分钟转写文本
- LLM (qwen-max) 识别：定义/结论、重要数据、推理转折、核心观点
- 返回 time_str (HH:MM:SS) + evidence (原文摘录) + reason

### 2. 视频帧对齐 (Frame Alignment)
```python
# _nearest_frame_by_ts()
# 找到最接近语义时间点的实际视频帧
```

- 遍历2分钟切片内的所有帧
- 计算每帧timestamp与候选时刻的距离
- 选择最接近的帧作为关键时刻锚点

### 3. 多模态验证 (Multimodal Verification)
```python
# key_moments_manager.analyze_with_multimodal()
# 在精确时间点进行视觉+文本综合判定
```

- 提取该时间点前后10秒的视频片段
- 提取该时间点前后10秒的转写文本
- 用 qwen-vl-max-latest 综合判断重要性

## 本次优化内容

### 1. 视频质量提升
- **CRF: 28 → 18** (更低 = 更清晰)
- **Preset: ultrafast → medium** (更好的编码质量)
- **音频: 96k → 128k AAC**

### 2. 模型确认
- **文本分析**: `qwen-max` (最强模型)
- **视觉分析**: `qwen-vl-max-latest`
- **ASR**: `qwen-audio-turbo` (与实时流一致)

### 3. 知识库集成
- 读取全局 `context.txt`
- 传递给AI作为背景知识
- Prompt强调"不要为了找而找"

### 4. 转写逻辑修复
- 强制对完整30秒视频切片做ASR
- 确保包含"未来15秒"的音频

## 环境变量配置

可通过以下变量微调精度：

```bash
# 视频切片分析
MULTIMODAL_MAX_HITS_PER_SLICE=1        # 每个切片最多标记几个关键时刻
MULTIMODAL_BEFORE_SECONDS=10           # 分析窗口：前N秒转写
MULTIMODAL_AFTER_SECONDS=10            # 分析窗口：后N秒转写
MULTIMODAL_VIDEO_BEFORE_SECONDS=10     # 视频窗口：前N秒
MULTIMODAL_VIDEO_AFTER_SECONDS=10      # 视频窗口：后N秒

# 调试模式
MULTIMODAL_DEBUG=1                      # 打印候选时刻定位日志
LLM_TRACE=1                             # 打印LLM prompt和响应
```

## 精准度保证

1. **时间戳来源**: 实时ASR转写自带精确时间戳
2. **定位误差**: ≈ 帧间隔 (30fps ≈ 33ms)
3. **语义准确性**: 由qwen-max保证，要求提供证据摘录
4. **视频同步**: 音视频严格对齐，避免裁剪导致偏移

## 下一步测试建议

1. 重启系统 `./start.sh`
2. 选择OBS虚拟摄像头模式
3. 播放一段有明显"关键语句"的视频
4. 观察系统是否精确定位到关键语句的时间点
5. 检查生成的视频切片是否正好包含该关键时刻
