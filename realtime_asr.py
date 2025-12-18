"""实时语音识别模块 (Realtime ASR)

- 默认使用阿里云 DashScope 流式 ASR
- 当环境变量 ASR_PROVIDER=fireredasr 时，使用本地 FireRedASR-AED 离线分段转写
- 使用共享音频管理器避免设备冲突
"""

import threading
import time
import os
import json
from pathlib import Path
from datetime import datetime
from collections import deque
import wave
import tempfile
from typing import Optional

import numpy as np

# 导入共享音频管理器
from audio_manager import get_audio_manager, PYAUDIO_AVAILABLE

# 检查DashScope可用性
DASHSCOPE_ASR_AVAILABLE = False

try:
    from dashscope.audio.asr import Recognition, RecognitionCallback
    import dashscope
    DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY")
    if DASHSCOPE_API_KEY:
        DASHSCOPE_ASR_AVAILABLE = True
        dashscope.api_key = DASHSCOPE_API_KEY
except ImportError:
    pass


# 检查 FireRedASR 可用性（仅做轻量导入检查，不在此处加载大模型）
FIREREDASR_ASR_AVAILABLE = False
FIREREDASR_IMPORT_ERROR = ""
try:
    # 允许直接从本项目目录下的 FireRedASR/ 或 vendor/FireRedASR/ 导入
    try:
        from fireredasr.models.fireredasr import FireRedAsr  # noqa: F401
    except Exception:
        here = Path(__file__).parent
        candidates = [here / "FireRedASR", here / "vendor" / "FireRedASR"]
        for c in candidates:
            if c.exists() and str(c) not in os.sys.path:
                os.sys.path.insert(0, str(c))
        from fireredasr.models.fireredasr import FireRedAsr  # noqa: F401
    FIREREDASR_ASR_AVAILABLE = True
except Exception:
    FIREREDASR_ASR_AVAILABLE = False
    try:
        import traceback
        FIREREDASR_IMPORT_ERROR = traceback.format_exc(limit=2)
    except Exception:
        FIREREDASR_IMPORT_ERROR = "(unknown import error)"

    # 额外诊断：当前进程使用的解释器（便于定位是否跑错环境）
    try:
        FIREREDASR_IMPORT_ERROR += f"\n[debug] sys.executable={os.sys.executable}"
    except Exception:
        pass


class TranscriptSegment:
    """转录片段"""
    def __init__(self, text, timestamp, is_final=True):
        self.text = text
        self.timestamp = timestamp
        self.is_final = is_final


class RealtimeASR:
    """实时语音识别类 - 使用共享音频管理器 + 批量识别模式"""
    
    RATE = 16000
    CHANNELS = 1
    CHUNK = 3200

    def __init__(self, output_dir=None, segment_seconds: float = 1.5):
        """
        初始化实时语音识别
        
        Args:
            output_dir: 转录文本保存目录
        """
        self.output_dir = Path(output_dir) if output_dir else Path("integrated_data/transcripts")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.is_recording = False
        self.is_paused = False
        self.transcript_segments = deque(maxlen=1000)  # 最多保存1000个片段
        self.current_text = ""
        self.lock = threading.Lock()
        
        # 共享音频管理器
        self.audio_manager = get_audio_manager()
        self.audio_listener = None
        
        # 流式识别
        self.recognition = None
        self.recognition_thread = None
        
        # 自动重连机制
        self.connection_failed = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 3
        self.reconnect_delay = 2.0  # 初始延迟2秒

        # 离线分段识别（FireRedASR / FunASR）
        self.segment_seconds = max(1.0, float(segment_seconds))
        self._audio_segment_buffer = deque()
        self._firered_model = None
        self._firered_last_text = ""
        
        # FunASR 模型
        self.funasr_model = None
        self._funasr_last_text = ""
        
        # 外部回调 - 用于将转写结果通知外部系统
        self.on_transcript_update = None

        # provider 选择
        self.asr_provider = os.environ.get("ASR_PROVIDER", "qwen").strip().lower()

        # 便于状态查询：记录当前模型信息（不保证一定可用，但能回答“现在ASR是什么模型”）
        self.asr_model = ""
        self.asr_model_dir = ""
        self.asr_type = ""
        
        # 检查依赖
        if not PYAUDIO_AVAILABLE:
            print("⚠️  PyAudio未安装,实时语音识别不可用")
            return

        # FunASR 支持
        if self.asr_provider == "funasr":
            try:
                from funasr import AutoModel
                self.funasr_model = None
                funasr_model_name = os.environ.get("FUNASR_MODEL", "iic/SenseVoiceSmall")
                self.asr_model = funasr_model_name
                print(f"✅ 实时语音识别已就绪 (FunASR, model={funasr_model_name}, segment_seconds={self.segment_seconds})")
            except ImportError as e:
                print(f"⚠️  FunASR 未安装: {e}")
                if DASHSCOPE_ASR_AVAILABLE:
                    print("   回退到 DashScope 实时识别")
                    self.asr_provider = "qwen"
                else:
                    return
        
        # FireRedASR 支持
        elif self.asr_provider == "fireredasr":
            if not FIREREDASR_ASR_AVAILABLE:
                if DASHSCOPE_ASR_AVAILABLE:
                    print("⚠️  FireRedASR 未安装/不可导入,回退到 DashScope 实时识别")
                    if FIREREDASR_IMPORT_ERROR:
                        print("   🔎 FireRedASR 导入失败摘要(用于排查):")
                        for line in FIREREDASR_IMPORT_ERROR.strip().splitlines()[-6:]:
                            print(f"      {line}")
                    self.asr_provider = "qwen"
                else:
                    print("⚠️  FireRedASR 未安装/不可导入,实时语音识别不可用")
                    if FIREREDASR_IMPORT_ERROR:
                        print("   🔎 FireRedASR 导入失败摘要(用于排查):")
                        for line in FIREREDASR_IMPORT_ERROR.strip().splitlines()[-6:]:
                            print(f"      {line}")
                    return
            else:
                model_dir = os.environ.get("FIREREDASR_MODEL_DIR", "pretrained_models/FireRedASR-AED-L")
                self.asr_model_dir = str(model_dir)
                self.asr_type = os.environ.get("FIREREDASR_ASR_TYPE", "aed").strip().lower()
                self.asr_model = f"{self.asr_type}:{Path(model_dir).name}"
                if not Path(model_dir).exists():
                    if DASHSCOPE_ASR_AVAILABLE:
                        print(f"⚠️  FireRedASR 模型目录不存在: {model_dir}，回退到 DashScope 实时识别")
                        self.asr_provider = "qwen"
                    else:
                        print(f"⚠️  FireRedASR 模型目录不存在: {model_dir}")
                        return
                else:
                    print(f"✅ 实时语音识别已就绪 (FireRedASR 离线分段, segment_seconds={self.segment_seconds})")

        # DashScope 回退
        if self.asr_provider not in ("fireredasr", "funasr"):
            if not DASHSCOPE_ASR_AVAILABLE:
                print("⚠️  DashScope API Key未设置,实时语音识别不可用")
                return
            self.asr_model = "paraformer-realtime-v2"
            print("✅ 实时语音识别已就绪 (DashScope 流式)")
    
    def _on_complete(self):
        """识别完成回调"""
        print("🎤 识别会话结束")
    
    def _on_error(self, result):
        """识别错误回调 - 触发自动重连"""
        print(f"❌ 识别错误: {result}")
        # 标记连接失败，触发重连
        self.connection_failed = True
    
    def _on_event(self, result):
        """识别事件回调"""
        # 从output中获取sentence
        output = result.get('output', {})
        sentence = output.get('sentence', {})
        text = sentence.get('text', '').strip()
        
        if text:
            # 判断是否为最终结果: sentence_end=True 或 end_time不为None
            is_final = sentence.get('sentence_end', False) or sentence.get('end_time') is not None
            timestamp = time.time()
            
            with self.lock:
                if is_final:
                    # 最终结果
                    segment = TranscriptSegment(text, timestamp, is_final=True)
                    self.transcript_segments.append(segment)
                    print(f"\n📝 [句子完成] {text[:60]}{'...' if len(text) > 60 else ''}")
                    
                    # 调用外部回调
                    if self.on_transcript_update:
                        try:
                            self.on_transcript_update(text, is_final=True, timestamp=timestamp)
                        except Exception as e:
                            print(f"⚠️  回调错误: {e}")
                            import traceback
                            traceback.print_exc()
                else:
                    # 临时结果 - 更新当前文本并触发回调
                    self.current_text = text
                    
                    # 通知临时结果（用于实时更新UI）
                    if self.on_transcript_update:
                        try:
                            self.on_transcript_update(text, is_final=False, timestamp=timestamp)
                        except Exception as e:
                            pass  # 临时结果错误不打印
    
    def _on_audio(self, audio_data: bytes):
        """接收音频数据并发送到识别引擎"""
        if not self.is_recording or self.is_paused:
            return

        if self.asr_provider == "fireredasr":
            # FireRedASR 离线：先缓冲，由 worker 定时切片转写
            with self.lock:
                self._audio_segment_buffer.append(audio_data)
            return

        if self.recognition:
            try:
                self.recognition.send_audio_frame(audio_data)
            except Exception as e:
                error_msg = str(e).lower()
                # 检测连接错误
                if "stopped" in error_msg or "closing" in error_msg or "reset" in error_msg:
                    if not self.connection_failed:
                        print(f"⚠️  ASR连接中断: {e}")
                        self.connection_failed = True
                else:
                    print(f"⚠️  发送音频帧错误: {e}")

    def _get_fireredasr_model(self):
        if self._firered_model is not None:
            return self._firered_model

        asr_type = os.environ.get("FIREREDASR_ASR_TYPE", "aed").strip().lower()
        model_dir = os.environ.get("FIREREDASR_MODEL_DIR", "pretrained_models/FireRedASR-AED-L")

        try:
            try:
                from fireredasr.models.fireredasr import FireRedAsr
            except Exception:
                here = Path(__file__).parent
                candidates = [here / "FireRedASR", here / "vendor" / "FireRedASR"]
                for c in candidates:
                    if c.exists() and str(c) not in os.sys.path:
                        os.sys.path.insert(0, str(c))
                from fireredasr.models.fireredasr import FireRedAsr
        except Exception as e:
            raise ImportError(f"无法导入 FireRedASR: {e}") from e

        self._firered_model = FireRedAsr.from_pretrained(asr_type, model_dir)
        return self._firered_model

    def _get_funasr_model(self):
        """获取或创建FunASR模型（懒加载）"""
        if self.funasr_model is not None:
            return self.funasr_model

        funasr_model_name = os.environ.get("FUNASR_MODEL", "iic/SenseVoiceSmall")
        
        try:
            from funasr import AutoModel
            print(f"🔄 加载FunASR模型: {funasr_model_name} ...")
            self.funasr_model = AutoModel(
                model=funasr_model_name,
                device="cpu",  # 可改为"cuda"启用GPU
                disable_pbar=True,
                disable_log=True
            )
            print(f"✅ FunASR模型加载完成")
            return self.funasr_model
        except Exception as e:
            raise ImportError(f"无法加载 FunASR 模型 {funasr_model_name}: {e}") from e

    @staticmethod
    def _write_wav_16k_mono(path: str, pcm_bytes: bytes):
        wf = wave.open(path, 'wb')
        wf.setnchannels(1)
        wf.setsampwidth(2)  # int16
        wf.setframerate(16000)
        wf.writeframes(pcm_bytes)
        wf.close()

    @staticmethod
    def _rms_energy(pcm_bytes: bytes) -> float:
        if not pcm_bytes:
            return 0.0
        arr = np.frombuffer(pcm_bytes, dtype=np.int16)
        if arr.size == 0:
            return 0.0
        return float(np.sqrt(np.mean(arr.astype(np.float32) ** 2)))

    def _fireredasr_worker(self):
        """FireRedASR 离线分段转写线程"""
        try:
            # 注册音频监听器
            self.audio_listener = self.audio_manager.register_listener(
                "RealtimeASR(FireRed)",
                self._on_audio
            )

            next_flush = time.time() + self.segment_seconds
            first_run = True  # 首次运行标志，允许快速启动
            
            while self.is_recording:
                time.sleep(0.05)
                if self.is_paused:
                    continue

                now = time.time()
                # 首次运行或达到时间间隔时处理
                should_process = first_run or now >= next_flush
                
                if not should_process:
                    continue
                    
                # 首次运行等待至少1秒音频累积（约10个chunks）
                if first_run:
                    with self.lock:
                        buffer_duration = len(self._audio_segment_buffer) * 0.1  # 每chunk=3200字节=0.1秒
                        if buffer_duration < 1.0:
                            continue
                    first_run = False
                    print(f"🎤 [实时ASR] 首次处理启动，累积 {buffer_duration:.1f}秒 音频")
                    
                next_flush = now + self.segment_seconds

                with self.lock:
                    if not self._audio_segment_buffer:
                        continue
                    chunks = list(self._audio_segment_buffer)
                    buffer_duration = len(chunks) * 0.1  # 每chunk=3200字节=0.1秒
                    self._audio_segment_buffer.clear()
                
                # 记录音频段的中间时刻（回溯半个buffer时长）
                audio_timestamp = now - (buffer_duration / 2.0)

                pcm = b"".join(chunks)
                # 简单能量门限：过滤纯静音段，减少误触发
                if self._rms_energy(pcm) < 200.0:
                    continue

                tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                tmp_path = tmp.name
                tmp.close()
                try:
                    self._write_wav_16k_mono(tmp_path, pcm)
                    model = self._get_fireredasr_model()
                    use_gpu = os.environ.get("FIREREDASR_USE_GPU", "0").strip() in {"1", "true", "yes"}
                    beam_size = int(os.environ.get("FIREREDASR_BEAM_SIZE", "1"))  # 默认1提速（原3）
                    nbest = int(os.environ.get("FIREREDASR_NBEST", "1"))
                    decode_conf = {"use_gpu": 1 if use_gpu else 0, "beam_size": beam_size, "nbest": nbest}
                    
                    # 记录识别耗时
                    infer_start = time.time()
                    results = model.transcribe(["utt1"], [tmp_path], decode_conf)
                    infer_time = time.time() - infer_start
                    text = ""
                    if results:
                        text = (results[0].get("text") or "").strip()

                    if not text:
                        continue
                    # 去重：连续相同文本不重复入队
                    if text == self._firered_last_text:
                        continue
                    self._firered_last_text = text
                    
                    print(f"🎤 [实时ASR] 识别到新片段: {text} (耗时: {infer_time:.2f}秒)")

                    # 使用音频采集时间而非识别完成时间
                    seg = TranscriptSegment(text, audio_timestamp, is_final=True)
                    with self.lock:
                        self.transcript_segments.append(seg)

                    if self.on_transcript_update:
                        try:
                            self.on_transcript_update(text, is_final=True, timestamp=audio_timestamp)
                        except Exception:
                            pass
                finally:
                    try:
                        os.unlink(tmp_path)
                    except Exception:
                        pass

        except Exception as e:
            print(f"❌ FireRedASR 实时转写错误: {e}")
        finally:
            if self.audio_listener:
                try:
                    self.audio_manager.unregister_listener(self.audio_listener)
                except Exception:
                    pass
                self.audio_listener = None

    def _funasr_worker(self):
        """FunASR 离线分段转写线程"""
        try:
            # 注册音频监听器
            self.audio_listener = self.audio_manager.register_listener(
                "RealtimeASR(FunASR)",
                self._on_audio
            )

            next_flush = time.time() + self.segment_seconds
            first_run = True
            
            while self.is_recording:
                time.sleep(0.05)
                if self.is_paused:
                    continue

                now = time.time()
                should_process = first_run or now >= next_flush
                
                if not should_process:
                    continue
                    
                if first_run:
                    with self.lock:
                        buffer_duration = len(self._audio_segment_buffer) * 0.1
                        if buffer_duration < 1.0:
                            continue
                    first_run = False
                    print(f"🎤 [实时ASR] 首次处理启动，累积 {buffer_duration:.1f}秒 音频")
                    
                next_flush = now + self.segment_seconds

                with self.lock:
                    if not self._audio_segment_buffer:
                        continue
                    chunks = list(self._audio_segment_buffer)
                    buffer_duration = len(chunks) * 0.1
                    self._audio_segment_buffer.clear()
                
                audio_timestamp = now - (buffer_duration / 2.0)

                pcm = b"".join(chunks)
                if self._rms_energy(pcm) < 200.0:
                    continue

                # 转换为numpy数组
                import numpy as np
                audio_np = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0

                try:
                    model = self._get_funasr_model()
                    infer_start = time.time()
                    
                    # FunASR识别（支持直接输入numpy数组）
                    result = model.generate(input=audio_np, cache={}, language="auto", use_itn=True)
                    infer_time = time.time() - infer_start
                    
                    text = ""
                    if result and len(result) > 0:
                        text = result[0].get("text", "").strip()

                    if not text:
                        continue
                    
                    if text == self._funasr_last_text:
                        continue
                    self._funasr_last_text = text
                    
                    print(f"🎤 [实时ASR] 识别到新片段: {text} (耗时: {infer_time:.2f}秒)")

                    seg = TranscriptSegment(text, audio_timestamp, is_final=True)
                    with self.lock:
                        self.transcript_segments.append(seg)

                    if self.on_transcript_update:
                        try:
                            self.on_transcript_update(text, is_final=True, timestamp=audio_timestamp)
                        except Exception:
                            pass

                except Exception as e:
                    print(f"⚠️  FunASR 识别错误: {e}")
                    import traceback
                    traceback.print_exc()

        except Exception as e:
            print(f"❌ FunASR 实时转写错误: {e}")
        finally:
            if self.audio_listener:
                try:
                    self.audio_manager.unregister_listener(self.audio_listener)
                except Exception:
                    pass
                self.audio_listener = None
    
    def _recognition_worker(self):
        """识别工作线程 - 流式模式（带自动重连）"""
        
        while self.is_recording:
            try:
                print(f"🎤 启动流式语音识别... (尝试 {self.reconnect_attempts + 1}/{self.max_reconnect_attempts + 1})")
                
                # 创建识别回调 (DashScope API不需要参数)
                callback = RecognitionCallback()
                callback.on_complete = self._on_complete
                callback.on_error = self._on_error
                callback.on_event = self._on_event
                
                # 创建流式识别对象
                self.recognition = Recognition(
                    model='paraformer-realtime-v2',
                    format='pcm',
                    sample_rate=16000,
                    callback=callback
                )
                
                # 启动识别
                self.recognition.start()
                print("✅ 流式识别已启动")
                
                # 注册音频监听器
                if not self.audio_listener:
                    self.audio_listener = self.audio_manager.register_listener(
                        "RealtimeASR",
                        self._on_audio
                    )
                    print("✅ 音频采集已启动")
                
                # 重置连接状态
                self.connection_failed = False
                self.reconnect_attempts = 0
                
                # 保持线程运行，监控连接状态
                while self.is_recording and not self.connection_failed:
                    time.sleep(0.5)
                
                # 检查是否需要重连
                if self.connection_failed and self.is_recording:
                    print(f"🔄 检测到连接中断，准备重连...")
                    
                    # 清理当前连接
                    if self.recognition:
                        try:
                            self.recognition.stop()
                        except:
                            pass
                        self.recognition = None
                    
                    # 检查重连次数
                    if self.reconnect_attempts >= self.max_reconnect_attempts:
                        print(f"❌ 重连失败次数过多({self.max_reconnect_attempts}次)，停止ASR")
                        self.is_recording = False
                        break
                    
                    # 指数退避延迟
                    delay = self.reconnect_delay * (2 ** self.reconnect_attempts)
                    print(f"⏱️  等待 {delay:.1f} 秒后重连...")
                    time.sleep(delay)
                    
                    self.reconnect_attempts += 1
                    continue  # 重新开始循环，尝试重连
                else:
                    # 正常停止
                    break
                    
            except Exception as e:
                print(f"❌ 识别错误: {e}")
                import traceback
                traceback.print_exc()
                
                # 清理
                if self.recognition:
                    try:
                        self.recognition.stop()
                    except:
                        pass
                    self.recognition = None
                
                # 判断是否重连
                if self.reconnect_attempts < self.max_reconnect_attempts and self.is_recording:
                    delay = self.reconnect_delay * (2 ** self.reconnect_attempts)
                    print(f"⏱️  {delay:.1f} 秒后自动重连...")
                    time.sleep(delay)
                    self.reconnect_attempts += 1
                    continue
                else:
                    break
        
        # 最终清理
        if self.recognition:
            try:
                self.recognition.stop()
            except:
                pass
        
        # 取消注册音频监听器
        if self.audio_listener:
            try:
                self.audio_manager.unregister_listener(self.audio_listener)
                self.audio_listener = None
            except:
                pass
        
        print("🛑 识别已停止")
    
    def start_recording(self):
        """开始录制和转录"""
        if not PYAUDIO_AVAILABLE:
            print("⚠️  实时语音识别依赖不完整")
            return False

        # 检查ASR依赖
        if self.asr_provider == "fireredasr":
            if not FIREREDASR_ASR_AVAILABLE:
                print("⚠️  实时语音识别依赖不完整")
                return False
        elif self.asr_provider == "funasr":
            try:
                from funasr import AutoModel
            except ImportError:
                print("⚠️  FunASR未安装")
                return False
        elif self.asr_provider != "funasr":  # DashScope
            if not DASHSCOPE_ASR_AVAILABLE:
                print("⚠️  实时语音识别依赖不完整")
                return False
        
        if self.is_recording:
            print("⚠️  已在录制中")
            return False
        
        self.is_recording = True
        
        # 根据ASR提供商选择worker线程
        if self.asr_provider == "fireredasr":
            self.recognition_thread = threading.Thread(target=self._fireredasr_worker, daemon=True)
        elif self.asr_provider == "funasr":
            self.recognition_thread = threading.Thread(target=self._funasr_worker, daemon=True)
        else:  # DashScope
            self.recognition_thread = threading.Thread(target=self._recognition_worker, daemon=True)
        
        self.recognition_thread.start()
        return True
    
    def start(self):
        """开始录制和转录 (别名)"""
        return self.start_recording()
    
    def stop_recording(self):
        """停止录制"""
        if not self.is_recording:
            return
        
        self.is_recording = False
        
        if self.recognition_thread:
            self.recognition_thread.join(timeout=3)
        
        # 保存转录结果
        self._save_transcript()
        
        print("✅ 语音识别已停止")

    def stop(self):
        """停止 (别名)"""
        self.stop_recording()

    def pause(self):
        """暂停录音/转写"""
        self.is_paused = True

    def resume(self):
        """恢复录音/转写"""
        self.is_paused = False

    def clear_transcript(self):
        """清空转写缓存"""
        with self.lock:
            self.transcript_segments.clear()
            self.current_text = ""
            self._firered_last_text = ""
            self._audio_segment_buffer.clear()
    
    def _save_transcript(self):
        """保存转录结果到文件"""
        if not self.transcript_segments:
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = self.output_dir / f"transcript_{timestamp}.txt"
        
        with self.lock:
            with open(filepath, 'w', encoding='utf-8') as f:
                for seg in self.transcript_segments:
                    f.write(f"[{datetime.fromtimestamp(seg.timestamp).strftime('%H:%M:%S')}] {seg.text}\n")
        
        print(f"💾 转录已保存: {filepath}")
    
    def get_recent_transcript(self, duration_seconds=10):
        """
        获取最近的转录文本
        
        Args:
            duration_seconds: 获取最近N秒的转录
            
        Returns:
            转录文本字符串
        """
        current_time = time.time()
        cutoff_time = current_time - duration_seconds
        
        with self.lock:
            recent_segments = [
                seg.text for seg in self.transcript_segments
                if seg.timestamp >= cutoff_time and seg.is_final
            ]
            
            if recent_segments:
                return "\n".join(recent_segments)
            
            # 如果没有最终结果,返回当前正在识别的文本
            return self.current_text if self.current_text else ""
    
    def get_full_transcript(self):
        """获取完整转录文本"""
        with self.lock:
            return "\n".join([seg.text for seg in self.transcript_segments if seg.is_final])
    
    def get_all_segments(self):
        """获取所有转录片段"""
        with self.lock:
            return list(self.transcript_segments)
    
    def get_status(self):
        """获取识别状态"""
        with self.lock:
            segment_count = len(self.transcript_segments)

        if self.asr_provider == "fireredasr":
            available = PYAUDIO_AVAILABLE and FIREREDASR_ASR_AVAILABLE
        else:
            available = PYAUDIO_AVAILABLE and DASHSCOPE_ASR_AVAILABLE

        return {
            "is_recording": self.is_recording,
            "available": available,
            "segment_count": segment_count,
            "current_text": self.current_text,
            "provider": self.asr_provider,
            "model": self.asr_model,
            "model_dir": self.asr_model_dir,
            "asr_type": self.asr_type,
            "is_paused": self.is_paused,
            "message": "运行中" if self.is_recording else "就绪"
        }


# 全局实例(可选)
_global_asr = None


def get_realtime_asr(output_dir=None):
    """获取全局ASR实例"""
    global _global_asr
    if _global_asr is None:
        _global_asr = RealtimeASR(output_dir=output_dir)
    return _global_asr


if __name__ == "__main__":
    # 测试代码
    asr = RealtimeASR()
    asr.start_recording()
    time.sleep(2)
    print("状态:", asr.get_status())
    asr.stop_recording()
