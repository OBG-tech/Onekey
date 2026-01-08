#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎤 实时麦克风音频录制模块
用于在摄像头模式下录制系统麦克风音频
使用共享音频管理器避免设备冲突
"""

import wave
import threading
import time
import os
from pathlib import Path
from datetime import datetime
from collections import deque
from typing import Optional, Deque, Tuple

# 导入共享音频管理器
from audio_manager import get_audio_manager, PYAUDIO_AVAILABLE

class MicrophoneRecorder:
    """麦克风录制器 - 使用共享音频管理器"""
    
    # 音频参数 (必须与SharedAudioManager一致)
    RATE = 16000
    CHANNELS = 1
    CHUNK = 3200
    FORMAT = 'paInt16'  # PyAudio.paInt16
    
    def __init__(self, output_dir=None):
        self.output_dir = Path(output_dir or "integrated_data/audio")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.is_recording = False
        # 存储 (timestamp, pcm_bytes)；用于按时间窗精确截取关键时刻音频
        self.audio_buffer: Deque[Tuple[float, bytes]] = deque()
        self.lock = threading.Lock()

        # 保留最近 N 秒音频（关键时刻默认±15秒=30秒；留足余量）
        self.buffer_max_seconds = float(os.environ.get("MIC_BUFFER_SECONDS", "60"))
        
        # 共享音频管理器
        self.audio_manager = get_audio_manager()
        self.audio_listener = None
        
        if PYAUDIO_AVAILABLE:
            print("✅ 麦克风初始化成功")
        else:
            print("❌ PyAudio未安装,麦克风功能不可用")
    
    def _on_audio(self, audio_data: bytes):
        """接收音频数据"""
        if self.is_recording:
            # 首次接收到音频数据时输出日志
            if len(self.audio_buffer) == 0:
                print(f"🎤 [DEBUG] 首次接收到音频数据: {len(audio_data)}字节")
            
            with self.lock:
                self.audio_buffer.append((time.time(), audio_data))

                # 依据时间戳裁剪，确保保留最近 buffer_max_seconds
                cutoff = time.time() - float(self.buffer_max_seconds)
                while self.audio_buffer and self.audio_buffer[0][0] < cutoff:
                    self.audio_buffer.popleft()
    
    def start_recording(self):
        """开始录制"""
        print("🎤 [DEBUG] start_recording() 被调用")
        
        if not PYAUDIO_AVAILABLE:
            print("❌ [DEBUG] PyAudio未安装")
            return False
        
        try:
            self.is_recording = True
            
            # 注册音频监听器
            self.audio_listener = self.audio_manager.register_listener(
                "MicrophoneRecorder",
                self._on_audio
            )
            
            print("🎤 [DEBUG] 已注册音频监听器")
            print("✅ 麦克风录制已启动")
            return True
        except Exception as e:
            print(f"❌ 麦克风启动失败: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def stop_recording(self):
        """停止录制"""
        self.is_recording = False
        
        # 注销音频监听器
        if self.audio_listener:
            self.audio_manager.unregister_listener(self.audio_listener)
            self.audio_listener = None
        
        print("🎤 麦克风录制已停止")
    
    def save_audio_clip(self, duration_seconds=10):
        """
        保存最近N秒的音频
        
        Args:
            duration_seconds: 要保存的秒数
            
        Returns:
            保存的文件路径
        """
        print(f"🎤 [DEBUG] save_audio_clip() 被调用, 时长={duration_seconds}秒")
        
        with self.lock:
            buffer_size = len(self.audio_buffer)
            if buffer_size:
                span = self.audio_buffer[-1][0] - self.audio_buffer[0][0]
            else:
                span = 0.0
            print(f"🎤 [DEBUG] 当前缓冲区大小: {buffer_size} chunks, 覆盖约 {span:.1f}s")
        
        if not self.audio_buffer:
            print("⚠️  音频缓冲区为空")
            return None
        
        try:
            end_ts = time.time()
            start_ts = end_ts - float(duration_seconds)
            audio_data = self._slice_by_time(start_ts, end_ts)
            print(f"🎤 [DEBUG] 选取窗口: [{start_ts:.3f}, {end_ts:.3f}], chunks={len(audio_data)}")
            
            if not audio_data:
                return None
            
            # 生成文件名
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            audio_path = self.output_dir / f"mic_{timestamp}.wav"
            print(f"🎤 [DEBUG] 准备保存到: {audio_path}")
            
            # 合并音频数据
            combined_data = b''.join(audio_data)
            print(f"🎤 [DEBUG] 合并音频数据: {len(combined_data)} 字节")
            
            # 保存为WAV文件（使用标准 wave 模块）
            wf = wave.open(str(audio_path), 'wb')
            wf.setnchannels(1)  # 单声道
            wf.setsampwidth(2)  # 16-bit = 2 bytes
            wf.setframerate(16000)  # 16kHz
            wf.writeframes(combined_data)
            wf.close()
            
            # 验证生成的文件
            print(f"🎤 [DEBUG] 验证 WAV 文件...")
            try:
                wf_verify = wave.open(str(audio_path), 'rb')
                params = wf_verify.getparams()
                print(f"🎤 [DEBUG] WAV 参数 - channels: {params.nchannels}, sample_width: {params.sampwidth}, framerate: {params.framerate}, frames: {params.nframes}")
                wf_verify.close()
            except Exception as ve:
                print(f"🎤 [DEBUG] WAV 验证失败: {ve}")
            
            print(f"   ✅ 音频已保存: {audio_path.name} ({len(combined_data)} bytes)")
            return str(audio_path)
            
        except Exception as e:
            print(f"   ⚠️ 保存音频失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _slice_by_time(self, start_ts: float, end_ts: float):
        """按时间窗切片音频（返回 pcm_bytes 列表）。"""
        if end_ts <= start_ts:
            return []
        with self.lock:
            return [pcm for ts, pcm in self.audio_buffer if start_ts <= ts <= end_ts]

    def save_audio_around(self, center_timestamp: float, before_seconds: float = 15.0, after_seconds: float = 15.0,
                          fallback_seconds: Optional[float] = None):
        """保存以 center_timestamp 为中心的时间窗音频。

        适用于关键时刻：在生成完整视频（含后段）后再调用，保证音画窗口一致。
        """
        start_ts = float(center_timestamp) - float(before_seconds)
        end_ts = float(center_timestamp) + float(after_seconds)
        audio_data = self._slice_by_time(start_ts, end_ts)
        if not audio_data and fallback_seconds:
            return self.save_audio_clip(duration_seconds=fallback_seconds)
        if not audio_data:
            print(f"⚠️  指定时间窗内无音频数据: [{start_ts:.3f}, {end_ts:.3f}]")
            return None

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            audio_path = self.output_dir / f"mic_{timestamp}.wav"
            combined_data = b"".join(audio_data)

            wf = wave.open(str(audio_path), 'wb')
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(combined_data)
            wf.close()

            print(f"   ✅ 音频已保存(对齐窗口): {audio_path.name} ({len(combined_data)} bytes)")
            return str(audio_path)
        except Exception as e:
            print(f"   ⚠️ 保存对齐音频失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def cleanup(self):
        """清理资源"""
        self.stop_recording()


# 测试代码
if __name__ == "__main__":
    print("🎤 测试麦克风录制...")
    recorder = MicrophoneRecorder()
    
    if recorder.start_recording():
        print("录制5秒...")
        time.sleep(5)
        
        audio_file = recorder.save_audio_clip(duration_seconds=5)
        if audio_file:
            print(f"✅ 测试成功! 音频保存在: {audio_file}")
        else:
            print("❌ 保存失败")
        
        recorder.cleanup()
    else:
        print("❌ 无法启动录制")
