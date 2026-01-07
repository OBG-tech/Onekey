# Mac 迁移包使用说明

## 📦 包含内容

本精简包只包含必要的代码和配置文件，不包含历史数据。

### ✅ 已包含
- 所有Python源代码
- 启动脚本和配置文件
- HTML前端界面
- 文档和说明
- YOLO模型文件
- 空的数据目录结构

### ❌ 未包含（需在Mac上重新创建）
- Python虚拟环境（需重新安装）
- 历史录像数据
- 人脸数据库
- 关键帧图片
- 日志文件

## 🚀 Mac上的安装步骤

### 1. 解压文件
```bash
cd ~/Desktop
# 如果是压缩包，先解压
tar -xzf onekey_clean.tar.gz
```

### 2. 创建虚拟环境
```bash
cd onekey_clean
python3 -m venv .venv
source .venv/bin/activate
```

### 3. 安装依赖
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. 配置环境变量
```bash
cp .env.local.example .env.local
# 编辑 .env.local 填入你的API密钥
nano .env.local
```

### 5. 检查Mac环境
```bash
./check_macos_env.sh
```

### 6. 启动系统
```bash
# 使用Mac专用启动脚本
./🔄\ 一键重启系统.command
```

## 📚 重要文档

- `macOS_M2_移植指南.md` - Mac平台完整配置指南
- `macOS_快速参考.md` - MacOS常用命令
- `README.md` - 项目说明
- `自动录音录像指南.md` - 录音录像功能说明

## ⚠️ 注意事项

1. **模型文件**: YOLO模型已包含，但InsightFace模型需要首次运行时下载
2. **OBS设置**: 需要在Mac上重新配置OBS
3. **摄像头**: Mac摄像头索引可能不同，使用 `detect_cameras_macos.py` 检测
4. **权限**: Mac可能需要授予终端、摄像头、麦克风权限

## 🔗 获取帮助

- 查看 `macOS_M2_移植指南.md` 获取详细的Mac配置步骤
- 遇到问题查看 `📚 重要操作指令汇总.md`

---

**打包时间**: $(date)
**原项目大小**: ~125GB
**精简后大小**: ~500MB
