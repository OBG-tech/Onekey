# 🔧 AI模型配置修复说明

## 🐛 问题原因

错误信息：
```
[AI分析失败] 错误: NotFoundError: Error code: 404 - {'error': {'message': 'The model `gpt-5.1-codex-max` does not exist or you do not have access to it.', 'type': 'invalid_request_error', 'param': None, 'code': 'model_not_found'}}
```

**根本原因**：`.env.local` 文件中配置了错误的模型名称 `gpt-5.1-codex-max`，这是一个不存在的模型。

## ✅ 已修复

**文件**：`/home/artinx/onekey/.env.local`

**修改前**：
```bash
LLM_MODEL=gpt-5.1-codex-max
VISION_MODEL_FAST=gpt-5.1-codex-max
VISION_MODEL=gpt-5.1-codex-max
```

**修改后**：
```bash
LLM_MODEL=qwen-max
VISION_MODEL_FAST=qwen-vl-plus
VISION_MODEL=qwen-vl-max-latest
```

## 📋 正确的Qwen模型名称

### 文本模型（用于文本生成和总结）

| 模型名称 | 描述 | 用途 |
|---------|------|------|
| `qwen-max` | 最强文本模型 | 推荐用于关键时刻分析 ⭐ |
| `qwen-plus` | 平衡型模型 | 性价比高 |
| `qwen-turbo` | 快速模型 | 实时场景 |
| `qwen-long` | 长文本模型 | 处理超长上下文 |

### 视觉模型（用于图像分析）

| 模型名称 | 描述 | 用途 |
|---------|------|------|
| `qwen-vl-max-latest` | 最强视觉模型 | 推荐用于关键时刻 ⭐ |
| `qwen-vl-plus` | 快速视觉模型 | 快速分析场景 |
| `qwen-vl-max` | 旧版最强模型 | 稳定版本 |

## 🔧 配置说明

### 完整的 .env.local 配置示例

```bash
# Qwen / DashScope API密钥
DASHSCOPE_API_KEY=sk-your-api-key-here

# LLM 提供商（qwen 或 claude）
LLM_PROVIDER=qwen

# 文本模型（用于文本总结和分析）
LLM_MODEL=qwen-max

# 视觉模型 - 快速版（用于实时分析）
VISION_MODEL_FAST=qwen-vl-plus

# 视觉模型 - 完整版（用于关键时刻详细分析）
VISION_MODEL=qwen-vl-max-latest

# ASR 语音识别（可选，默认优先使用 fireredasr）
# ASR_PROVIDER=qwen
# ASR_PROVIDER=fireredasr

# 关键时刻时间窗口（可选）
# KEY_MOMENT_BEFORE_SECONDS=15
# KEY_MOMENT_AFTER_SECONDS=15

# 麦克风缓冲时长（可选）
# MIC_BUFFER_SECONDS=60
```

## 🚀 使用 Claude 模型（可选）

如果你有 Claude API 密钥，也可以使用：

```bash
# Claude API 密钥
ANTHROPIC_API_KEY=sk-ant-your-key-here

# 使用 Claude
LLM_PROVIDER=claude
LLM_MODEL=claude-3-5-haiku-20241022
VISION_MODEL_FAST=claude-3-5-haiku-20241022
VISION_MODEL=claude-3-5-haiku-20241022
```

### 支持的 Claude 模型

| 模型名称 | 描述 | 特点 |
|---------|------|------|
| `claude-3-5-sonnet-20241022` | 最强模型 | 高质量，较贵 |
| `claude-3-5-haiku-20241022` | 快速模型 | 性价比最高 ⭐ |
| `claude-3-opus-20240229` | 旧版最强 | 稳定但贵 |

## 🔍 验证配置

### 方法1：运行测试脚本

```bash
cd /home/artinx/onekey
python3 test_ai_analysis.py
```

**预期输出**：
```
✅ API Key: sk-84c8ffca...ff07
✅ LLM 响应: 我是通义千问...
✅ 视觉LLM 响应: 图像中显示...
```

### 方法2：检查环境变量

```bash
# 查看当前配置
cat .env.local | grep -E "LLM_MODEL|VISION_MODEL"

# 应该显示：
# LLM_MODEL=qwen-max
# VISION_MODEL_FAST=qwen-vl-plus
# VISION_MODEL=qwen-vl-max-latest
```

### 方法3：启动系统并观察

```bash
./start_multicam.sh
# 或
python3 integrated_system.py --camera auto
```

在终端中查找：
```
✅ KeyMomentsManager 初始化成功
   LLM 提供商: qwen
   视觉模型: qwen-vl-max-latest
   文本模型: qwen-max
```

## ⚠️ 常见错误配置

### ❌ 错误示例1：使用 GPT 模型名称

```bash
LLM_MODEL=gpt-4
VISION_MODEL=gpt-4-vision
```

**问题**：这是 OpenAI 的模型，不能用于 Qwen/DashScope API

**修复**：使用 `qwen-max` 和 `qwen-vl-max-latest`

### ❌ 错误示例2：拼写错误

```bash
LLM_MODEL=qwen-max-latest  # ❌ 文本模型没有 -latest 后缀
VISION_MODEL=qwen-vl-max   # ⚠️ 建议用 qwen-vl-max-latest
```

**修复**：
```bash
LLM_MODEL=qwen-max
VISION_MODEL=qwen-vl-max-latest
```

### ❌ 错误示例3：混用不同提供商

```bash
LLM_PROVIDER=qwen
LLM_MODEL=claude-3-5-haiku-20241022  # ❌ 混用
```

**修复**：保持一致
```bash
# 全部使用 Qwen
LLM_PROVIDER=qwen
LLM_MODEL=qwen-max

# 或全部使用 Claude
LLM_PROVIDER=claude
LLM_MODEL=claude-3-5-haiku-20241022
```

## 📊 模型性能对比

### Qwen 模型推荐配置

| 场景 | 配置 | 说明 |
|------|------|------|
| **最高质量** | `qwen-max` + `qwen-vl-max-latest` | 推荐用于重要项目 ⭐ |
| **平衡性能** | `qwen-plus` + `qwen-vl-plus` | 日常使用 |
| **最快速度** | `qwen-turbo` + `qwen-vl-plus` | 实时场景 |

### Claude 模型推荐配置

| 场景 | 配置 | 说明 |
|------|------|------|
| **最高质量** | `claude-3-5-sonnet-20241022` | 质量最好但较贵 |
| **性价比** | `claude-3-5-haiku-20241022` | 推荐 ⭐ |

## 🔄 应用配置更改

修改 `.env.local` 后需要重启系统：

```bash
# 1. 停止当前运行的系统（Ctrl+C）

# 2. 重新启动
./start_multicam.sh
# 或
python3 integrated_system.py --camera auto

# 3. 观察启动日志，确认模型配置正确
# 应该看到：
#    视觉模型: qwen-vl-max-latest
#    文本模型: qwen-max
```

## 💡 性能优化建议

### 推荐配置（默认）

```bash
LLM_MODEL=qwen-max              # 最强文本模型
VISION_MODEL_FAST=qwen-vl-plus  # 快速视觉（实时分析）
VISION_MODEL=qwen-vl-max-latest # 完整视觉（关键时刻）
```

这个配置：
- ✅ 实时分析使用快速模型（低延迟）
- ✅ 关键时刻使用最强模型（高质量）
- ✅ 平衡性能和成本

### 如果API调用较慢

```bash
# 全部使用快速模型
LLM_MODEL=qwen-plus
VISION_MODEL_FAST=qwen-vl-plus
VISION_MODEL=qwen-vl-plus
```

### 如果需要最高质量

```bash
# 全部使用最强模型
LLM_MODEL=qwen-max
VISION_MODEL_FAST=qwen-vl-max-latest
VISION_MODEL=qwen-vl-max-latest
```

## 📝 总结

✅ **已修复**：`.env.local` 中的模型名称已更正为有效的 Qwen 模型

✅ **推荐配置**：
- 文本模型：`qwen-max`
- 快速视觉：`qwen-vl-plus`  
- 完整视觉：`qwen-vl-max-latest`

✅ **验证方法**：运行 `python3 test_ai_analysis.py` 测试连接

⚠️ **注意**：修改配置后需要重启系统才能生效

---

**修复日期**：2026-01-12  
**状态**：✅ 已解决  
**影响**：AI分析功能现在应该可以正常工作
