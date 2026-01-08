# -*- coding: utf-8 -*-
"""共享音频管理器 - 解决多模块同时访问麦克风的冲突

统一管理音频流，支持多个监听器同时接收音频数据。

性能注意：音频回调线程必须尽量轻量，不能在回调里为每个 chunk 创建新线程，
否则会造成线程风暴、卡顿、甚至进程不稳定。
"""

import threading
import queue
from typing import Callable, List, Optional
import numpy as np

# 尝试导入PyAudio
PYAUDIO_AVAILABLE = False
try:
    import pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    print("⚠️  PyAudio未安装,音频功能不可用")


class AudioListener:
    """音频监听器基类"""
    def __init__(self, name: str, callback: Callable[[bytes], None]):
        self.name = name
        self.callback = callback
        self.enabled = True

        # 每个监听器独立队列/线程：避免某个监听器处理慢拖垮所有监听器（从而造成全局延迟）
        self._queue: "queue.Queue[bytes | None]" = queue.Queue(maxsize=30)
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 1.5):
        self._stop_event.set()
        try:
            self._queue.put_nowait(None)
        except Exception:
            pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def push(self, audio_data: bytes):
        if not self.enabled:
            return
        try:
            self._queue.put_nowait(audio_data)
        except queue.Full:
            # 丢弃最旧帧，保留最新，避免延迟越来越大
            try:
                _ = self._queue.get_nowait()
            except Exception:
                pass
            try:
                self._queue.put_nowait(audio_data)
            except Exception:
                pass

    def _run(self):
        while not self._stop_event.is_set():
            try:
                audio_data = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue
            if audio_data is None:
                continue
            if self.enabled and self.callback:
                try:
                    self.callback(audio_data)
                except Exception as e:
                    print(f"⚠️  {self.name} 音频处理错误: {e}")
    
    def on_audio(self, audio_data: bytes):
        """接收音频数据（快速入队，实际处理在监听器线程内执行）"""
        self.push(audio_data)


class SharedAudioManager:
    """
    共享音频管理器
    - 单一音频流管理
    - 支持多个监听器同时接收数据
    - 线程安全
    """
    
    # 单例模式
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        # 避免重复初始化
        if hasattr(self, '_initialized'):
            return
        
        self._initialized = True
        
        # 音频参数
        self.FORMAT = pyaudio.paInt16 if PYAUDIO_AVAILABLE else None
        self.CHANNELS = 1
        self.RATE = 16000
        self.CHUNK = 3200
        
        # PyAudio实例
        self.audio = None
        self.stream = None
        
        # 监听器管理
        self.listeners: List[AudioListener] = []
        self.listeners_lock = threading.Lock()
        
        # 状态管理
        self.is_running = False
        self.stream_lock = threading.Lock()

        # 音频分发队列（回调线程 -> 分发线程）
        # 队列越大越可能积压导致“越听越慢”，这里刻意偏小。
        self._dispatch_queue: "queue.Queue[bytes | None]" = queue.Queue(maxsize=15)
        self._dispatch_stop_event = threading.Event()
        self._dispatch_thread = None
        
        print("✅ 共享音频管理器初始化完成")
    
    def register_listener(self, name: str, callback: Callable[[bytes], None]) -> AudioListener:
        """
        注册音频监听器
        
        Args:
            name: 监听器名称
            callback: 音频数据回调函数,接收bytes参数
        
        Returns:
            AudioListener对象
        """
        with self.listeners_lock:
            listener = AudioListener(name, callback)
            listener.start()
            self.listeners.append(listener)
            print(f"✅ 注册音频监听器: {name}")
            
            # 如果之前没有运行,现在有监听器了就启动
            if not self.is_running and PYAUDIO_AVAILABLE:
                self._start_stream()
            
            return listener
    
    def unregister_listener(self, listener: AudioListener):
        """注销音频监听器"""
        with self.listeners_lock:
            if listener in self.listeners:
                self.listeners.remove(listener)
                try:
                    listener.stop()
                except Exception:
                    pass
                print(f"✅ 注销音频监听器: {listener.name}")
            
            # 如果没有监听器了就停止流
            if len(self.listeners) == 0 and self.is_running:
                self._stop_stream()
    
    def _audio_callback(self, in_data, frame_count, time_info, status):
        """PyAudio回调函数 - 分发音频数据到所有监听器"""
        if status:
            print(f"⚠️  音频流状态: {status}")

        # 关键：回调线程只做入队，避免阻塞/创建大量线程
        try:
            self._dispatch_queue.put_nowait(in_data)
        except queue.Full:
            # 队列满：丢弃最旧的一帧，保留最新，防止积压导致延迟越来越大
            try:
                _ = self._dispatch_queue.get_nowait()
            except Exception:
                pass
            try:
                self._dispatch_queue.put_nowait(in_data)
            except Exception:
                pass
        
        return (in_data, pyaudio.paContinue)

    def _dispatch_loop(self):
        """分发线程：从队列读取音频，依次调用各监听器回调。"""
        while not self._dispatch_stop_event.is_set():
            try:
                audio_data = self._dispatch_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if audio_data is None:
                continue

            # 复制监听器快照，避免持锁调用回调导致死锁/阻塞注册
            with self.listeners_lock:
                listeners = list(self.listeners)

            # 关键：这里只做“推送”，不要做实际耗时处理
            for listener in listeners:
                if listener.enabled:
                    listener.push(audio_data)
    
    def _start_stream(self):
        """启动音频流"""
        if not PYAUDIO_AVAILABLE:
            print("⚠️  PyAudio不可用,无法启动音频流")
            return False
        
        with self.stream_lock:
            if self.is_running:
                return True
            
            try:
                # 初始化PyAudio
                if self.audio is None:
                    self.audio = pyaudio.PyAudio()
                
                # 打开音频流
                self.stream = self.audio.open(
                    format=self.FORMAT,
                    channels=self.CHANNELS,
                    rate=self.RATE,
                    input=True,
                    frames_per_buffer=self.CHUNK,
                    stream_callback=self._audio_callback,
                    start=True
                )
                
                self.is_running = True
                # 启动分发线程
                self._dispatch_stop_event.clear()
                if self._dispatch_thread is None or not self._dispatch_thread.is_alive():
                    self._dispatch_thread = threading.Thread(target=self._dispatch_loop, daemon=True)
                    self._dispatch_thread.start()
                print(f"🎤 音频流启动成功 (16kHz, mono, {self.CHUNK} chunk)")
                return True
                
            except Exception as e:
                print(f"❌ 音频流启动失败: {e}")
                return False
    
    def _stop_stream(self):
        """停止音频流"""
        with self.stream_lock:
            if not self.is_running:
                return
            
            try:
                if self.stream:
                    self.stream.stop_stream()
                    self.stream.close()
                    self.stream = None
                
                self.is_running = False
                # 停止分发线程
                self._dispatch_stop_event.set()
                try:
                    self._dispatch_queue.put_nowait(None)
                except Exception:
                    pass
                if self._dispatch_thread and self._dispatch_thread.is_alive():
                    self._dispatch_thread.join(timeout=2)

                # 停止各监听器线程
                with self.listeners_lock:
                    listeners = list(self.listeners)
                for l in listeners:
                    try:
                        l.stop(timeout=0.5)
                    except Exception:
                        pass
                print("🎤 音频流已停止")
                
            except Exception as e:
                print(f"⚠️  停止音频流时出错: {e}")
    
    def get_status(self):
        """获取音频管理器状态"""
        return {
            "is_running": self.is_running,
            "listener_count": len(self.listeners),
            "listeners": [
                {
                    "name": l.name,
                    "enabled": l.enabled
                }
                for l in self.listeners
            ],
            "audio_config": {
                "rate": self.RATE,
                "channels": self.CHANNELS,
                "chunk": self.CHUNK
            }
        }
    
    def cleanup(self):
        """清理资源"""
        # 先停分发线程
        self._dispatch_stop_event.set()
        try:
            self._dispatch_queue.put_nowait(None)
        except Exception:
            pass
        if self._dispatch_thread and self._dispatch_thread.is_alive():
            self._dispatch_thread.join(timeout=2)

        self._stop_stream()
        
        with self.listeners_lock:
            listeners = list(self.listeners)
            self.listeners.clear()

        for l in listeners:
            try:
                l.stop(timeout=0.5)
            except Exception:
                pass
        
        if self.audio:
            self.audio.terminate()
            self.audio = None
        
        print("✅ 音频管理器已清理")


# 全局单例实例
_audio_manager = None

def get_audio_manager() -> SharedAudioManager:
    """获取共享音频管理器单例"""
    global _audio_manager
    if _audio_manager is None:
        _audio_manager = SharedAudioManager()
    return _audio_manager
