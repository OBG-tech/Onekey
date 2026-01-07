# 🎬 OBS全程录制使用指南

## 🎯 功能说明

**新增功能：** OBS全程不间断录制

- ✅ 系统启动后自动开始OBS录制
- ✅ 一直录制到手动停止（可以录制十几个小时）
- ✅ 自动启动语音识别
- ✅ 安全停止录制，避免文件损坏

## 📋 前置准备

### 1. 安装obs-websocket-py

```bash
# 进入虚拟环境
cd /home/nucleus/onekey
source .venv/bin/activate

# 安装
pip install obs-websocket-py
```

### 2. 配置OBS WebSocket

**首次设置（只需一次）：**

1. 打开OBS
2. 点击 `工具 → obs-websocket设置`
3. ✅ 勾选 "启用WebSocket服务器"
4. 设置端口：`4455` （默认）
5. 密码：留空（或设置密码，需要同步修改脚本）
6. 点击"应用"和"确定"

### 3. OBS录制设置（重要！）

**建议设置（避免文件过大或损坏）：**

1. `文件 → 设置 → 输出 → 录像`
2. **录像格式**：`MKV` （更安全，崩溃不会损坏）
3. **编码器**：`x264` 或 硬件编码
4. **比特率**：`5000-8000 Kbps`
5. **录像路径**：选择磁盘空间充足的目录（推荐预留100GB以上）

**可选：启用分段录制**

1. `文件 → 设置 → 高级`
2. ✅ 勾选 "自动重新连接"
3. 在"录像"部分：
   - ✅ 勾选 "自动分段"
   - 分段类型选择：`时间` 或 `文件大小`
   - 时间：建议 `30分钟` 或 `1小时`
   - 文件大小：建议 `2GB` 或 `4GB`

## 🚀 使用方法

### 启动系统（自动录制）

```bash
./start_with_full_recording.sh
```

**启动流程：**
1. ✅ 自动启动OBS
2. ⏸️ 提示在OBS中启动虚拟摄像机（手动确认）
3. ✅ 自动启动系统服务
4. ✅ 自动启动语音识别
5. ✅ **自动启动OBS录制** （全程录制）
6. ✅ 打开Web界面

### 停止系统（安全停止录制）

```bash
./stop_with_full_recording.sh
```

**停止流程：**
1. ✅ 自动停止OBS录制
2. ✅ 停止系统服务
3. ✅ 显示录制统计

### 查看录制状态

```bash
python3 obs_auto_record.py status
```

## 📊 录像文件位置

**OBS完整录像：**
- 默认位置：`~/视频/` 或 OBS设置中指定的路径
- 文件格式：`.mkv` 或 `.mp4`
- 文件大小：取决于录制时长（约3-5GB/小时）

**查看录像：**
```bash
# 打开录像目录
xdg-open ~/视频/

# 查看最新录像
ls -lht ~/视频/ | head -10
```

## 🔍 验证设置正确

### 测试OBS控制是否正常

```bash
# 1. 确保OBS正在运行
# 2. 测试连接
python3 obs_auto_record.py status

# 应该显示：
# ✅ 已连接到 OBS
# 📊 OBS录制状态
```

如果失败，检查：
- OBS是否正在运行
- WebSocket服务器是否已启用
- 端口是否为4455
- 防火墙是否阻止

## ⚠️ 重要注意事项

### 1. 磁盘空间

**10小时录像约需：**
- 1080p, 6000kbps: 约 27GB
- 1080p, 8000kbps: 约 36GB
- 4K:  约 100GB+

**监控空间：**
```bash
# 检查可用空间
df -h ~/视频/

# 查看录像总大小
du -sh ~/视频/
```

### 2. 长时间录制建议

- ✅ 启用分段录制（30分钟或2GB一个文件）
- ✅ 定期检查录制状态
- ✅ 确保电源稳定
- ✅ 定期备份重要录像

### 3. 系统崩溃预防

**如果系统崩溃，MKV格式可以恢复大部分内容：**
```bash
# 查找未完成的录像
find ~/视频/ -name "*.mkv" -type f

# 可以尝试播放，通常能播放到崩溃前的内容
```

## 🛠️ 故障排除

### 问题1: 无法自动启动OBS录制

**检查清单：**
```bash
# 1. OBS是否运行
pgrep obs

# 2. obs-websocket-py是否安装
python3 -c "import obsws_python; print('OK')"

# 3. 测试连接
python3 obs_auto_record.py status
```

**解决方法：**
- 在OBS中启用WebSocket服务器
- 检查端口是否正确（4455）
- 如果设置了密码，在脚本中配置密码

### 问题2: OBS在Web界面显示正常，但没有录像文件

**可能原因：**
- OBS录制未真正启动
- 录像路径设置错误
- 磁盘空间不足

**解决方法：**
```bash
# 检查OBS录制状态
python3 obs_auto_record.py status

# 手动在OBS中点击"开始录制"
# 检查OBS设置中的录像路径
```

### 问题3: 录像文件损坏

**解决方法：**
- 使用MKV格式（更安全）
- 启用分段录制
- 确保使用 `stop_with_full_recording.sh` 正常停止

## 📊 使用流程对比

### 新方式（全程录制）

```bash
# 启动
./start_with_full_recording.sh
# → OBS自动开始录制

# 进行你的实验/会议（10小时）

# 停止
./stop_with_full_recording.sh
# → OBS自动停止录制
# → 得到完整的10小时录像
```

### 旧方式（需手动）

```bash
# 启动
./start_auto_recording.sh
# → 需要手动在OBS点击"开始录制"

# 进行实验
# 可能忘记开启录制！

# 停止
kill $(cat service.pid)
# → 需要手动在OBS点击"停止录制"
```

## 💾 录像管理

### 备份重要录像

```bash
# 复制到外部硬盘
cp ~/视频/*.mkv /media/外部硬盘/备份/

# 或打包
tar -czf obs_recordings_$(date +%Y%m%d).tar.gz ~/视频/*.mkv
```

### 清理旧录像

```bash
# 删除30天前的录像
find ~/视频/ -name "*.mkv" -mtime +30 -delete

# 或手动筛选删除
ls -lht ~/视频/
```

## 🔗 相关文件

| 文件 | 说明 |
|------|------|
| `start_with_full_recording.sh` | 启动脚本（自动录制） |
| `stop_with_full_recording.sh` | 停止脚本（安全停止） |
| `obs_auto_record.py` | OBS控制脚本 |
| `start_auto_recording.sh` | 原启动脚本（需手动录制） |

## ✅ 快速检查清单

启动前确认：
- [ ] obs-websocket-py已安装
- [ ] OBS WebSocket已启用
- [ ] OBS录像路径已设置
- [ ] 磁盘空间充足（预留100GB+）
- [ ] OBS录制格式设为MKV
- [ ] （可选）启用分段录制

使用时确认：
- [ ] 启动脚本后，OBS录制已开始
- [ ] 定期检查: `python3 obs_auto_record.py status`
- [ ] 关闭前使用 `stop_with_full_recording.sh`

## 📞 获取帮助

**查看日志：**
```bash
tail -f service_output.log
```

**联系支持：**
- 查看实现计划：`implementation_plan.md`
- 查看完整文档：`📹 视频存储位置说明.md`

---

**重要提醒：** 使用新脚本 `start_with_full_recording.sh` 可以实现OBS全程自动录制！
