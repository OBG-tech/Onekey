#!/usr/bin/env python3
"""
🎬 智能视频分析与人脸追踪整合系统
结合 ONE_KEY 的智能分析 + multi_person_tracker 的实时追踪
支持: 本地视频、摄像头、OBS实时流
"""

print("⏳ 系统启动中...", end="\r")

import cv2
import os
import sys
import json
import threading
import time
import argparse
import webbrowser
import re
from pathlib import Path
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from socketserver import ThreadingMixIn
from collections import defaultdict
import numpy as np

print("⏳ 加载核心模块...", end="\r")

# YOLO人物检测 (延迟导入,只在使用时加载模型)
from ultralytics import YOLO

# 可选: InsightFace人脸识别 - 禁用以使用纯YOLO追踪模式
INSIGHTFACE_AVAILABLE = False
FaceAnalysis = None
# try:
#     # 延迟导入,只在需要时加载
#     import insightface
#     INSIGHTFACE_AVAILABLE = True
#     print("✅ InsightFace 人脸识别可用")
# except (ImportError, Exception) as e:
#     INSIGHTFACE_AVAILABLE = False
#     print(f"⚠️  InsightFace 不可用: {e}")
print("💡 使用纯YOLO追踪模式 (InsightFace已禁用)")

# ============================================================
# 🎤 ASR 后端选择 (Qwen/DashScope vs FireRedASR)
# ============================================================

# ASR_PROVIDER:
# - qwen: 使用 DashScope/Qwen 语音能力 (通义千问云端实时ASR，推荐)
# - funasr: 使用 FunASR 离线识别 (需手动安装模型)
# - fireredasr: 使用本地 FireRedASR-AED (离线推理，不走云，CPU模式较慢)
# 默认使用通义千问云端实时ASR（速度快、准确率高、自动标点）
ASR_PROVIDER = os.environ.get("ASR_PROVIDER", "qwen").strip().lower()

# FireRedASR 配置（仅当 ASR_PROVIDER=fireredasr 时生效）
FIREREDASR_MODEL_DIR = os.environ.get("FIREREDASR_MODEL_DIR", "pretrained_models/FireRedASR-AED-L")
FIREREDASR_ASR_TYPE = os.environ.get("FIREREDASR_ASR_TYPE", "aed").strip().lower()  # aed | llm
FIREREDASR_USE_GPU = os.environ.get("FIREREDASR_USE_GPU", "0").strip() in {"1", "true", "yes"}
FIREREDASR_BEAM_SIZE = int(os.environ.get("FIREREDASR_BEAM_SIZE", "3"))
FIREREDASR_NBEST = int(os.environ.get("FIREREDASR_NBEST", "1"))

_fireredasr_model_cache = None

def _get_fireredasr_model():
    """延迟加载 FireRedASR 模型（单例缓存）"""
    global _fireredasr_model_cache
    if _fireredasr_model_cache is not None:
        return _fireredasr_model_cache
    try:
        from fireredasr.models.fireredasr import FireRedAsr
    except Exception:
        # 兼容：项目根目录内直接 git clone FireRedASR（不做 pip install）
        project_dir = Path(__file__).parent
        candidates = [project_dir / "FireRedASR", project_dir / "vendor" / "FireRedASR"]
        for c in candidates:
            if c.exists() and str(c) not in sys.path:
                sys.path.insert(0, str(c))
        try:
            from fireredasr.models.fireredasr import FireRedAsr
        except Exception as e:
            raise ImportError(
                "未安装 fireredasr（FireRedASR）。\n"
                "参考: https://github.com/FireRedTeam/FireRedASR\n"
                "快速接入方式（二选一）：\n"
                "1) 直接在本项目目录下执行: git clone https://github.com/FireRedTeam/FireRedASR.git\n"
                "   然后设置 FIREREDASR_MODEL_DIR 指向权重目录；\n"
                "2) 按 FireRedASR README 创建其环境并安装依赖。\n"
                f"原始错误: {e}"
            ) from e

    model_dir = FIREREDASR_MODEL_DIR
    if not os.path.exists(model_dir):
        raise FileNotFoundError(
            f"FireRedASR 模型目录不存在: {model_dir}\n"
            "请先从 HuggingFace 下载权重并放到该目录，例如 FireRedTeam/FireRedASR-AED-L"
        )

    _fireredasr_model_cache = FireRedAsr.from_pretrained(FIREREDASR_ASR_TYPE, model_dir)
    print(f"✅ FireRedASR 已加载: type={FIREREDASR_ASR_TYPE}, dir={model_dir}, gpu={FIREREDASR_USE_GPU}")
    return _fireredasr_model_cache

def transcribe_audio_with_fireredasr(wav_path: str) -> str:
    """使用 FireRedASR-AED 本地转写。

    说明：FireRedASR 的推理通常要求 16kHz/mono 的 WAV。
    为兼容浏览器上传的 webm / 其他音频格式，这里会在必要时自动转码。
    """

    import subprocess
    import tempfile

    def _convert_to_wav_16k_mono(src_path: str) -> str | None:
        suffix = Path(src_path).suffix.lower()
        if suffix == ".wav":
            return src_path

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp.close()
        dst_path = tmp.name

        cmd = [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-i",
            src_path,
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "16000",
            "-ac",
            "1",
            dst_path,
        ]
        try:
            result = subprocess.run(cmd, capture_output=True, timeout=60)
            if result.returncode != 0 or not os.path.exists(dst_path):
                try:
                    os.unlink(dst_path)
                except Exception:
                    pass
                return None
            return dst_path
        except Exception:
            try:
                os.unlink(dst_path)
            except Exception:
                pass
            return None

    converted_path: str | None = None
    try:
        converted_path = _convert_to_wav_16k_mono(wav_path)
        if not converted_path:
            print("⚠️ FireRedASR 需要 WAV(16k/mono)，且 ffmpeg 转码失败")
            return ""

        model = _get_fireredasr_model()
        decode_conf = {
            "use_gpu": 1 if FIREREDASR_USE_GPU else 0,
            "beam_size": FIREREDASR_BEAM_SIZE,
            "nbest": FIREREDASR_NBEST,
        }
        results = model.transcribe(["utt1"], [converted_path], decode_conf)
        if not results:
            return ""
        text = (results[0].get("text") or "").strip()
        return text
    except Exception as e:
        print(f"⚠️ FireRedASR 转写失败: {e}")
        return ""
    finally:
        try:
            if converted_path and converted_path != wav_path and os.path.exists(converted_path):
                os.unlink(converted_path)
        except Exception:
            pass

def transcribe_audio(audio_path: str) -> str:
    """统一转写入口：根据 ASR_PROVIDER 选择后端。"""
    if ASR_PROVIDER == "fireredasr":
        text = transcribe_audio_with_fireredasr(audio_path)
        if text and text.strip():
            return text
        # FireRedASR 不可用/失败时，允许回退到云端（若用户已配置）
        return transcribe_audio_with_qwen(audio_path)
    return transcribe_audio_with_qwen(audio_path)

# 可选: AI分析功能 (支持 Qwen 和 Claude)
ONEKEY_AI_AVAILABLE = False
QWEN_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
CLAUDE_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "") or os.environ.get("CLAUDE_API_KEY", "")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "qwen").lower()

try:
    if LLM_PROVIDER.startswith("claude"):
        # Claude provider
        try:
            from anthropic import Anthropic
            if CLAUDE_API_KEY:
                ONEKEY_AI_AVAILABLE = True
                print("✅ Claude Haiku 4.5 API 可用")
            else:
                print("⚠️  未设置 ANTHROPIC_API_KEY 环境变量，AI分析功能不可用")
        except ImportError:
            print("⚠️  Anthropic库未安装（pip install anthropic），AI分析功能不可用")
    else:
        # Qwen provider (default)
        from openai import OpenAI
        if QWEN_API_KEY:
            ONEKEY_AI_AVAILABLE = True
            print("✅ Qwen API 可用")
        else:
            print("⚠️  未设置 DASHSCOPE_API_KEY 环境变量，AI分析功能不可用")
except ImportError:
    print("⚠️  OpenAI库未安装，AI分析功能不可用")

# 🎯 双轨关键时刻识别系统
try:
    from key_moments_manager import KeyMomentsManager
    KEY_MOMENTS_AVAILABLE = True
    print("✅ 关键时刻管理器可用")
except ImportError:
    KEY_MOMENTS_AVAILABLE = False
    print("⚠️  关键时刻管理器未安装")

# 🎤 实时语音识别系统
REALTIME_ASR_AVAILABLE = False
realtime_asr_engine = None
PYAUDIO_AVAILABLE = False
DASHSCOPE_ASR_AVAILABLE = False
FIREREDASR_ASR_AVAILABLE = False

try:
    from realtime_asr import RealtimeASR, PYAUDIO_AVAILABLE, DASHSCOPE_ASR_AVAILABLE, FIREREDASR_ASR_AVAILABLE
    if PYAUDIO_AVAILABLE and (DASHSCOPE_ASR_AVAILABLE or FIREREDASR_ASR_AVAILABLE):
        REALTIME_ASR_AVAILABLE = True
        print("✅ 实时语音识别可用")
    else:
        print("⚠️  实时语音识别依赖不完整")
except (ImportError, Exception) as e:
    print(f"⚠️  实时语音识别模块导入失败: {e}")

# 🎤 麦克风录制系统
MICROPHONE_AVAILABLE = False
microphone_recorder = None

try:
    from microphone_recorder import MicrophoneRecorder
    MICROPHONE_AVAILABLE = True
    print("✅ 麦克风录制可用")
except (ImportError, Exception) as e:
    print(f"⚠️  麦克风录制模块导入失败: {e}")

# 📝 AI会议纪要系统
MEETING_NOTES_AVAILABLE = False
meeting_notes_generator = None

try:
    from meeting_notes import MeetingNotesGenerator
    MEETING_NOTES_AVAILABLE = True
    print("✅ AI会议纪要生成器可用")
except (ImportError, Exception) as e:
    print(f"⚠️  AI会议纪要模块导入失败: {e}")

# 🎬 AI直播间系统
AI_LIVE_AVAILABLE = False
ai_live_commentary = None

try:
    from ai_live_commentary import AILiveCommentary
    AI_LIVE_AVAILABLE = True
    print("✅ AI直播间可用")
except (ImportError, Exception) as e:
    print(f"⚠️  AI直播间模块导入失败: {e}")

# ============================================================
# 📡 配置项
# ============================================================

# 追踪配置
MODEL_PATH = os.path.expanduser("~/tracker_cache/yolo11n.pt")
if not os.path.exists(MODEL_PATH):
    MODEL_PATH = "models/yolo11n.pt"

# 人脸识别配置
FACE_MATCH_THRESHOLD = 0.40
MIN_FACE_SIZE = 40
MIN_FACE_QUALITY = 0.3
SAMPLE_INTERVAL = 2  # 每2秒采样一次人脸和保存图像
KEYFRAME_INTERVAL = 30  # 每30秒保存一次关键帧

# 显示配置
DISPLAY_FRAME_SKIP = 2
MAX_TRAJECTORY_LENGTH = 30

# 颜色池 (BGR格式)
COLOR_POOL = [
    (147, 20, 255),   # 深粉色
    (0, 215, 255),    # 金色
    (255, 144, 30),   # 道奇蓝
    (180, 105, 255),  # 热粉色
    (0, 255, 127),    # 春绿色
    (203, 192, 255),  # 粉紫色
    (19, 69, 139),    # 马鞍棕
    (255, 191, 0),    # 深天蓝
    (42, 42, 165),    # 棕色
    (147, 112, 219),  # 中紫色
]

# 目录配置
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "integrated_data"
FACE_DB_PATH = DATA_DIR / "face_database"
ANALYSIS_PATH = DATA_DIR / "analysis_results"
LOGS_PATH = DATA_DIR / "logs"
ANALYSIS_LOG_FILE = LOGS_PATH / "analysis.log"
KEYFRAME_PATH = DATA_DIR / "key_frames"
SNAPSHOT_PATH = DATA_DIR / "snapshots"
KEY_MOMENTS_PATH = DATA_DIR / "key_moments"  # 关键时刻目录

# 创建必要目录
for path in [DATA_DIR, FACE_DB_PATH, ANALYSIS_PATH, KEYFRAME_PATH, SNAPSHOT_PATH, KEY_MOMENTS_PATH, LOGS_PATH]:
    path.mkdir(exist_ok=True, parents=True)

# ============================================================
# 🌐 全局状态
# ============================================================

is_running = True
current_frame_jpeg = None  # 存储当前帧的 JPEG 数据用于视频流
current_frame_seq = 0  # 每次更新帧+1，用于避免MJPEG重复发送同一帧
current_frame_raw = None   # 存储原始帧用于关键时刻标记
frame_lock = threading.Lock()  # 线程锁

# 🎬 视频切片缓冲区 (用于多模态 AI 分析)
# 结构: [{"ts": epoch_seconds, "frame_number": int, "frame": np.ndarray}, ...]
# 重要：不能只存 30 帧，否则在 30fps/每10帧采样=3fps 的情况下只覆盖≈10秒，
# 会导致“切片分析挑到的时间点”在视频里只剩几秒、甚至完全不对应。
video_slice_buffer = []

# 默认：5fps 采样、3.5分钟=1050帧；为了控制内存，存储降分辨率帧
VIDEO_SLICE_SECONDS = float(os.environ.get("MULTIMODAL_SLICE_SECONDS", "210"))
VIDEO_SLICE_FPS = float(os.environ.get("MULTIMODAL_SLICE_FPS", "5"))  # 提高到5fps，生成更流畅的30秒视频
VIDEO_SLICE_FRAME_WIDTH = int(os.environ.get("MULTIMODAL_SLICE_FRAME_WIDTH", "320"))
if VIDEO_SLICE_FPS < 0.2:
    VIDEO_SLICE_FPS = 0.2
video_slice_max_frames = int(VIDEO_SLICE_SECONDS * VIDEO_SLICE_FPS) + 5
video_slice_start_time = time.time()

current_stats = {
    "frame_count": 0,
    "person_count": 0,
    "track_ids": [],
    "fps": 0,
    "status": "starting",
    "known_people": 0,
    "face_detections": 0,
    "stream_mode": "none",  # none, camera, video, obs
    "ai_analysis_enabled": False,
    "keyframe_count": 0,
    "key_moments_count": 0,     # 关键时刻总数
    "user_anchors_count": 0,    # 用户标记数
    "ai_detected_count": 0      # AI识别数
}

track_trajectories = {}

# 🎯 关键时刻管理器实例
key_moments_manager = None

# ============================================================
# 🎨 人脸数据库
# ============================================================

class FaceDatabase:
    """管理人脸特征向量和ID映射"""
    def __init__(self):
        self.face_embeddings = []
        self.person_ids = []
        self.person_names = {}
        self.person_images = {}
        self.detection_history = defaultdict(list)
        self.next_person_id = 1
        # 🔄 当前会话活跃人物 (每次启动时清空)
        self.active_people_this_session = set()  # 只记录本次会话出现的 person_id
        
        # 🎯 人物重识别系统 (Re-ID)
        self.person_features = {}  # person_id -> 特征向量列表
        self.track_to_person_map = {}  # track_id -> person_id 映射
        self.person_appearance_history = defaultdict(list)  # person_id -> [track_ids]
    
    def extract_simple_features(self, image):
        """提取简单的视觉特征用于Re-ID (颜色直方图 + HOG)"""
        if image is None or image.size == 0:
            return None
        
        try:
            # 调整大小以加快处理速度
            img_resized = cv2.resize(image, (128, 256))
            
            # 1. 颜色直方图 (HSV空间,上下半身分开)
            hsv = cv2.cvtColor(img_resized, cv2.COLOR_BGR2HSV)
            h, w = hsv.shape[:2]
            
            # 上半身 (可能是衣服)
            upper_hist = cv2.calcHist([hsv[:h//2]], [0, 1], None, [30, 32], [0, 180, 0, 256])
            upper_hist = cv2.normalize(upper_hist, upper_hist).flatten()
            
            # 下半身 (可能是裤子)
            lower_hist = cv2.calcHist([hsv[h//2:]], [0, 1], None, [30, 32], [0, 180, 0, 256])
            lower_hist = cv2.normalize(lower_hist, lower_hist).flatten()
            
            # 2. 简单的纹理特征 (边缘密度)
            gray = cv2.cvtColor(img_resized, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            edge_density = np.sum(edges > 0) / edges.size
            
            # 3. 整体亮度
            brightness = np.mean(gray) / 255.0
            
            # 合并特征
            feature = np.concatenate([
                upper_hist * 0.5,  # 上半身颜色权重更高
                lower_hist * 0.3,
                [edge_density, brightness]
            ])
            
            # L2归一化
            feature = feature / (np.linalg.norm(feature) + 1e-6)
            
            return feature
        except Exception as e:
            print(f"⚠️ 特征提取失败: {e}")
            return None
    
    def find_matching_person(self, image, threshold=0.65):
        """通过视觉特征查找匹配的person_id"""
        feature = self.extract_simple_features(image)
        if feature is None:
            return None
        
        best_match_id = None
        best_similarity = 0
        
        for person_id, feature_list in self.person_features.items():
            if len(feature_list) == 0:
                continue
            
            # 计算与该人物所有特征的相似度
            similarities = [np.dot(feature, f) for f in feature_list]
            max_sim = max(similarities)
            
            if max_sim > best_similarity:
                best_similarity = max_sim
                best_match_id = person_id
        
        if best_similarity >= threshold:
            return best_match_id
        
        return None
    
    def add_person_feature(self, person_id, image):
        """为person添加新的特征向量"""
        feature = self.extract_simple_features(image)
        if feature is not None:
            if person_id not in self.person_features:
                self.person_features[person_id] = []
            
            # 保持每个人最多5个特征向量(取不同角度/光照)
            self.person_features[person_id].append(feature)
            if len(self.person_features[person_id]) > 5:
                self.person_features[person_id].pop(0)
    
    def map_track_to_person(self, track_id, person_id):
        """建立track_id到person_id的映射"""
        self.track_to_person_map[track_id] = person_id
        if track_id not in self.person_appearance_history[person_id]:
            self.person_appearance_history[person_id].append(track_id)
    
    def load_from_disk(self):
        """从磁盘加载已有的人脸图片"""
        try:
            FACE_DB_PATH.mkdir(parents=True, exist_ok=True)
            
            # 扫描 face_database 目录中的所有图片
            image_files = sorted(FACE_DB_PATH.glob("person_*.jpg"))
            
            for img_path in image_files:
                # 从文件名提取 person_id: person_3.jpg -> 3
                filename = img_path.stem  # 'person_3'
                person_id = int(filename.split('_')[1])
                
                # 注册图片路径
                self.person_images[person_id] = str(img_path)
                
                # 注册默认名称
                if person_id not in self.person_names:
                    self.person_names[person_id] = f"Person_{person_id}"
                
                # 更新 next_person_id
                if person_id >= self.next_person_id:
                    self.next_person_id = person_id + 1
            
            if len(self.person_images) > 0:
                print(f"✅ 已加载 {len(self.person_images)} 个人脸图片")
        except Exception as e:
            print(f"⚠️ 加载人脸图片失败: {e}")
    
    def find_match(self, embedding, threshold=FACE_MATCH_THRESHOLD):
        """查找匹配的人脸"""
        if len(self.face_embeddings) == 0:
            return None
        
        # 计算相似度
        similarities = [np.dot(embedding, emb) for emb in self.face_embeddings]
        max_sim = max(similarities)
        
        if max_sim > threshold:
            max_idx = similarities.index(max_sim)
            return self.person_ids[max_idx]
        return None
    
    def add_face(self, embedding, person_id=None, frame_image=None):
        """添加新人脸"""
        if person_id is None:
            person_id = self.next_person_id
            self.next_person_id += 1
            self.person_names[person_id] = f"Person_{person_id}"
        
        self.face_embeddings.append(embedding)
        self.person_ids.append(person_id)
        
        # 保存人脸图片
        if frame_image is not None:
            img_path = FACE_DB_PATH / f"person_{person_id}.jpg"
            cv2.imwrite(str(img_path), frame_image)
            self.person_images[person_id] = str(img_path)
        
        return person_id
    
    def record_detection(self, person_id, frame_num, bbox, snapshot=None):
        """记录检测历史"""
        detection = {
            "frame": frame_num,
            "bbox": bbox,
            "timestamp": datetime.now().strftime("%H:%M:%S")
        }
        
        if snapshot is not None:
            snapshot_dir = SNAPSHOT_PATH / f"person_{person_id}"
            snapshot_dir.mkdir(exist_ok=True)
            snapshot_path = snapshot_dir / f"frame_{frame_num}.jpg"
            cv2.imwrite(str(snapshot_path), snapshot)
            detection["snapshot"] = str(snapshot_path)
        
        self.detection_history[person_id].append(detection)
    
    def get_person_count(self):
        return len(set(self.person_ids))

    def delete_person(self, person_id):
        """删除人物及其所有数据"""
        # 删除人脸特征
        indices_to_remove = [i for i, pid in enumerate(self.person_ids) if pid == person_id]
        for idx in sorted(indices_to_remove, reverse=True):
            self.face_embeddings.pop(idx)
            self.person_ids.pop(idx)
        
        # 删除人脸图片
        if person_id in self.person_images:
            img_path = Path(self.person_images[person_id])
            if img_path.exists():
                img_path.unlink()
            del self.person_images[person_id]
        
        # 删除人物名称
        if person_id in self.person_names:
            del self.person_names[person_id]
        
        # 删除检测历史
        if person_id in self.detection_history:
            # 删除快照
            snapshot_dir = SNAPSHOT_PATH / f"person_{person_id}"
            if snapshot_dir.exists():
                import shutil
                shutil.rmtree(snapshot_dir)
            del self.detection_history[person_id]
        
        print(f"✅ 已删除人物 {person_id} 的所有数据")

face_db = FaceDatabase()
face_db.load_from_disk()  # 启动时加载已有的人脸图片

# ============================================================
# 🖥️  HTTP服务器 - 复古像素风格API
# ============================================================

class IntegratedHandler(SimpleHTTPRequestHandler):
    """处理API请求和静态文件"""
    
    def log_message(self, format, *args):
        """重写日志方法，只显示非API请求和错误"""
        # 过滤掉常见的API轮询请求（仅当args[0]是字符串时）
        if args and isinstance(args[0], str):
            if any(api in args[0] for api in ['/api/stats', '/api/people', '/api/key_moments', 
                                              '/api/realtime_asr/transcript', '/api/realtime_asr/status',
                                              '/api/meeting_notes/current', '/api/video_feed',
                                              '/api/face/', '/api/key_moment_image/', '/api/linkography',
                                              '/api/button_log']):
                return  # 静默这些高频API请求
        # 显示其他请求（如标记关键时刻、启动ASR等）和错误
        super().log_message(format, *args)
    
    def do_GET(self):
        global is_running

        # 兼容带 query 的请求（例如 /api/video_feed?t=...）
        # 仅用 path 做路由匹配；同时将 self.path 归一化，避免静态文件解析把 ? 当作文件名
        try:
            from urllib.parse import urlparse
            parsed = urlparse(self.path)
            # 保留 query，供需要参数的 API 使用
            self._query_string = parsed.query or ""
            self.path = parsed.path
        except Exception:
            self._query_string = ""
        
        if self.path == '/api/stats':
            self.send_json_response(self._get_stats())
            
        elif self.path == '/api/stop':
            self._handle_stop()
            
        elif self.path == '/api/start':
            # 重新启动需要重新运行脚本
            self.send_json_response({
                "status": "info",
                "message": "Please restart the script to start tracking again.",
                "command": "cd ~/onekey && source .venv/bin/activate && python3 integrated_system.py --camera 0 --no-window"
            })
            
        elif self.path == '/api/restart':
            # 返回重启命令，客户端可以用它来重启
            import subprocess
            self.send_json_response({
                "status": "restarting",
                "message": "Restarting system..."
            })
            # 异步重启
            def do_restart():
                time.sleep(1)
                os.execv(sys.executable, [sys.executable] + sys.argv)
            threading.Thread(target=do_restart, daemon=True).start()
            
        elif self.path == '/api/video_feed':
            self._serve_video_stream()
        
        elif self.path == '/api/video_source_info':
            self._serve_video_source_info()
        
        elif self.path.startswith('/api/video_source_file'):
            self._serve_video_source_file()
            
        elif self.path == '/api/people':
            self.send_json_response(self._get_people())
            
        elif self.path.startswith('/api/face/'):
            self._serve_face_image()
            
        elif self.path.startswith('/api/timeline/'):
            self.send_json_response(self._get_timeline())
            
        elif self.path.startswith('/api/frame/'):
            self._serve_frame_image()
            
        elif self.path == '/api/keyframes':
            self.send_json_response(self._get_keyframes())
            
        elif self.path.startswith('/api/keyframe/'):
            self._serve_keyframe_image()
        
        # 🎯 关键时刻 API
        elif self.path == '/api/key_moments':
            self.send_json_response(self._get_key_moments())
            
        elif self.path == '/api/key_moments/stats':
            self._handle_key_moments_stats()
        
        elif self.path == '/api/key_moments/narrative':
            self._handle_narrative_generation()
        
        elif self.path == '/api/button_log':
            self._handle_button_log()

        elif self.path == '/api/analysis_log':
            self._handle_analysis_log()

        elif self.path.startswith('/api/linkography'):
            self.send_json_response(self._get_linkography())
            
        elif self.path.startswith('/api/key_moment_image/'):
            self._serve_key_moment_image()
        
        elif self.path.startswith('/api/key_moment_video/'):
            self._serve_key_moment_video()
        
        # 🎤 语音转文字 API
        elif self.path == '/api/transcript':
            self.send_json_response(self._get_transcript())
            
        elif self.path == '/api/meeting_notes':
            self.send_json_response(self._get_meeting_notes())
        
        # 🎤 实时 ASR API
        elif self.path == '/api/realtime_asr/status':
            self.send_json_response(self._get_realtime_asr_status())
            
        elif self.path == '/api/realtime_asr/transcript':
            self.send_json_response(self._get_realtime_asr_transcript())
        
        # 📝 AI会议纪要 API
        elif self.path == '/api/meeting_notes/status':
            self.send_json_response(self._get_meeting_notes_status())
        
        elif self.path == '/api/meeting_notes/current':
            self.send_json_response(self._get_current_meeting_notes())
            
        else:
            # 静态文件服务
            super().do_GET()

    def _get_query_params(self) -> dict:
        """解析 query string 参数（在 do_GET 中已保存到 self._query_string）。"""
        try:
            from urllib.parse import parse_qs
            raw = getattr(self, "_query_string", "") or ""
            qs = parse_qs(raw, keep_blank_values=False)
            # 只取第一个值
            return {k: (v[0] if isinstance(v, list) and v else "") for k, v in qs.items()}
        except Exception:
            return {}
    
    def do_POST(self):
        """处理 POST 请求"""
        if self.path == '/api/mark_moment' or self.path == '/api/mark_key_moment':
            self._handle_mark_moment()
        elif self.path == '/api/transcribe':
            self._handle_transcribe()
        elif self.path == '/api/generate_notes':
            self._handle_generate_notes()
        # 🎤 实时 ASR 控制 API
        elif self.path == '/api/realtime_asr/start':
            self._handle_realtime_asr_start()
        elif self.path == '/api/realtime_asr/stop':
            self._handle_realtime_asr_stop()
        elif self.path == '/api/realtime_asr/pause':
            self._handle_realtime_asr_pause()
        elif self.path == '/api/realtime_asr/resume':
            self._handle_realtime_asr_resume()
        elif self.path == '/api/realtime_asr/clear':
            self._handle_realtime_asr_clear()
        
        # 👥 人物列表管理 API
        elif self.path == '/api/people/clear':
            self._handle_clear_people()
        
        # 📝 AI会议纪要控制 API
        elif self.path == '/api/meeting_notes/start':
            self._handle_meeting_notes_start()
        elif self.path == '/api/meeting_notes/stop':
            self._handle_meeting_notes_stop()
        
        # 🎬 AI直播间 API
        elif self.path == '/api/ai_live/start':
            self._handle_ai_live_start()
        elif self.path == '/api/ai_live/stop':
            self._handle_ai_live_stop()
        elif self.path == '/api/ai_live/generate':
            self._handle_ai_live_generate()
        elif self.path == '/api/ai_live/status':
            self._handle_ai_live_status()
        
        else:
            self.send_error(404, "Not Found")

    def do_OPTIONS(self):
        """处理 OPTIONS 请求 (CORS 预检)"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_DELETE(self):
        """处理 DELETE 请求"""
        print(f"🗑️  DELETE请求: {self.path}")
        
        # 删除关键时刻: /api/key_moments/{moment_id}
        if self.path.startswith('/api/key_moments/') and '/frame/' not in self.path:
            try:
                moment_id = self.path.split('/')[-1]
                print(f"📌 删除关键时刻: {moment_id}")
                if KEY_MOMENTS_AVAILABLE and key_moments_manager:
                    key_moments_manager.delete_moment(moment_id)
                    self.send_json_response({
                        "status": "success",
                        "message": f"Moment {moment_id} deleted"
                    })
                    print(f"✅ 成功删除关键时刻 {moment_id}")
                else:
                    self.send_json_response({
                        "status": "error",
                        "message": "Key moments manager not available"
                    })
            except Exception as e:
                print(f"❌ 删除关键时刻出错: {e}")
                self.send_json_response({
                    "status": "error",
                    "message": str(e)
                })
        # 删除人物记录: /api/people/{person_id}
        elif self.path.startswith('/api/people/'):
            try:
                person_id = int(self.path.split('/')[-1])
                face_db.delete_person(person_id)
                self.send_json_response({
                    "status": "success",
                    "message": f"Person {person_id} deleted"
                })
            except Exception as e:
                print(f"❌ 删除人物出错: {e}")
                self.send_json_response({
                    "status": "error",
                    "message": str(e)
                })
        # 删除 timeline 帧: /api/timeline/{person_id}/frame/{frame_num}
        elif '/api/timeline/' in self.path and '/frame/' in self.path:
            try:
                parts = self.path.split('/')
                person_id = int(parts[3])
                frame_num = int(parts[5])
                
                # 删除关键时刻中的该帧
                if KEY_MOMENTS_AVAILABLE and key_moments_manager:
                    key_moments_manager.delete_frame_from_timeline(person_id, frame_num)
                
                self.send_json_response({
                    "status": "success",
                    "message": f"Frame {frame_num} deleted"
                })
            except Exception as e:
                print(f"❌ 删除帧出错: {e}")
                self.send_json_response({
                    "status": "error",
                    "message": str(e)
                })
        else:
            print(f"⚠️  未匹配的DELETE路径: {self.path}")
            self.send_json_response({
                "status": "error",
                "message": "Not Found"
            })
    
    def _handle_stop(self):
        """处理停止请求 - 完全停止系统"""
        global is_running, realtime_asr_engine, key_moments_manager
        
        print("🛑 收到停止请求，正在停止所有服务...")
        
        # 1. 停止视频处理循环
        is_running = False
        current_stats["status"] = "stopped"
        
        # 2. 停止实时语音识别
        if REALTIME_ASR_AVAILABLE and realtime_asr_engine is not None:
            try:
                realtime_asr_engine.stop()
                print("   ✅ 语音识别已停止")
            except Exception as e:
                print(f"   ⚠️ 停止语音识别时出错: {e}")
        
        # 3. 保存关键时刻数据
        if KEY_MOMENTS_AVAILABLE and key_moments_manager is not None:
            try:
                key_moments_manager._save_moments()
                stats = key_moments_manager.get_stats()
                print(f"   ✅ 关键时刻已保存 (共 {stats.get('total_moments', 0)} 个)")
            except Exception as e:
                print(f"   ⚠️ 保存关键时刻时出错: {e}")
        
        print("🛑 系统已完全停止")
        
        self.send_json_response({
            "status": "stopped",
            "message": "System completely stopped",
            "saved": True
        })
    
    def send_json_response(self, data):
        """发送JSON响应"""
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def _get_stats(self):
        """获取实时统计"""
        stats = current_stats.copy()
        stats['known_people'] = face_db.get_person_count()
        return stats
    
    def _get_people(self):
        """获取已识别人员列表 (仅本次会话出现的人物)"""
        people = []
        seen_person_ids = set()
        
        # 1. 本次会话中识别出的已知人脸
        for person_id in face_db.active_people_this_session:
            if person_id in face_db.person_images and person_id not in seen_person_ids:
                # 计算这个person_id的所有track_ids
                all_tracks = face_db.person_appearance_history.get(person_id, [])
                people.append({
                    "id": person_id,
                    "name": face_db.person_names.get(person_id, f"Person_{person_id}"),
                    "detections": len(all_tracks),
                    "type": "face",
                    "track_count": len(all_tracks)  # 追踪次数
                })
                seen_person_ids.add(person_id)
        
        # 2. 当前活跃的追踪对象 - 映射到对应的person_id
        current_track_ids = current_stats.get("track_ids", [])
        for track_id in current_track_ids:
            # 获取这个track_id对应的person_id
            person_id = face_db.track_to_person_map.get(track_id, track_id)
            
            # 如果这个person_id还没有在列表中
            if person_id not in seen_person_ids:
                has_image = person_id in face_db.person_images
                all_tracks = face_db.person_appearance_history.get(person_id, [track_id])
                people.append({
                    "id": person_id,
                    "name": face_db.person_names.get(person_id, f"Person_{person_id}"),
                    "detections": len(all_tracks),
                    "type": "face" if has_image else "track",
                    "track_count": len(all_tracks)
                })
                seen_person_ids.add(person_id)
        
        return people
    
    def _serve_face_image(self):
        """提供人脸图片"""
        try:
            person_id = int(self.path.split('/')[-1])
            if person_id in face_db.person_images:
                img_path = face_db.person_images[person_id]
                if os.path.exists(img_path):
                    self.send_response(200)
                    self.send_header('Content-type', 'image/jpeg')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    with open(img_path, 'rb') as f:
                        self.wfile.write(f.read())
                    return
            self.send_error(404)
        except:
            self.send_error(400)
    
    def _get_timeline(self):
        """获取人物时间线"""
        try:
            person_id = int(self.path.split('/')[-1])
            return {
                "person_id": person_id,
                "person_name": face_db.person_names.get(person_id, f"Person_{person_id}"),
                "frames": [
                    {
                        "frame_id": f"{person_id}_{det['frame']}",
                        "frame_num": det['frame'],
                        "timestamp": det.get('timestamp', '--:--:--'),
                        "bbox": det['bbox'],
                        "snapshot": f"/api/frame/{person_id}_{det['frame']}"
                    }
                    for det in face_db.detection_history.get(person_id, [])
                    if det.get('snapshot')
                ]
            }
        except:
            return {"error": "Invalid person ID"}
    
    def _serve_frame_image(self):
        """提供关键帧图片"""
        try:
            frame_id = self.path.split('/')[-1]
            person_id, frame_num = map(int, frame_id.split('_'))
            
            for det in face_db.detection_history.get(person_id, []):
                if det['frame'] == frame_num and 'snapshot' in det:
                    snapshot_path = det['snapshot']
                    if os.path.exists(snapshot_path):
                        self.send_response(200)
                        self.send_header('Content-type', 'image/jpeg')
                        self.send_header('Access-Control-Allow-Origin', '*')
                        self.end_headers()
                        with open(snapshot_path, 'rb') as f:
                            self.wfile.write(f.read())
                        return
            self.send_error(404)
        except:
            self.send_error(400)
    
    def _get_keyframes(self):
        """获取AI分析的关键帧"""
        import datetime
        keyframes = []
        if KEYFRAME_PATH.exists():
            for kf in sorted(KEYFRAME_PATH.glob("*.jpg")):
                # 获取文件修改时间
                mtime = os.path.getmtime(kf)
                time_str = datetime.datetime.fromtimestamp(mtime).strftime("%H:%M:%S")
                
                # 从文件名提取帧号
                frame_num = kf.stem.replace("keyframe_", "")
                
                keyframes.append({
                    "filename": kf.name,
                    "url": f"/api/keyframe/{kf.name}",
                    "timestamp": f"Frame {int(frame_num)} @ {time_str}"
                })
        return {"keyframes": keyframes[-20:], "count": len(keyframes)}  # 最多返回20个最新
    
    def _serve_keyframe_image(self):
        """提供关键帧图片"""
        try:
            filename = self.path.split('/')[-1]
            keyframe_path = KEYFRAME_PATH / filename
            
            if keyframe_path.exists():
                self.send_response(200)
                self.send_header('Content-type', 'image/jpeg')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Cache-Control', 'public, max-age=3600')
                self.end_headers()
                with open(keyframe_path, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404, "Keyframe not found")
        except Exception as e:
            print(f"Error serving keyframe: {e}")
            self.send_error(400)
    
    def _serve_video_source_info(self):
        """提供视频源信息"""
        global key_moments_manager, current_stats
        try:
            stream_mode = current_stats.get("stream_mode", "unknown")
            video_path = None
            
            if stream_mode == "video" and key_moments_manager:
                video_path = getattr(key_moments_manager, 'video_source', None)
            
            self.send_json_response({
                "stream_mode": stream_mode,
                "video_path": video_path,
                "has_audio": bool(video_path and os.path.exists(str(video_path)))
            })
        except Exception as e:
            print(f"Error getting video source info: {e}")
            self.send_json_response({"stream_mode": "unknown", "video_path": None, "has_audio": False})
    
    def _serve_video_source_file(self):
        """提供视频文件流（支持 Range 请求以实现拖动进度条）"""
        global key_moments_manager
        try:
            if not key_moments_manager:
                self.send_error(500, "Key moments manager not initialized")
                return
            
            video_path = getattr(key_moments_manager, 'video_source', None)
            if not video_path or not os.path.exists(str(video_path)):
                self.send_error(404, "Video file not found")
                return
            
            # 获取文件大小
            file_size = os.path.getsize(video_path)
            
            # 支持 Range 请求
            range_header = self.headers.get('Range')
            if range_header:
                # 解析 Range 头
                import re
                range_match = re.match(r'bytes=(\d+)-(\d*)', range_header)
                if range_match:
                    start = int(range_match.group(1))
                    end = int(range_match.group(2)) if range_match.group(2) else file_size - 1
                    content_length = end - start + 1
                    
                    self.send_response(206)  # Partial Content
                    self.send_header('Content-Range', f'bytes {start}-{end}/{file_size}')
                    self.send_header('Content-Length', str(content_length))
                else:
                    start = 0
                    content_length = file_size
                    self.send_response(200)
                    self.send_header('Content-Length', str(file_size))
            else:
                start = 0
                content_length = file_size
                self.send_response(200)
                self.send_header('Content-Length', str(file_size))
            
            # 检测文件类型
            if str(video_path).endswith('.mkv'):
                content_type = 'video/x-matroska'
            elif str(video_path).endswith('.mp4'):
                content_type = 'video/mp4'
            elif str(video_path).endswith('.webm'):
                content_type = 'video/webm'
            else:
                content_type = 'video/mp4'  # 默认
            
            self.send_header('Content-type', content_type)
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-cache')  # 改为 no-cache 避免音频缓存问题
            self.end_headers()
            
            # 分块传输（避免大文件一次性读取）
            chunk_size = 1024 * 1024  # 1MB chunks
            with open(video_path, 'rb') as f:
                f.seek(start)
                remaining = content_length
                while remaining > 0:
                    chunk = f.read(min(chunk_size, remaining))
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        # 客户端断开连接
                        break
                    remaining -= len(chunk)
        except Exception as e:
            print(f"Error serving video source file: {e}")
            import traceback
            traceback.print_exc()
            self.send_error(400)
    
    # ============================================================
    # 🎯 关键时刻 API (双轨识别系统)
    # ============================================================
    
    def _get_key_moments(self):
        """获取所有关键时刻 (用户标记 + AI识别)"""
        global key_moments_manager
        if key_moments_manager is None:
            return {"moments": [], "count": 0, "error": "Key moments manager not initialized"}
        
        # 🛡️ Safety: If empty, try to reload from disk
        if not key_moments_manager.moments:
            try:
                print("⚠️ Key moments list empty, attempting reload from disk...")
                key_moments_manager._load_moments()
            except Exception as e:
                print(f"❌ Failed to reload moments: {e}")

        moments = key_moments_manager.get_moments()
        
        # 🟢 Force Show ALL moments (Disable filtering to match 8084 viewer)
        filtered_moments = moments
        skipped_count = 0

        
        # 添加图片和视频 URL
        for m in filtered_moments:
            m['image_url'] = f"/api/key_moment_image/{m['id']}"
            if m.get('video_path') and os.path.exists(m.get('video_path', '')):
                m['video_url'] = f"/api/key_moment_video/{m['id']}"
        
        return {
            "moments": filtered_moments,
            "count": len(filtered_moments),
            "total_before_filter": len(moments),
            "filtered_out": skipped_count,
            "stats": key_moments_manager.get_stats()
        }
    
    def _handle_button_log(self):
        """读取button_log.txt文件并返回按钮按压记录"""
        try:
            button_log_path = Path(__file__).parent / "button_log.txt"
            
            if not button_log_path.exists():
                self.send_json_response([])
                return
            
            button_presses = []
            with open(button_log_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # 解析格式: "2025-12-15 22:52:19 - 按钮: 1"
                    try:
                        parts = line.split(' - ')
                        if len(parts) >= 2:
                            timestamp_str = parts[0].strip()
                            button_part = parts[1].strip()
                            
                            # 提取按钮号码
                            if '按钮:' in button_part or '按钮：' in button_part:
                                button_num = button_part.replace('按钮:', '').replace('按钮：', '').strip().rstrip('.')
                                
                                # 转换时间戳为Unix时间戳
                                from datetime import datetime
                                dt = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                                unix_timestamp = dt.timestamp()
                                
                                button_presses.append({
                                    'timestamp': unix_timestamp,
                                    'datetime': timestamp_str,
                                    'button': button_num
                                })
                    except Exception as e:
                        print(f"解析按钮日志行失败: {line}, 错误: {e}")
                        continue
            
            self.send_json_response(button_presses)
        
        except Exception as e:
            print(f"❌ 读取按钮日志失败: {e}")
            self.send_json_response([])
    
    def _handle_analysis_log(self):
        """返回分析日志（analysis.log）的末尾内容"""
        try:
            params = self._get_query_params()
            try:
                tail_lines = int(params.get("lines", 200))
            except Exception:
                tail_lines = 200
            tail_lines = max(10, min(1000, tail_lines))

            log_path = ANALYSIS_LOG_FILE
            if not log_path.exists():
                self.send_json_response({"lines": [], "path": str(log_path)})
                return

            with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()

            tail = [ln.rstrip("\n") for ln in lines[-tail_lines:]]
            self.send_json_response({
                "lines": tail,
                "path": str(log_path),
                "total_lines": len(lines)
            })
        except Exception as e:
            print(f"⚠️ 读取分析日志失败: {e}")
            self.send_json_response({"lines": [], "path": str(ANALYSIS_LOG_FILE)})
    
    def _handle_key_moments_stats(self):
        """包装统计方法"""
        self.send_json_response(self._get_key_moments_stats())
    
    def _handle_narrative_generation(self):
        """包装叙事生成方法"""
        self.send_json_response(self._generate_narrative())
    
    def _get_key_moments_stats(self):
        """获取关键时刻统计"""
        global key_moments_manager
        if key_moments_manager is None:
            return {"error": "Key moments manager not initialized"}
        return key_moments_manager.get_stats()
    
    def _generate_narrative(self):
        """生成团队叙事"""
        global key_moments_manager
        if key_moments_manager is None:
            return {"error": "Key moments manager not initialized"}
        return key_moments_manager.generate_narrative()

    def _get_linkography(self):
        """生成 Linkography 图数据（LLM 基于卡片内容寻找跨时刻关系）。"""
        global key_moments_manager
        if key_moments_manager is None:
            return {"status": "error", "error": "Key moments manager not initialized", "nodes": [], "edges": []}

        params = self._get_query_params()
        try:
            limit = int(params.get("limit") or 30)
        except Exception:
            limit = 30
        limit = max(5, min(60, limit))

        moments = key_moments_manager.get_moments()
        # 保证时间有序，并控制规模（默认取最新 N 个，避免 prompt 过长）
        moments = sorted(moments, key=lambda x: float(x.get("timestamp") or 0.0))
        if len(moments) > limit:
            moments = moments[-limit:]

        try:
            if hasattr(key_moments_manager, "generate_linkography"):
                return key_moments_manager.generate_linkography(moments=moments)
        except Exception as e:
            return {"status": "error", "error": f"Linkography generation failed: {e}", "nodes": [], "edges": []}

        return {"status": "error", "error": "Linkography not supported", "nodes": [], "edges": []}
    
    def _serve_key_moment_image(self):
        """提供关键时刻图片"""
        global key_moments_manager
        try:
            moment_id = self.path.split('/')[-1]
            if key_moments_manager is None:
                self.send_error(500, "Key moments manager not initialized")
                return
            
            image_path = key_moments_manager.get_moment_image_path(moment_id)
            if image_path and os.path.exists(image_path):
                self.send_response(200)
                self.send_header('Content-type', 'image/jpeg')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Cache-Control', 'public, max-age=3600')
                self.end_headers()
                with open(image_path, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404, "Key moment image not found")
        except Exception as e:
            print(f"Error serving key moment image: {e}")
            self.send_error(400)
    
    def _serve_key_moment_video(self):
        """提供关键时刻视频片段"""
        global key_moments_manager
        try:
            moment_id = self.path.split('/')[-1]
            if key_moments_manager is None:
                self.send_error(500, "Key moments manager not initialized")
                return
            
            video_path = key_moments_manager.get_moment_video_path(moment_id)
            if video_path and os.path.exists(video_path):
                # 获取文件大小
                file_size = os.path.getsize(video_path)
                
                # 支持 Range 请求 (用于视频播放)
                range_header = self.headers.get('Range')
                if range_header:
                    # 解析 Range 头
                    range_match = re.match(r'bytes=(\d+)-(\d*)', range_header)
                    if range_match:
                        start = int(range_match.group(1))
                        end = int(range_match.group(2)) if range_match.group(2) else file_size - 1
                        content_length = end - start + 1
                        
                        self.send_response(206)  # Partial Content
                        self.send_header('Content-Range', f'bytes {start}-{end}/{file_size}')
                        self.send_header('Content-Length', str(content_length))
                    else:
                        start = 0
                        content_length = file_size
                        self.send_response(200)
                        self.send_header('Content-Length', str(file_size))
                else:
                    start = 0
                    content_length = file_size
                    self.send_response(200)
                    self.send_header('Content-Length', str(file_size))
                
                self.send_header('Content-type', 'video/mp4')
                self.send_header('Accept-Ranges', 'bytes')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Cache-Control', 'public, max-age=3600')
                self.end_headers()
                
                with open(video_path, 'rb') as f:
                    f.seek(start)
                    remaining = content_length
                    chunk_size = 64 * 1024  # 64KB chunks
                    
                    while remaining > 0:
                        try:
                            read_size = min(chunk_size, remaining)
                            chunk = f.read(read_size)
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            remaining -= len(chunk)
                        except (ConnectionResetError, BrokenPipeError):
                            # 客户端断开连接，这是正常现象（例如视频seek或暂停）
                            break
                        except Exception as e:
                            print(f"Error streaming video chunk: {e}")
                            break
            else:
                self.send_error(404, "Key moment video not found")
        except Exception as e:
            print(f"Error serving key moment video: {e}")
            import traceback
            traceback.print_exc()
            self.send_error(400)
    
    def _handle_mark_moment(self):
        """处理用户标记关键时刻 (The Anchor - 0.5秒意图锚定)"""
        global key_moments_manager, current_frame_raw
        
        try:
            # 读取请求体
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8') if content_length > 0 else '{}'
            data = json.loads(body) if body else {}
            
            user_note = data.get('note', '')
            
            if key_moments_manager is None:
                self.send_json_response({
                    "success": False,
                    "error": "Key moments manager not initialized"
                })
                return
            
            # 获取当前帧
            with frame_lock:
                frame = current_frame_raw.copy() if current_frame_raw is not None else None
            
            if frame is None:
                self.send_json_response({
                    "success": False,
                    "error": "No frame available"
                })
                return
            
            # 获取最近的语音转写内容
            global transcript_buffer
            now_ts = time.time()

            # 1) 短片段：用于即时展示（不作为全部上下文）
            recent_items = transcript_buffer[-10:] if transcript_buffer else []
            recent_transcript = " ".join([
                (t.get("text", "") or "").strip()
                for t in recent_items
                if (t.get("text", "") or "").strip()
            ])

            # 备注兜底：用户没写备注时，用“近期短转写”作为卡片描述，避免前端出现 No description
            effective_user_note = (user_note or "").strip() or (recent_transcript or "").strip()

            # 2) 长上下文：用于后续AI分析（会写入 moment_id_context.txt）
            # 策略：优先取最近 N 分钟；再做行数/字符上限截断。
            context_window_minutes = float(os.environ.get("KEY_MOMENT_CONTEXT_WINDOW_MINUTES", "20"))
            context_max_lines = int(os.environ.get("KEY_MOMENT_CONTEXT_MAX_LINES", "500"))
            context_max_chars = int(os.environ.get("KEY_MOMENT_CONTEXT_MAX_CHARS", "12000"))
            cutoff_ts = now_ts - max(0.0, context_window_minutes) * 60.0

            items = transcript_buffer if transcript_buffer else []
            filtered = []
            has_any_ts = any(("timestamp" in t and isinstance(t.get("timestamp"), (int, float))) for t in items)
            if has_any_ts:
                for t in items:
                    ts_epoch = t.get("timestamp")
                    if isinstance(ts_epoch, (int, float)) and ts_epoch >= cutoff_ts:
                        filtered.append(t)
            else:
                # 兼容旧数据（没有 timestamp）：退化成最近200条
                filtered = items[-200:]

            context_lines = []
            for t in filtered:
                text = (t.get("text", "") or "").strip()
                if not text:
                    continue
                ts = (t.get("time", "") or "").strip()
                if ts:
                    context_lines.append(f"[{ts}] {text}")
                else:
                    context_lines.append(text)

            # 行数截断（取末尾，保留更接近按键的内容）
            if len(context_lines) > context_max_lines:
                context_lines = context_lines[-context_max_lines:]

            context_transcript = "\n".join(context_lines)
            if len(context_transcript) > context_max_chars:
                context_transcript = context_transcript[-context_max_chars:]
                context_transcript = "[...context truncated...]\n" + context_transcript

            print(f"🎬 [关键时刻] 近期语音(短): {len(recent_transcript)} 字")
            if recent_transcript:
                print(f"🎬 [关键时刻] 内容: {recent_transcript[:100]}...")
            
            # 标记关键时刻
            moment = key_moments_manager.mark_user_anchor(
                frame=frame,
                frame_number=current_stats.get("frame_count", 0),
                person_count=current_stats.get("person_count", 0),
                track_ids=current_stats.get("track_ids", []),
                user_note=effective_user_note,
                transcript=recent_transcript,
                context_transcript=context_transcript
            )

            # 在 AFTER 秒后补齐“窗口内(前后)转写”，让关键时刻详情能看到后 15 秒内容。
            # 同时把该窗口写回 moment.transcript，避免依赖关键时刻二次ASR（会显著拖慢实时）。
            try:
                before_s = float(os.environ.get("KEY_MOMENT_BEFORE_SECONDS", "15"))
                after_s = float(os.environ.get("KEY_MOMENT_AFTER_SECONDS", "15"))

                moment_id = moment.id
                mark_ts = float(moment.timestamp)

                def _delayed_patch_anchor_text():
                    try:
                        # 等待“后段”语音进 buffer
                        time.sleep(max(0.0, after_s) + 1.0)

                        start_ts = mark_ts - max(0.0, before_s)
                        print(f"⏰ [延迟线程] 等待 {after_s} 秒后补齐窗口转写...")
                        end_ts = mark_ts + max(0.0, after_s)

                        items = transcript_buffer if transcript_buffer else []
                        print(f"⏰ [延迟线程] 筛选时间窗口: [{start_ts:.1f}, {end_ts:.1f}]")
                        window = []
                        for t in items:
                            ts_epoch = t.get("timestamp")
                            try:
                                ts_val = float(ts_epoch)
                            except (TypeError, ValueError):
                                continue
                            if start_ts <= ts_val <= end_ts:
                                window.append(t)
                        print(f"⏰ [延迟线程] 筛选结果: buffer总共 {len(items)} 条, 窗口内 {len(window)} 条")

                        lines = []
                        for t in window:
                            text = (t.get("text", "") or "").strip()
                            if not text:
                                continue
                            ts_str = (t.get("time", "") or "").strip()
                            if ts_str:
                                lines.append(f"[{ts_str}] {text}")
                            else:
                                lines.append(text)

                        window_text = "\n".join(lines).strip()

                        # ASR 元信息：取实时 ASR 的状态（如果可用）
                        asr_meta = {}
                        try:
                            global realtime_asr_engine
                            if realtime_asr_engine is not None:
                                st = realtime_asr_engine.get_status() or {}
                                asr_meta = {
                                    "provider": st.get("provider", ""),
                                    "model": st.get("model", ""),
                                    "model_dir": st.get("model_dir", ""),
                                    "asr_type": st.get("asr_type", ""),
                                }
                        except Exception:
                            asr_meta = {}

                        if key_moments_manager is not None and hasattr(key_moments_manager, "update_user_anchor_text"):
                            key_moments_manager.update_user_anchor_text(
                                moment_id=moment_id,
                                user_note=effective_user_note,
                                transcript=window_text,
                                context_transcript=window_text,
                                asr_meta=asr_meta,
                            )
                    except Exception:
                        pass

                threading.Thread(target=_delayed_patch_anchor_text, daemon=True).start()
            except Exception:
                pass
            
            # 更新统计
            stats = key_moments_manager.get_stats()
            current_stats["key_moments_count"] = stats.get("total_moments", 0)
            current_stats["user_anchors_count"] = stats.get("user_anchors", 0)
            current_stats["ai_detected_count"] = stats.get("ai_detected", 0)
            
            self.send_json_response({
                "success": True,
                "moment": moment.to_dict(),
                "message": f"🔴 关键时刻已标记: {moment.time_str}"
            })
            
        except Exception as e:
            print(f"Error marking moment: {e}")
            import traceback
            traceback.print_exc()
            self.send_json_response({
                "success": False,
                "error": str(e)
            })
    
    # ============================================================
    # 🎤 语音转文字 API
    # ============================================================
    
    def _handle_transcribe(self):
        """处理音频转写请求"""
        global transcript_buffer
        
        try:
            # 解析 multipart 表单数据
            content_type = self.headers.get('Content-Type', '')
            
            if 'multipart/form-data' not in content_type:
                self.send_json_response({"success": False, "error": "需要 multipart/form-data"})
                return
            
            # 获取 boundary
            boundary = content_type.split('boundary=')[1] if 'boundary=' in content_type else None
            if not boundary:
                self.send_json_response({"success": False, "error": "缺少 boundary"})
                return
            
            # 读取内容
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            
            # 简单解析 multipart 数据，提取音频
            boundary_bytes = f'--{boundary}'.encode()
            parts = body.split(boundary_bytes)
            
            audio_data = None
            for part in parts:
                if b'audio' in part and b'\r\n\r\n' in part:
                    header_end = part.find(b'\r\n\r\n')
                    audio_data = part[header_end + 4:]
                    # 移除结尾的 \r\n--
                    if audio_data.endswith(b'\r\n'):
                        audio_data = audio_data[:-2]
                    if audio_data.endswith(b'--'):
                        audio_data = audio_data[:-2]
                    break
            
            if not audio_data:
                self.send_json_response({"success": False, "error": "未找到音频数据"})
                return
            
            # 保存临时音频文件
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as f:
                f.write(audio_data)
                temp_path = f.name
            
            # 调用 Qwen ASR 进行转写
            text = transcribe_audio(temp_path)
            
            # 删除临时文件
            os.unlink(temp_path)
            
            if text:
                # 添加到转写缓冲区
                transcript_buffer.append({
                    "time": datetime.now().strftime("%H:%M:%S"),
                    "timestamp": time.time(),
                    "text": text
                })
                
                self.send_json_response({
                    "success": True,
                    "text": text
                })
            else:
                self.send_json_response({
                    "success": True,
                    "text": ""
                })
                
        except Exception as e:
            print(f"转写错误: {e}")
            import traceback
            traceback.print_exc()
            self.send_json_response({
                "success": False,
                "error": str(e)
            })
    
    def _handle_generate_notes(self):
        """处理生成会议纪要请求"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body) if body else {}
            
            transcript = data.get('transcript', '')
            mode = data.get('mode', 'realtime')
            
            if len(transcript) < 20:
                self.send_json_response({
                    "success": False,
                    "error": "转写内容太少"
                })
                return
            
            # 调用 LLM 生成会议纪要
            notes = generate_meeting_notes_with_llm(transcript, mode)
            
            if notes:
                self.send_json_response({
                    "success": True,
                    "notes": notes
                })
            else:
                self.send_json_response({
                    "success": False,
                    "error": "生成失败"
                })
                
        except Exception as e:
            print(f"生成会议纪要错误: {e}")
            self.send_json_response({
                "success": False,
                "error": str(e)
            })
    
    def _get_transcript(self):
        """获取当前转写内容"""
        global transcript_buffer
        return {
            "transcript": transcript_buffer,
            "count": len(transcript_buffer)
        }
    
    def _get_meeting_notes(self):
        """获取智能会议纪要 - 结合关键时刻和语音转写，累积更新"""
        global meeting_notes_cache, meeting_notes_history, key_moments_manager, transcript_buffer
        
        # 如果有 key_moments_manager，使用智能生成
        if KEY_MOMENTS_AVAILABLE and key_moments_manager is not None:
            try:
                # 生成智能会议纪要
                notes = key_moments_manager.generate_meeting_notes(transcript_buffer)
                
                # 将新纪要添加到历史记录中
                if notes and notes.get("summary"):
                    # 添加时间戳
                    notes["update_time"] = datetime.now().strftime("%H:%M:%S")
                    
                    # 检查是否是新内容 (避免重复)
                    if not meeting_notes_history or \
                       meeting_notes_history[-1].get("summary") != notes.get("summary"):
                        meeting_notes_history.append(notes.copy())
                        # 保持最多20条历史记录
                        if len(meeting_notes_history) > 20:
                            meeting_notes_history.pop(0)
                
                meeting_notes_cache = notes
                
                # 返回包含历史的完整纪要
                return {
                    "current": notes,
                    "history": meeting_notes_history,
                    "total_updates": len(meeting_notes_history),
                    "status": "active"
                }
            except Exception as e:
                print(f"⚠️ 生成会议纪要失败: {e}")
                
        # 回退到缓存或基本纪要
        if meeting_notes_cache:
            return {
                "current": meeting_notes_cache,
                "history": meeting_notes_history,
                "total_updates": len(meeting_notes_history),
                "status": "cached"
            }
            
        return {
            "current": {
                "summary": "会议进行中，纪要将在有足够内容后生成...",
                "discussion_topics": [],
                "decisions": [],
                "action_items": [],
                "key_quotes": [],
                "participants_count": current_stats.get("person_count", 0),
            },
            "history": meeting_notes_history,
            "total_updates": len(meeting_notes_history),
            "status": "recording"
        }
    
    # ============================================================
    # 🎤 实时 ASR API 处理
    # ============================================================
    
    def _get_realtime_asr_status(self):
        """获取实时 ASR 状态"""
        global realtime_asr_engine
        
        if not REALTIME_ASR_AVAILABLE:
            return {
                "available": False,
                "error": "实时语音识别模块不可用，请安装 pyaudio 和 dashscope"
            }
        
        if realtime_asr_engine is None:
            return {
                "available": True,
                "is_running": False,
                "is_recording": False,
                "message": "ASR engine not started"
            }
        
        state = realtime_asr_engine.get_status()
        return {
            "available": True,
            **state
        }
    
    def _get_realtime_asr_transcript(self):
        """获取实时转写内容"""
        global realtime_asr_engine, transcript_buffer
        
        if realtime_asr_engine is None:
            return {
                "success": False,
                "transcript": "",
                "segments": [],
                "error": "ASR engine not started"
            }
        
        state = realtime_asr_engine.get_status()
        
        # 从transcript_buffer获取所有实时转写内容
        realtime_segments = [t for t in transcript_buffer if t.get("source") == "realtime"]
        transcript_text = "\n".join([f"[{s['time']}] {s['text']}" for s in realtime_segments])
        
        # 如果有当前正在识别的文本,也显示出来
        current = state.get("current_text", "")
        
        return {
            "success": True,
            "transcript": transcript_text,
            "segments": realtime_segments,
            "current_text": current,
            "is_recording": state.get("is_recording", False),
            "segment_count": len(realtime_segments)
        }
    
    def _handle_realtime_asr_start(self):
        """启动实时 ASR"""
        global realtime_asr_engine, transcript_buffer
        
        if not REALTIME_ASR_AVAILABLE:
            self.send_json_response({
                "success": False,
                "error": "实时语音识别不可用"
            })
            return
        
        try:
            # 创建或重用引擎
            if realtime_asr_engine is None:
                realtime_asr_engine = RealtimeASR()
                
                # 设置回调 - 将转写结果同步到 transcript_buffer
                def on_transcript_update(text: str, is_final: bool, timestamp: float = None):
                    global transcript_buffer
                    if not text.strip():
                        return
                    
                    from datetime import datetime
                    ts = timestamp if timestamp is not None else time.time()

                    # 统一使用“相对会话起点”的时间，避免 16:03:43 vs 00:09:57 的歧义
                    base_ts = None
                    try:
                        if 'key_moments_manager' in globals() and key_moments_manager is not None:
                            st = getattr(key_moments_manager, 'start_time', None)
                            if isinstance(st, (int, float)):
                                base_ts = float(st)
                    except Exception:
                        base_ts = None

                    if base_ts is not None:
                        sec = max(0, int(round(float(ts) - float(base_ts))))
                        hh = sec // 3600
                        mm = (sec % 3600) // 60
                        ss = sec % 60
                        time_str = f"{hh:02d}:{mm:02d}:{ss:02d}"
                    else:
                        time_str = datetime.fromtimestamp(ts).strftime("%H:%M:%S")
                    wall_time_str = datetime.fromtimestamp(ts).strftime("%H:%M:%S")
                    
                    if is_final:
                        # 最终结果：移除最后一条临时记录（如果有），添加最终记录
                        if transcript_buffer and transcript_buffer[-1].get("is_temporary"):
                            transcript_buffer.pop()
                        
                        transcript_buffer.append({
                            "time": time_str,
                            "time_wall": wall_time_str,
                            "timestamp": ts,
                            "text": text.strip(),
                            "source": "realtime",
                            "is_temporary": False
                        })
                    else:
                        # 临时结果：更新或添加临时记录
                        if transcript_buffer and transcript_buffer[-1].get("is_temporary"):
                            # 更新最后一条临时记录
                            transcript_buffer[-1]["text"] = text.strip()
                            transcript_buffer[-1]["time"] = time_str
                            transcript_buffer[-1]["time_wall"] = wall_time_str
                            transcript_buffer[-1]["timestamp"] = ts
                        else:
                            # 添加新的临时记录
                            transcript_buffer.append({
                                "time": time_str,
                                "time_wall": wall_time_str,
                                "timestamp": ts,
                                "text": text.strip(),
                                "source": "realtime",
                                "is_temporary": True
                            })
                
                realtime_asr_engine.on_transcript_update = on_transcript_update
            
            # 启动
            success = realtime_asr_engine.start()
            
            self.send_json_response({
                "success": success,
                "message": "Real-time ASR started" if success else "Start failed"
            })
            
        except Exception as e:
            print(f"启动实时 ASR 错误: {e}")
            import traceback
            traceback.print_exc()
            self.send_json_response({
                "success": False,
                "error": str(e)
            })
    
    def _handle_realtime_asr_stop(self):
        """停止实时 ASR"""
        global realtime_asr_engine
        
        if realtime_asr_engine is None:
            self.send_json_response({
                "success": True,
                "message": "ASR engine not running"
            })
            return
        
        try:
            realtime_asr_engine.stop()
            self.send_json_response({
                "success": True,
                "message": "Real-time ASR stopped"
            })
        except Exception as e:
            self.send_json_response({
                "success": False,
                "error": str(e)
            })
    
    def _handle_realtime_asr_pause(self):
        """暂停实时 ASR"""
        global realtime_asr_engine
        
        if realtime_asr_engine is None:
            self.send_json_response({
                "success": False,
                "error": "ASR engine not started"
            })
            return
        
        realtime_asr_engine.pause()
        self.send_json_response({
            "success": True,
            "message": "Recording paused"
        })
    
    def _handle_realtime_asr_resume(self):
        """恢复实时 ASR"""
        global realtime_asr_engine
        
        if realtime_asr_engine is None:
            self.send_json_response({
                "success": False,
                "error": "ASR engine not started"
            })
            return
        
        realtime_asr_engine.resume()
        self.send_json_response({
            "success": True,
            "message": "Recording resumed"
        })
    
    def _handle_realtime_asr_clear(self):
        """清空转写记录"""
        global realtime_asr_engine, transcript_buffer
        
        if realtime_asr_engine:
            realtime_asr_engine.clear_transcript()
        
        # 同时清空 transcript_buffer 中的实时转写
        transcript_buffer = [t for t in transcript_buffer if t.get("source") != "realtime"]
        
        self.send_json_response({
            "success": True,
            "message": "Transcript cleared"
        })
    
    def _handle_clear_people(self):
        """清空当前会话的人物列表"""
        global face_db
        
        try:
            # 清空本次会话的活跃人物列表
            cleared_count = len(face_db.active_people_this_session)
            face_db.active_people_this_session.clear()
            
            print(f"🔄 已清空人物列表 (清除 {cleared_count} 人)")
            
            self.send_json_response({
                "success": True,
                "message": f"已清空人物列表 (清除 {cleared_count} 人)",
                "cleared_count": cleared_count
            })
        except Exception as e:
            print(f"❌ 清空人物列表失败: {e}")
            self.send_json_response({
                "success": False,
                "error": str(e)
            })
    
    def _get_meeting_notes_status(self):
        """获取会议纪要生成器状态"""
        global meeting_notes_generator
        
        if not MEETING_NOTES_AVAILABLE:
            return {
                "available": False,
                "is_generating": False,
                "message": "AI meeting notes unavailable"
            }
        
        if meeting_notes_generator is None:
            return {
                "available": True,
                "is_generating": False,
                "message": "Not started"
            }
        
        return meeting_notes_generator.get_status()
    
    def _get_current_meeting_notes(self):
        """获取当前会议纪要"""
        global meeting_notes_generator
        
        if meeting_notes_generator is None:
            return {
                "success": False,
                "error": "会议纪要生成器未启动"
            }
        
        notes = meeting_notes_generator.get_current_notes()
        return {
            "success": True,
            **notes
        }
    
    def _handle_meeting_notes_start(self):
        """启动AI会议纪要生成"""
        global meeting_notes_generator, realtime_asr_engine
        
        if not MEETING_NOTES_AVAILABLE:
            self.send_json_response({
                "success": False,
                "error": "AI meeting notes unavailable"
            })
            return
        
        try:
            # 确保ASR引擎已启动
            if realtime_asr_engine is None or not realtime_asr_engine.is_recording:
                self.send_json_response({
                    "success": False,
                    "error": "请先启动实时语音识别"
                })
                return
            
            # 创建会议纪要生成器
            if meeting_notes_generator is None:
                meeting_notes_generator = MeetingNotesGenerator(
                    output_dir=DATA_DIR / "meeting_notes",
                    asr_engine=realtime_asr_engine
                )
            
            # 启动生成
            success = meeting_notes_generator.start()
            
            self.send_json_response({
                "success": success,
                "message": "AI meeting notes generation started" if success else "Start failed"
            })
            
        except Exception as e:
            print(f"启动会议纪要生成错误: {e}")
            import traceback
            traceback.print_exc()
            self.send_json_response({
                "success": False,
                "error": str(e)
            })
    
    def _handle_meeting_notes_stop(self):
        """停止AI会议纪要生成"""
        global meeting_notes_generator
        
        if meeting_notes_generator is None:
            self.send_json_response({
                "success": True,
                "message": "Meeting notes generator not running"
            })
            return
        
        try:
            meeting_notes_generator.stop()
            self.send_json_response({
                "success": True,
                "message": "AI meeting notes generation stopped"
            })
        except Exception as e:
            self.send_json_response({
                "success": False,
                "error": str(e)
            })
    
    def _handle_ai_live_start(self):
        """启动AI直播间"""
        global ai_live_commentary
        
        if not AI_LIVE_AVAILABLE:
            self.send_json_response({
                "success": False,
                "error": "AI直播间不可用"
            })
            return
        
        try:
            if ai_live_commentary is None:
                ai_live_commentary = AILiveCommentary()
            
            ai_live_commentary.start()
            self.send_json_response({
                "success": True,
                "message": "AI live room started"
            })
        except Exception as e:
            self.send_json_response({
                "success": False,
                "error": str(e)
            })
    
    def _handle_ai_live_stop(self):
        """停止AI直播间"""
        global ai_live_commentary
        
        if ai_live_commentary is None:
            self.send_json_response({
                "success": True,
                "message": "AI live room not running"
            })
            return
        
        try:
            ai_live_commentary.stop()
            self.send_json_response({
                "success": True,
                "message": "AI live room stopped"
            })
        except Exception as e:
            self.send_json_response({
                "success": False,
                "error": str(e)
            })
    
    def _handle_ai_live_generate(self):
        """生成AI评论"""
        global ai_live_commentary, transcript_buffer, key_moments_manager
        
        if not AI_LIVE_AVAILABLE or ai_live_commentary is None:
            self.send_json_response({
                "success": False,
                "error": "AI直播间未启动"
            })
            return
        
        try:
            # 获取最近转写（最近30秒）
            recent_transcript = ""
            if transcript_buffer:
                cutoff_time = time.time() - 30
                recent_items = [
                    t for t in transcript_buffer 
                    if isinstance(t.get('timestamp'), (int, float)) and t.get('timestamp') > cutoff_time
                ]
                recent_transcript = "\n".join([
                    f"[{t.get('time', '')}] {t.get('text', '')}" 
                    for t in recent_items
                ])
            
            # 检测最近是否有关键时刻（60秒内）
            key_moment_detected = False
            latest_moment_desc = ""
            if KEY_MOMENTS_AVAILABLE and key_moments_manager:
                try:
                    moments = key_moments_manager.get_moments()
                    if moments:
                        # 检查最新关键时刻
                        latest = moments[-1]
                        moment_time = latest.get('timestamp', 0)
                        if isinstance(moment_time, (int, float)) and (time.time() - moment_time < 60):
                            key_moment_detected = True
                            latest_moment_desc = latest.get('description', '') or latest.get('tagline', '')
                except Exception:
                    pass
            
            # 构建上下文
            context = {
                'recent_transcript': recent_transcript,
                'key_moment_detected': key_moment_detected,
                'key_moment_desc': latest_moment_desc  # 新增：关键时刻描述
            }
            
            # 生成评论
            result = ai_live_commentary.generate_commentary(context)
            
            # 转换为JSON可序列化格式
            response = {
                "success": True,
                "commentator": None,
                "audience": []
            }
            
            if result['commentator']:
                msg = result['commentator']
                response['commentator'] = {
                    "content": msg.content,
                    "author": msg.author,
                    "role": msg.role,
                    "emoji": msg.emoji,
                    "timestamp": msg.timestamp
                }
            
            for msg in result['audience']:
                response['audience'].append({
                    "content": msg.content,
                    "author": msg.author,
                    "role": msg.role,
                    "emoji": msg.emoji,
                    "timestamp": msg.timestamp
                })
            
            self.send_json_response(response)
            
        except Exception as e:
            print(f"生成AI评论错误: {e}")
            import traceback
            traceback.print_exc()
            self.send_json_response({
                "success": False,
                "error": str(e)
            })
    
    def _handle_ai_live_status(self):
        """获取AI直播间状态"""
        global ai_live_commentary
        
        if not AI_LIVE_AVAILABLE:
            self.send_json_response({
                "available": False,
                "running": False
            })
            return
        
        if ai_live_commentary is None:
            self.send_json_response({
                "available": True,
                "running": False
            })
            return
        
        status = ai_live_commentary.get_status()
        self.send_json_response({
            "available": True,
            **status
        })
    
    def _serve_video_stream(self):
        """提供 MJPEG 视频流"""
        global current_frame_jpeg, current_frame_seq

        params = self._get_query_params() if hasattr(self, '_get_query_params') else {}
        try:
            fps = int(params.get('fps') or os.environ.get('WEB_STREAM_FPS', '12'))
        except Exception:
            fps = 12
        fps = max(1, min(30, fps))
        interval = 1.0 / float(fps)
        
        self.send_response(200)
        self.send_header('Content-type', 'multipart/x-mixed-replace; boundary=frame')
        self.send_header('Cache-Control', 'no-cache, private')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        
        try:
            last_sent_seq = -1
            next_send = time.monotonic()
            while is_running:
                with frame_lock:
                    frame_data = current_frame_jpeg
                    seq = current_frame_seq
                
                # 如果还没有帧，轻睡眠等待
                if frame_data is None:
                    time.sleep(min(0.05, interval))
                    continue

                # 避免重复发送同一帧（减少浏览器解码压力，降低“卡/糊”的观感）
                if seq == last_sent_seq:
                    time.sleep(min(0.02, interval))
                    continue

                # 节流到目标FPS（服务端发送节奏更稳）
                now = time.monotonic()
                if now < next_send:
                    time.sleep(min(next_send - now, interval))
                next_send = time.monotonic() + interval

                last_sent_seq = seq

                if frame_data is not None:
                    self.wfile.write(b'--frame\r\n')
                    self.wfile.write(b'Content-Type: image/jpeg\r\n\r\n')
                    self.wfile.write(frame_data)
                    self.wfile.write(b'\r\n')
                    self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass  # 客户端断开连接


# ============================================================
# 🎤 语音转文字功能 (Qwen ASR)
# ============================================================

transcript_buffer = []  # 转写缓冲区
meeting_notes_cache = {}  # 会议纪要缓存
meeting_notes_history = []  # 📝 纪要历史记录 (累积更新)

def transcribe_audio_with_qwen(audio_path: str) -> str:
    """使用 Qwen ASR 转写音频"""
    if not ONEKEY_AI_AVAILABLE:
        print("⚠️ Qwen API 不可用，跳过转写")
        return ""
    
    try:
        import subprocess
        
        # 先转换为 wav 格式
        wav_path = audio_path.replace('.webm', '.wav')
        result = subprocess.run([
            'ffmpeg', '-y', '-i', audio_path, 
            '-ar', '16000', '-ac', '1', '-f', 'wav', wav_path
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            print(f"ffmpeg 转换失败: {result.stderr}")
            return ""
        
        # 检查文件大小
        file_size = os.path.getsize(wav_path)
        if file_size < 1000:  # 小于1KB说明基本没内容
            os.unlink(wav_path)
            return ""
        
        # 方法1: 使用 DashScope 原生 Paraformer ASR API
        try:
            import dashscope
            from dashscope.audio.asr import Transcription
            
            dashscope.api_key = QWEN_API_KEY
            
            # 使用本地文件转写
            task = Transcription.async_call(
                model='paraformer-v2',
                file_urls=[f'file://{wav_path}'],
                language_hints=['zh', 'en']
            )
            
            # 等待结果
            result = Transcription.wait(task)
            
            if result.status_code == 200:
                text = ""
                for r in result.output.get('results', []):
                    text += r.get('transcription_text', '')
                
                os.unlink(wav_path)
                
                if text.strip():
                    print(f"🎤 转写: {text[:50]}...")
                    return text.strip()
                return ""
            else:
                print(f"ASR 失败: {result.message}")
        except ImportError:
            print("dashscope 未安装，使用备用方法")
        except Exception as e:
            print(f"DashScope ASR 错误: {e}")
        
        # 方法2: 使用 Qwen-Audio-Turbo (兼容 OpenAI 格式)
        try:
            from openai import OpenAI
            import base64
            
            with open(wav_path, 'rb') as f:
                audio_base64 = base64.b64encode(f.read()).decode('utf-8')
            
            client = OpenAI(
                api_key=QWEN_API_KEY,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
            )
            
            response = client.chat.completions.create(
                model="qwen2-audio-instruct",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "audio_url", "audio_url": {"url": f"data:audio/wav;base64,{audio_base64}"}},
                            {"type": "text", "text": "请将这段音频转写为文字。只输出转写的文字内容，不要添加任何解释。"}
                        ]
                    }
                ],
                max_tokens=500,
                timeout=30
            )
            
            text = response.choices[0].message.content.strip()
            os.unlink(wav_path)
            
            # 过滤无效结果
            invalid_responses = ['空', '无', '没有语音', '无语音内容', '', '这段音频没有语音内容', '无法识别']
            if any(inv in text for inv in invalid_responses):
                return ""
            
            print(f"🎤 转写: {text[:50]}...")
            return text
            
        except Exception as e:
            print(f"Qwen Audio 转写错误: {e}")
            if os.path.exists(wav_path):
                os.unlink(wav_path)
            return ""
        
    except Exception as e:
        print(f"转写错误: {e}")
        import traceback
        traceback.print_exc()
        return ""


def generate_meeting_notes_with_llm(transcript: str, mode: str = 'realtime') -> dict:
    """使用 LLM 生成会议纪要（支持 Qwen 和 Claude）"""
    global meeting_notes_cache
    
    if not ONEKEY_AI_AVAILABLE:
        provider_name = "Claude" if LLM_PROVIDER.startswith("claude") else "Qwen"
        return {"error": f"{provider_name} API 不可用"}
    
    try:
        # 构建 prompt
        if mode == 'realtime':
            prompt = f"""请根据以下会议转写内容，生成简洁的实时会议纪要。

转写内容:
{transcript}

请以 JSON 格式返回:
{{
    "summary": "一句话概括当前讨论内容",
    "key_points": ["要点1", "要点2"],
    "action_items": ["待办事项1"],
    "decisions": ["决议1"]
}}

只返回 JSON，不要其他内容。如果内容太少无法提取，返回空数组。"""
        else:
            prompt = f"""请根据以下完整会议转写内容，生成详细的会议纪要。

转写内容:
{transcript}

请以 JSON 格式返回:
{{
    "summary": "会议整体摘要（2-3句话）",
    "key_points": ["讨论要点1", "讨论要点2", "讨论要点3"],
    "action_items": ["待办事项1: 责任人", "待办事项2: 责任人"],
    "decisions": ["决议1", "决议2"],
    "participants_insights": ["参与者观点1", "参与者观点2"]
}}

只返回 JSON，不要其他内容。"""
        
        # 根据 provider 调用不同的 API
        if LLM_PROVIDER.startswith("claude"):
            from anthropic import Anthropic
            client = Anthropic(api_key=CLAUDE_API_KEY)
            model = os.environ.get("LLM_MODEL", "claude-3-5-haiku-20241022")
            response = client.messages.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
                temperature=0.3
            )
            result_text = "".join([block.text for block in response.content if getattr(block, "type", None) == "text"]).strip()
        else:
            from openai import OpenAI
            client = OpenAI(
                api_key=QWEN_API_KEY,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
            )
            model = os.environ.get("LLM_MODEL", "qwen3-max")
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=800,
                timeout=30  # 显式设置超时
            )
            result_text = response.choices[0].message.content.strip()
        
        # 解析 JSON
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
        
        notes = json.loads(result_text)
        
        # 缓存结果
        meeting_notes_cache = notes
        meeting_notes_cache["updated_at"] = datetime.now().isoformat()
        
        print(f"📝 会议纪要已生成")
        return notes
        
    except Exception as e:
        print(f"生成会议纪要错误: {e}")
        return {"error": str(e)}


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """多线程 HTTP 服务器，支持同时处理多个请求"""
    daemon_threads = True

def start_web_server(port=8080):
    """启动Web服务器（多线程）"""
    os.chdir(str(BASE_DIR))
    server = ThreadingHTTPServer(('0.0.0.0', port), IntegratedHandler)
    print(f"🌐 Web界面: http://localhost:{port}/integrated%20final.html")
    server.serve_forever()

# ============================================================
# 📹 视频源管理 - 支持OBS
# ============================================================

class VideoSource:
    """统一的视频源管理"""
    
    @staticmethod
    def open_camera(camera_id=0):
        """打开摄像头"""
        cap = cv2.VideoCapture(camera_id)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        current_stats["stream_mode"] = "camera"
        return cap, 30
    
    @staticmethod
    def open_video(video_path):
        """打开视频文件"""
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        current_stats["stream_mode"] = "video"
        return cap, fps
    
    @staticmethod
    def open_obs_stream(url="rtmp://localhost/live"):
        """
        打开OBS推流
        OBS设置:
        1. 设置 -> 推流
        2. 服务: 自定义
        3. 服务器: rtmp://localhost/live
        4. 串流密钥: stream
        
        或使用虚拟摄像头:
        OBS -> 工具 -> 虚拟摄像头 -> 启动
        """
        import glob
        import subprocess
        
        # 方式1: RTMP流 (需要nginx-rtmp或其他流媒体服务器)
        cap = cv2.VideoCapture(url)
        
        # 方式2: OBS虚拟摄像头 (更简单)
        if not cap.isOpened():
            print("⚠️  RTMP流连接失败，尝试OBS虚拟摄像头...")
            
            # 查找 v4l2loopback 设备 (OBS 虚拟摄像头)
            video_devices = sorted(glob.glob("/dev/video*"), key=lambda x: int(x.replace("/dev/video", "")))
            obs_device_path = None
            obs_device_idx = None
            
            # 优先通过驱动名称识别 v4l2loopback 设备
            for device in video_devices:
                try:
                    idx = int(device.replace("/dev/video", ""))
                    # 使用 v4l2-ctl 检查驱动名称
                    result = subprocess.run(
                        ["v4l2-ctl", "-d", device, "--info"],
                        capture_output=True, text=True, timeout=2
                    )
                    if "v4l2 loopback" in result.stdout.lower() or "obs" in result.stdout.lower():
                        obs_device_path = device
                        obs_device_idx = idx
                        print(f"🎯 检测到 OBS 虚拟摄像头: {device}")
                        break
                except Exception:
                    continue
            
            # 🔧 在 Jetson Orin 等平台上，使用 GStreamer pipeline 处理 YUYV 格式
            if obs_device_path is not None:
                # 方法1: 使用 GStreamer pipeline (解决 YUYV 格式兼容问题)
                gst_pipeline = (
                    f"v4l2src device={obs_device_path} ! "
                    "video/x-raw,format=YUY2 ! "
                    "videoconvert ! "
                    "video/x-raw,format=BGR ! "
                    "appsink drop=1"
                )
                print(f"🚀 尝试 GStreamer pipeline: {obs_device_path}")
                cap = cv2.VideoCapture(gst_pipeline, cv2.CAP_GSTREAMER)
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        print(f"✅ GStreamer 成功打开 OBS 虚拟摄像头 (设备 {obs_device_idx})")
                        current_stats["stream_mode"] = "obs"
                        return cap, 30
                    cap.release()
                    print("⚠️  GStreamer 打开成功但无法读取帧")
                else:
                    print("⚠️  GStreamer pipeline 打开失败，尝试直接 V4L2...")
                
                # 方法2: 直接使用 V4L2 (传统方式)
                cap = cv2.VideoCapture(obs_device_idx, cv2.CAP_V4L2)
                if cap.isOpened():
                    # 设置较小的分辨率以提高兼容性
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # 减少缓冲延迟
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        print(f"✅ V4L2 成功打开 OBS 虚拟摄像头 (设备 {obs_device_idx})")
                        current_stats["stream_mode"] = "obs"
                        return cap, 30
                    cap.release()
                
                # 方法3: 不指定后端 (OpenCV 自动选择)
                cap = cv2.VideoCapture(obs_device_idx)
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        print(f"✅ 成功打开 OBS 虚拟摄像头 (设备 {obs_device_idx})")
                        current_stats["stream_mode"] = "obs"
                        return cap, 30
                    cap.release()
            
            # 后备：从高设备号开始尝试（v4l2loopback 通常在较高设备号）
            for i in range(15, -1, -1):
                try:
                    # 优先使用 GStreamer
                    gst_pipeline = (
                        f"v4l2src device=/dev/video{i} ! "
                        "videoconvert ! "
                        "video/x-raw,format=BGR ! "
                        "appsink drop=1"
                    )
                    cap = cv2.VideoCapture(gst_pipeline, cv2.CAP_GSTREAMER)
                    if cap.isOpened():
                        ret, frame = cap.read()
                        if ret and frame is not None:
                            print(f"✅ GStreamer 找到可用摄像头 (设备 {i})")
                            current_stats["stream_mode"] = "obs"
                            return cap, 30
                        cap.release()
                    
                    # 后备直接打开
                    cap = cv2.VideoCapture(i)
                    if cap.isOpened():
                        ret, frame = cap.read()
                        if ret and frame is not None:
                            print(f"✅ 找到可用摄像头 (设备 {i})")
                            current_stats["stream_mode"] = "obs"
                            return cap, 30
                        cap.release()
                except Exception:
                    continue
        
        if cap.isOpened():
            current_stats["stream_mode"] = "obs"
            return cap, 30
        
        raise ValueError("无法连接OBS流，请确保OBS虚拟摄像头已启动")

# ============================================================
# 🎯 人脸识别处理
# ============================================================

def process_face_recognition(frame, boxes, frame_count, face_app):
    """处理人脸识别"""
    if not INSIGHTFACE_AVAILABLE or face_app is None or boxes is None:
        return {}
    
    person_face_map = {}
    
    for box in boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
        track_id = int(box.id.cpu().numpy().item()) if box.id is not None else None
        
        if track_id is None:
            continue
        
        # 提取人物区域
        person_crop = frame[y1:y2, x1:x2]
        if person_crop.size == 0:
            continue
        
        # 检测人脸
        faces = face_app.get(person_crop)
        if len(faces) == 0:
            continue
        
        # 取最大人脸
        face = max(faces, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))
        
        # 检查人脸质量
        face_width = face.bbox[2] - face.bbox[0]
        face_height = face.bbox[3] - face.bbox[1]
        
        if face_width < MIN_FACE_SIZE or face_height < MIN_FACE_SIZE:
            continue
        if hasattr(face, 'det_score') and face.det_score < MIN_FACE_QUALITY:
            continue
        
        # 获取人脸特征
        embedding = face.embedding
        embedding = embedding / np.linalg.norm(embedding)
        
        # 查找匹配
        person_id = face_db.find_match(embedding)
        
        if person_id is None:
            # 提取人脸图像
            fx1, fy1, fx2, fy2 = map(int, face.bbox)
            fx1, fy1 = max(0, fx1), max(0, fy1)
            fx2 = min(person_crop.shape[1], fx2)
            fy2 = min(person_crop.shape[0], fy2)
            face_crop = person_crop[fy1:fy2, fx1:fx2]
            
            if face_crop.size > 0:
                person_id = face_db.add_face(embedding, frame_image=face_crop)
                print(f"🆕 New person found: Person_{person_id}")
        
        # 记录检测
        snapshot = frame.copy() if frame_count % 30 == 0 else None
        face_db.record_detection(person_id, frame_count, (x1, y1, x2, y2), snapshot)
        person_face_map[track_id] = person_id
        current_stats['face_detections'] += 1
        
        # 🔄 标记为本次会话活跃人物
        face_db.active_people_this_session.add(person_id)
    
    return person_face_map

# ============================================================
# 🎬 主处理循环
# ============================================================

# 全局模型缓存
_yolo_model_cache = None
YOLO_DEVICE = "cpu"

def get_yolo_model():
    """延迟加载YOLO模型(单例模式)，自动使用GPU加速"""  
    global _yolo_model_cache, YOLO_DEVICE
    if _yolo_model_cache is None:
        import torch
        
        # 1. OpenVINO Check (AMD 780M)
        use_openvino = False
        try:
             # Check if we should check OpenVINO (if no CUDA and not MacOS MPS)
             is_mps = hasattr(torch.backends, 'mps') and torch.backends.mps.is_available()
             if not torch.cuda.is_available() and not is_mps:
                from openvino.runtime import Core
                if "GPU" in Core().available_devices:
                    use_openvino = True
                    YOLO_DEVICE = "GPU"
        except ImportError:
            pass
        except Exception as e:
            print(f"⚠️ OpenVINO Check Error: {e}")

        # 2. Device Selection
        if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            YOLO_DEVICE = "mps"
            print("🚀 首次加载YOLO模型(MPS GPU加速)...")
            _yolo_model_cache = YOLO(MODEL_PATH)
            _yolo_model_cache.to(YOLO_DEVICE)
        elif torch.cuda.is_available():
            YOLO_DEVICE = "cuda"
            print("🚀 首次加载YOLO模型(CUDA GPU加速)...")
            _yolo_model_cache = YOLO(MODEL_PATH)
            _yolo_model_cache.to(YOLO_DEVICE)
        elif use_openvino:
            print(f"🚀 首次加载YOLO模型(OpenVINO AMD GPU加速)...")
            # MODEL_PATH usually models/yolo11n.pt
            # Export path usually models/yolo11n_openvino_model
            ov_path = os.path.splitext(MODEL_PATH)[0] + "_openvino_model"
            
            if not os.path.exists(ov_path):
                print(f"⚠️ 正在导出 OpenVINO 模型: {ov_path}")
                try:
                    YOLO(MODEL_PATH).export(format="openvino")
                except Exception as e:
                    print(f"❌ 导出失败: {e}, 回退到CPU")
                    YOLO_DEVICE = "cpu"
                    _yolo_model_cache = YOLO(MODEL_PATH)
                    return _yolo_model_cache

            if os.path.exists(ov_path):
                _yolo_model_cache = YOLO(ov_path, task="detect")
                # Reset device to cpu for tracker compatibility (inference happens on OpenVINO runtime)
                YOLO_DEVICE = "cpu"
            else:
                YOLO_DEVICE = "cpu"
                _yolo_model_cache = YOLO(MODEL_PATH)
        else:
            YOLO_DEVICE = "cpu"
            print("🚀 首次加载YOLO模型(CPU)...")
            _yolo_model_cache = YOLO(MODEL_PATH)
            _yolo_model_cache.to(YOLO_DEVICE)
        
        print(f"✅ YOLO模型加载完成 (Device: {YOLO_DEVICE})")
    return _yolo_model_cache

def process_video_stream(cap, video_fps, face_app=None, enable_ai=False, show_window=True, video_source_path=None):
    """处理视频流"""
    global is_running, key_moments_manager, current_frame_raw, microphone_recorder
    
    # 延迟加载YOLO模型
    model = get_yolo_model()
    
    # 🎤 启动麦克风录制（摄像头模式）
    if MICROPHONE_AVAILABLE and not video_source_path:
        try:
            microphone_recorder = MicrophoneRecorder(output_dir=DATA_DIR / "audio")
            if microphone_recorder.start_recording():
                print("✅ 麦克风录制已启动")
        except Exception as e:
            print(f"⚠️  麦克风启动失败: {e}")
            microphone_recorder = None
    
    # 🎯 初始化关键时刻管理器 (传递视频源用于音频提取)
    if KEY_MOMENTS_AVAILABLE:
        key_moments_manager = KeyMomentsManager(
            data_dir=DATA_DIR,
            video_source=video_source_path,
            microphone_recorder=microphone_recorder,  # 传递麦克风录制器
            video_fps=video_fps
        )
    
    frame_count = 0
    fps_start_time = time.time()
    fps_frame_count = 0
    current_fps = 0
    last_sample_time = 0
    process_start_time = time.time()
    
    is_video_file = current_stats["stream_mode"] == "video"
    
    print(f"✅ 系统启动!")
    print(f"📊 视频源: {current_stats['stream_mode']}")
    print(f"🎯 人脸识别: {'启用' if INSIGHTFACE_AVAILABLE else '禁用'}")
    print(f"🤖 AI分析: {'启用' if enable_ai and ONEKEY_AI_AVAILABLE else '禁用'}")
    print(f"🔴 关键时刻标记: {'启用' if KEY_MOMENTS_AVAILABLE else '禁用'}")
    print("📺 按 'q' 退出 | Web界面可查看实时数据")
    
    current_stats["status"] = "running"

    while cap.isOpened() and is_running:
        success, frame = cap.read()
        
        if not success:
            print("❌ 读取帧失败")
            break
        
        frame_count += 1
        fps_frame_count += 1
        
        # 保存原始帧用于关键时刻标记
        with frame_lock:
            current_frame_raw = frame.copy()
        
        # 计算FPS
        if fps_frame_count >= 30:
            elapsed = time.time() - fps_start_time
            current_fps = fps_frame_count / elapsed if elapsed > 0 else 0
            fps_start_time = time.time()
            fps_frame_count = 0
        
        # YOLO追踪
        results = model.track(
            frame,
            persist=True,
            conf=0.25,
            classes=[0],
            verbose=False,
            device=YOLO_DEVICE,
            tracker="multi_person_tracker/configs/bytetrack_persistent.yaml"
            if Path("multi_person_tracker/configs/bytetrack_persistent.yaml").exists()
            else "bytetrack.yaml"
        )
        
        boxes = results[0].boxes
        person_count = len(boxes) if boxes is not None else 0
        track_ids = boxes.id.int().cpu().tolist() if boxes is not None and boxes.id is not None else []
        
        # 人脸识别采样
        current_time = time.time()
        person_face_map = {}
        
        if current_time - last_sample_time >= SAMPLE_INTERVAL and person_count > 0:
            person_face_map = process_face_recognition(frame, boxes, frame_count, face_app)
            last_sample_time = current_time
            
            # 💡 纯YOLO模式 + Re-ID: 智能匹配和保存人物图像
            if not INSIGHTFACE_AVAILABLE and boxes is not None:
                # print(f"🔍 采样检测: {len(boxes)} 个人物, Track IDs: {track_ids}")
                
                # 记录当前帧已分配的person_id，防止同一帧出现同一个人
                assigned_person_ids_this_frame = set()
                
                for box in boxes:
                    if box.id is not None:
                        track_id = int(box.id.cpu().numpy().item())
                        
                        # 裁剪人物图像
                        x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
                        h, w = frame.shape[:2]
                        margin = 20
                        x1_crop = max(0, x1 - margin)
                        y1_crop = max(0, y1 - margin)
                        x2_crop = min(w, x2 + margin)
                        y2_crop = min(h, y2 + margin)
                        person_crop = frame[y1_crop:y2_crop, x1_crop:x2_crop]
                        
                        if person_crop.size == 0:
                            continue
                        
                        # 🎯 Re-ID: 检查是否已经见过这个人
                        if track_id in face_db.track_to_person_map:
                            # 已知的track_id,直接使用映射的person_id
                            person_id = face_db.track_to_person_map[track_id]
                            # 更新特征库
                            face_db.add_person_feature(person_id, person_crop)
                        else:
                            # 新的track_id,尝试通过视觉特征匹配已知人物
                            # 提高阈值到 0.75 以减少误匹配
                            matched_person_id = face_db.find_matching_person(person_crop, threshold=0.75)
                            
                            # 关键修正: 如果匹配到的人已经在当前帧出现过，则不能复用该ID (物理约束)
                            if matched_person_id is not None and matched_person_id in assigned_person_ids_this_frame:
                                matched_person_id = None
                            
                            if matched_person_id is not None:
                                # 找到匹配!这是一个已知人物
                                person_id = matched_person_id
                                face_db.map_track_to_person(track_id, person_id)
                                face_db.add_person_feature(person_id, person_crop)
                                print(f"🔗 Re-ID匹配: Track#{track_id} -> Person_{person_id}")
                            else:
                                # 全新的人物,分配新ID
                                person_id = track_id  # 使用track_id作为person_id
                                # 如果该ID已被占用(极少情况),则自增
                                while person_id in face_db.person_names or person_id in assigned_person_ids_this_frame:
                                    person_id += 1000
                                    
                                face_db.map_track_to_person(track_id, person_id)
                                face_db.add_person_feature(person_id, person_crop)
                                
                                # 保存第一次出现的图像
                                img_path = FACE_DB_PATH / f"person_{person_id}.jpg"
                                cv2.imwrite(str(img_path), person_crop)
                                face_db.person_images[person_id] = str(img_path)
                                face_db.person_names[person_id] = f"Person_{person_id}"
                                face_db.active_people_this_session.add(person_id)
                                print(f"👤 New person: Person_{person_id} (Track#{track_id})")
                            
                            # 更新person_face_map用于后续绘制
                            person_face_map[track_id] = person_id
                        
                        # 记录本帧已使用的person_id
                        assigned_person_ids_this_frame.add(person_id)
            
            # 保存关键帧（当检测到人物时）
            if person_count > 0:
                keyframe_path = KEYFRAME_PATH / f"keyframe_{frame_count:06d}.jpg"
                cv2.imwrite(str(keyframe_path), frame)
                current_stats["keyframe_count"] = len(list(KEYFRAME_PATH.glob("*.jpg")))
        
        # 🎯 更新关键时刻管理器 (每帧检查是否需要 AI 分析)
        if KEY_MOMENTS_AVAILABLE and key_moments_manager is not None:
            # 🎬 将帧添加到缓冲区 (用于生成视频片段)
            key_moments_manager.add_frame_to_buffer(frame, frame_count)
            
            # 🔗 将track_ids转换为统一的person_ids
            unified_person_ids = [face_db.track_to_person_map.get(tid, tid) for tid in track_ids]
            
            key_moments_manager.update_frame(
                frame=frame,
                frame_number=frame_count,
                person_count=person_count,
                track_ids=unified_person_ids  # 使用统一的person_ids
            )
            # 更新关键时刻统计
            km_stats = key_moments_manager.get_stats()
            current_stats["key_moments_count"] = km_stats.get("total_moments", 0)
            current_stats["user_anchors_count"] = km_stats.get("user_anchors", 0)
            current_stats["ai_detected_count"] = km_stats.get("ai_detected", 0)
        
        # 🎤📷 多模态分析 (结合音频转写 + 视频切片)
        # 按切片窗口触发联合分析（默认2分钟，可用 MULTIMODAL_SLICE_SECONDS 调整）
        global last_multimodal_analysis_time, transcript_buffer, video_slice_buffer, video_slice_start_time
        if KEY_MOMENTS_AVAILABLE and key_moments_manager is not None:
            if not hasattr(process_video_stream, '_last_mm_time'):
            # 避免启动后立即触发一次“空转写/极少帧”的切片分析
                process_video_stream._last_mm_time = float(current_time)

            if not hasattr(process_video_stream, '_slice_last_ts'):
                process_video_stream._slice_last_ts = 0.0
            
            slice_seconds = float(VIDEO_SLICE_SECONDS) if VIDEO_SLICE_SECONDS and VIDEO_SLICE_SECONDS > 1e-6 else 210.0

            # 🎬 添加当前帧到视频切片缓冲区：按时间采样，覆盖完整切片窗口
            # 采样帧存储为降分辨率，避免内存爆炸。
            slice_interval = 1.0 / float(VIDEO_SLICE_FPS) if VIDEO_SLICE_FPS > 1e-6 else 0.5
            if (float(current_time) - float(getattr(process_video_stream, '_slice_last_ts', 0.0) or 0.0)) >= slice_interval:
                process_video_stream._slice_last_ts = float(current_time)
                try:
                    if VIDEO_SLICE_FRAME_WIDTH > 0:
                        h, w = frame.shape[:2]
                        if w > VIDEO_SLICE_FRAME_WIDTH:
                            scale = float(VIDEO_SLICE_FRAME_WIDTH) / float(w)
                            new_w = int(w * scale)
                            new_h = int(h * scale)
                            frame_small = cv2.resize(frame, (new_w, new_h))
                        else:
                            frame_small = frame
                    else:
                        frame_small = frame
                except Exception:
                    frame_small = frame

                slice_item = {
                    "ts": float(current_time),
                    "frame_number": int(frame_count),
                    "frame": frame_small.copy(),
                }
                if len(video_slice_buffer) < video_slice_max_frames:
                    video_slice_buffer.append(slice_item)
                else:
                    video_slice_buffer.pop(0)
                    video_slice_buffer.append(slice_item)
            
            # 按切片窗口触发一次分析
            if current_time - process_video_stream._last_mm_time >= slice_seconds and len(video_slice_buffer) > 0:
                # 获取最近切片窗口的转写文本
                recent_transcript = ""
                cutoff_time = current_time - slice_seconds
                if transcript_buffer:
                    recent_texts = [t.get('text', '') for t in transcript_buffer 
                                   if t.get('timestamp', 0) > cutoff_time]
                    recent_transcript = ' '.join(recent_texts)
                
                # 🔗 转换为统一的person_ids
                unified_person_ids = [face_db.track_to_person_map.get(tid, tid) for tid in track_ids]
                
                # 异步执行多模态分析(使用视频切片)
                def do_video_slice_analysis(frames_slice, transcript_text_5m, fn, pc, ti, curr_time):
                    try:
                        print(f"🎬 开始视频切片分析 ({int(slice_seconds)}s) (帧 {fn}, {len(frames_slice)} 关键帧, 语音: {len(transcript_text_5m)} 字)")

                        found_count = 0
                        max_hits = int(os.environ.get("MULTIMODAL_MAX_HITS_PER_SLICE", "1"))
                        if max_hits < 1:
                            max_hits = 1

                        def _transcript_window(center_ts: float, before_s: float, after_s: float) -> str:
                            items = transcript_buffer if transcript_buffer else []
                            start_ts = float(center_ts) - float(before_s)
                            end_ts = float(center_ts) + float(after_s)
                            window = []
                            for t in items:
                                ts_epoch = t.get("timestamp")
                                if isinstance(ts_epoch, (int, float)) and start_ts <= float(ts_epoch) <= end_ts:
                                    window.append(t)

                            lines = []
                            for t in window:
                                text = (t.get("text", "") or "").strip()
                                if not text:
                                    continue
                                ts_str = (t.get("time", "") or "").strip()
                                if ts_str:
                                    lines.append(f"[{ts_str}] {text}")
                                else:
                                    lines.append(text)
                            return "\n".join(lines).strip()

                        # 窗口默认值：用于“给多模态判定的转写窗口”
                        before_s = float(os.environ.get("MULTIMODAL_BEFORE_SECONDS", "15"))
                        after_s = float(os.environ.get("MULTIMODAL_AFTER_SECONDS", "15"))

                        # 视频窗口可以比转写窗口更大（默认跟随转写窗口）
                        video_before_s = float(os.environ.get("MULTIMODAL_VIDEO_BEFORE_SECONDS", str(before_s)))
                        video_after_s = float(os.environ.get("MULTIMODAL_VIDEO_AFTER_SECONDS", str(after_s)))

                        # 语义定位：先用 5 分钟全文转写挑出候选时间点，再回到这些时间点对齐最近的帧
                        candidates = []
                        try:
                            cutoff_5m = float(curr_time) - float(slice_seconds)
                            recent_items = [t for t in (transcript_buffer or []) if isinstance(t.get('timestamp'), (int, float)) and float(t.get('timestamp')) > cutoff_5m]
                            if hasattr(key_moments_manager, 'suggest_key_moment_candidates'):
                                base_ts = getattr(key_moments_manager, 'start_time', None)
                                candidates = key_moments_manager.suggest_key_moment_candidates(
                                    recent_items,
                                    max_candidates=5,
                                    base_timestamp=float(base_ts) if isinstance(base_ts, (int, float)) else None,
                                )
                        except Exception:
                            candidates = []

                        def _video_window_frames(center_ts: float, before: float, after: float):
                            out = []
                            try:
                                start_ts = float(center_ts) - float(before)
                                end_ts = float(center_ts) + float(after)
                                print(f"🔍 [DEBUG] 筛选切片: frames_slice={len(frames_slice)}, 目标窗口=[{start_ts:.1f}, {end_ts:.1f}]")
                            except Exception:
                                return out
                            
                            count_valid = 0
                            for it in frames_slice:
                                if not isinstance(it, dict):
                                    continue
                                ts = it.get('ts')
                                if not isinstance(ts, (int, float)):
                                    continue
                                count_valid += 1
                                if start_ts <= float(ts) <= end_ts:
                                    out.append(it)
                            
                            # print(f"🔍 [DEBUG] 筛选结果: {len(out)} 帧 (从 {count_valid} 帧中)")
                            return out

                        def _nearest_frame_by_ts(target_ts: float):
                            best = None
                            best_d = 1e18
                            for it in frames_slice:
                                if not isinstance(it, dict):
                                    continue
                                ts = it.get('ts')
                                if not isinstance(ts, (int, float)):
                                    continue
                                d = abs(float(ts) - float(target_ts))
                                if d < best_d:
                                    best_d = d
                                    best = it
                            return best, best_d
                        
                        # ① 先走“语义定位→对齐帧→多模态判定”
                        for cand in candidates:
                            try:
                                frame_item, delta = _nearest_frame_by_ts(float(cand.get('timestamp')))
                                if not frame_item:
                                    continue
                                frame_sample = frame_item.get("frame")
                                frame_no = int(frame_item.get("frame_number", fn))
                                frame_ts = float(frame_item.get("ts", curr_time))

                                window_transcript = _transcript_window(frame_ts, before_s=before_s, after_s=after_s)
                                if os.environ.get('MULTIMODAL_DEBUG', '0') == '1':
                                    print(f"🧭 Locator pick [{cand.get('time_str','--')}] Δt={delta:.1f}s reason={cand.get('reason','')[:60]}")

                                result = key_moments_manager.analyze_with_multimodal(
                                    frame=frame_sample,
                                    frame_number=frame_no,
                                    timestamp=frame_ts,
                                    transcript_text=window_transcript,
                                    person_count=pc,
                                    track_ids=ti,
                                    video_frames=_video_window_frames(frame_ts, video_before_s, video_after_s),
                                )
                                
                                # 如果检测到关键时刻(重要性 > 0.2)
                                if result:
                                    print(f"✨ 发现关键时刻! 重要性: {result.get('importance', 0):.2f}")
                                    print(f"   描述: {result.get('description', 'N/A')[:100]}")
                                    found_count += 1
                                    
                                    # 🔧 补齐窗口转写（只显示前后15秒的转写，不是整个切片）
                                    try:
                                        # 获取最新创建的关键时刻
                                        moments = key_moments_manager.get_moments()
                                        if moments:
                                            latest_moment = moments[-1]
                                            moment_id = latest_moment.get('id', '')
                                            moment_ts = float(latest_moment.get('timestamp', frame_ts))
                                            
                                            # 计算窗口
                                            before_s = float(os.environ.get("MULTIMODAL_BEFORE_SECONDS", "15"))
                                            after_s = float(os.environ.get("MULTIMODAL_AFTER_SECONDS", "15"))
                                            start_ts = moment_ts - before_s
                                            end_ts = moment_ts + after_s
                                            
                                            # 从transcript_buffer筛选窗口转写
                                            items = transcript_buffer if transcript_buffer else []
                                            window = []
                                            for t in items:
                                                ts_epoch = t.get("timestamp")
                                                try:
                                                    ts_val = float(ts_epoch)
                                                except (TypeError, ValueError):
                                                    continue
                                                if start_ts <= ts_val <= end_ts:
                                                    window.append(t)
                                            
                                            lines = []
                                            for t in window:
                                                text = (t.get("text", "") or "").strip()
                                                if not text:
                                                    continue
                                                ts_str = (t.get("time", "") or "").strip()
                                                if ts_str:
                                                    lines.append(f"[{ts_str}] {text}")
                                                else:
                                                    lines.append(text)
                                            
                                            window_text = "\n".join(lines).strip()
                                            
                                            # 更新moment的转写为窗口转写
                                            if window_text and key_moments_manager and hasattr(key_moments_manager, "update_user_anchor_text"):
                                                key_moments_manager.update_user_anchor_text(
                                                    moment_id=moment_id,
                                                    user_note="",
                                                    transcript=window_text,
                                                    context_transcript=transcript_text_5m,
                                                    asr_meta={},
                                                )
                                                print(f"   ✅ 已补齐窗口转写: {len(window)} 条片段, 共 {len(window_text)} 字")
                                    except Exception as patch_err:
                                        print(f"   ⚠️ 补齐窗口转写失败: {patch_err}")

                                    # 同一轮切片：允许命中多个（默认1个）
                                    if found_count >= max_hits:
                                        break
                            except Exception:
                                continue

                            if found_count >= max_hits:
                                break

                        # ② 兜底：如果语义定位没有候选/没命中，则继续用帧抽样扫描（保持原行为）
                        if found_count < max_hits:
                            for i, item in enumerate(frames_slice):
                                if i % 3 != 0:
                                    continue
                                if not isinstance(item, dict):
                                    continue
                                frame_sample = item.get("frame")
                                frame_no = int(item.get("frame_number", fn))
                                frame_ts = float(item.get("ts", curr_time))

                                window_transcript = _transcript_window(frame_ts, before_s=before_s, after_s=after_s)

                                result = key_moments_manager.analyze_with_multimodal(
                                    frame=frame_sample,
                                    frame_number=frame_no,
                                    timestamp=frame_ts,
                                    transcript_text=window_transcript,
                                    person_count=pc,
                                    track_ids=ti,
                                    video_frames=_video_window_frames(frame_ts, video_before_s, video_after_s),
                                )

                                if result:
                                    print(f"✨ 发现关键时刻! 重要性: {result.get('importance', 0):.2f}")
                                    print(f"   描述: {result.get('description', 'N/A')[:100]}")
                                    found_count += 1
                                    if found_count >= max_hits:
                                        break

                        if found_count == 0:
                            print("🧾 本轮切片：未命中关键时刻（可打开 MULTIMODAL_DEBUG=1 查看每次判定细节）")
                        
                        print(f"✅ 视频切片分析完成")
                    except Exception as e:
                        print(f"⚠️ 视频切片分析错误: {e}")
                        import traceback
                        traceback.print_exc()
                
                threading.Thread(
                    target=do_video_slice_analysis,
                    args=(video_slice_buffer.copy(), recent_transcript, frame_count, person_count, unified_person_ids, current_time),
                    daemon=True
                ).start()
                
                print(f"🤖 触发AI 切片分析 ({int(slice_seconds)}s) (帧 {frame_count}, 视频帧: {len(video_slice_buffer)}, 语音: {len(recent_transcript)} 字)")
                
                # 重置缓冲区
                video_slice_buffer = []
                process_video_stream._last_mm_time = current_time
        
        # 更新统计
        current_stats.update({
            "frame_count": frame_count,
            "person_count": person_count,
            "track_ids": track_ids,
            "fps": round(current_fps, 1)
        })
        
        # 绘制结果
        annotated_frame = frame.copy()
        
        # 为每个person_id分配颜色
        person_colors = {}
        for person_id in range(1, face_db.get_person_count() + 1):
            person_colors[person_id] = COLOR_POOL[(person_id - 1) % len(COLOR_POOL)]
        
        # 绘制每个检测框
        if boxes is not None:
            for box in boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
                track_id = int(box.id.cpu().numpy().item()) if box.id is not None else None
                conf = float(box.conf.cpu().numpy().item())
                
                # 确定颜色和标签
                if track_id in person_face_map:
                    person_id = person_face_map[track_id]
                    person_name = face_db.person_names.get(person_id, f"Person_{person_id}")
                    color = person_colors.get(person_id, (128, 128, 128))
                    label = f"{person_name} ({conf:.2f})"
                else:
                    if track_id is not None:
                        color = COLOR_POOL[track_id % len(COLOR_POOL)]
                        label = f"Track#{track_id} ({conf:.2f})"
                    else:
                        color = (128, 128, 128)
                        label = f"Detected ({conf:.2f})"
                
                # 绘制边框
                cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 3)
                
                # 绘制标签
                label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
                label_y = max(y1 - 10, label_size[1] + 10)
                cv2.rectangle(annotated_frame, 
                             (x1, label_y - label_size[1] - 5), 
                             (x1 + label_size[0] + 5, label_y + 5), 
                             color, -1)
                cv2.putText(annotated_frame, label, (x1 + 2, label_y), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                
                # 更新轨迹
                if track_id is not None:
                    center_x = (x1 + x2) // 2
                    center_y = (y1 + y2) // 2
                    
                    if track_id not in track_trajectories:
                        track_trajectories[track_id] = []
                    
                    track_trajectories[track_id].append((center_x, center_y))
                    
                    if len(track_trajectories[track_id]) > MAX_TRAJECTORY_LENGTH:
                        track_trajectories[track_id].pop(0)
                    
                    # 绘制轨迹
                    if len(track_trajectories[track_id]) > 1:
                        points = track_trajectories[track_id]
                        for j in range(1, len(points)):
                            alpha = j / len(points)
                            thickness = max(1, int(3 * alpha))
                            cv2.line(annotated_frame, points[j-1], points[j], color, thickness)
        
        # 显示统计信息
        info_text = f"Frame: {frame_count} | FPS: {current_fps:.1f} | People: {person_count} | Known: {face_db.get_person_count()}"
        cv2.putText(annotated_frame, info_text, (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # 显示模式
        mode_text = f"Mode: {current_stats['stream_mode'].upper()}"
        cv2.putText(annotated_frame, mode_text, (10, 60), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
        
        # 更新视频流帧 (用于网页显示)
        # 说明：网页端MJPEG如果发太快/压缩太狠，会出现“糊 + 卡”。这里提高质量并允许限宽。
        global current_frame_jpeg, current_frame_seq
        try:
            web_quality = int(os.environ.get('WEB_JPEG_QUALITY', '85'))
        except Exception:
            web_quality = 85
        web_quality = max(40, min(95, web_quality))

        try:
            web_max_w = int(os.environ.get('WEB_JPEG_MAX_WIDTH', '960'))
        except Exception:
            web_max_w = 960
        if web_max_w < 0:
            web_max_w = 0

        web_frame = annotated_frame
        try:
            if web_max_w > 0:
                h0, w0 = web_frame.shape[:2]
                if w0 > web_max_w:
                    scale = float(web_max_w) / float(w0)
                    new_w = int(w0 * scale)
                    new_h = int(h0 * scale)
                    if new_w > 0 and new_h > 0:
                        web_frame = cv2.resize(web_frame, (new_w, new_h), interpolation=cv2.INTER_AREA)
        except Exception:
            web_frame = annotated_frame

        ok, jpeg_data = cv2.imencode('.jpg', web_frame, [cv2.IMWRITE_JPEG_QUALITY, int(web_quality)])
        if ok:
            with frame_lock:
                current_frame_jpeg = jpeg_data.tobytes()
                current_frame_seq += 1
        
        # 显示本地窗口 (如果启用)
        if show_window:
            should_display = True
            if is_video_file:
                should_display = (frame_count % DISPLAY_FRAME_SKIP == 0)
            
            if should_display:
                try:
                    cv2.imshow("Integrated System (按q退出)", annotated_frame)
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord('q'):
                        is_running = False
                        break
                except Exception as e:
                    if frame_count == 1:
                        print(f"⚠️  无法显示窗口: {e}")
        else:
            # 即使不显示窗口,也需要处理事件避免卡死
            cv2.waitKey(1)
        
        # 每100帧打印
        # if frame_count % 100 == 0:
        #     print(f"📊 帧 {frame_count}: {person_count} 人, 已知 {face_db.get_person_count()} 人")
    
    # 清理
    current_stats["status"] = "stopped"
    cap.release()
    cv2.destroyAllWindows()

    # 停止后台服务，避免 Ctrl+C 退出时出现 native 崩溃/卡死
    try:
        shutdown_background_services()
    except Exception:
        pass
    
    print("\n" + "="*60)
    print("📊 最终统计:")
    print(f"  总帧数: {frame_count}")
    print(f"  已识别人数: {face_db.get_person_count()}")
    print(f"  人脸检测次数: {current_stats['face_detections']}")
    print("="*60)
    print("\n🌐 Web服务器仍在运行，可查看结果")
    print("⚠️  按 Ctrl+C 完全退出")
    
    # 保持服务器运行（便于查看结果）；Ctrl+C 时做一次干净退出
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n✅ 用户退出")
        try:
            shutdown_background_services()
        except Exception:
            pass
        return


def shutdown_background_services():
    """尽量干净地停止后台线程/音频资源，避免退出卡死或 BPT trap。"""
    global realtime_asr_engine, meeting_notes_generator, key_moments_manager, microphone_recorder

    # 先停会持续消费音频的模块
    if meeting_notes_generator is not None:
        try:
            meeting_notes_generator.stop()
        except Exception:
            pass

    if realtime_asr_engine is not None:
        try:
            realtime_asr_engine.stop()
        except Exception:
            pass

    if key_moments_manager is not None:
        # 兼容不同版本：可能有 stop/cleanup
        for meth in ("stop", "cleanup"):
            if hasattr(key_moments_manager, meth):
                try:
                    getattr(key_moments_manager, meth)()
                except Exception:
                    pass

    if microphone_recorder is not None:
        try:
            microphone_recorder.stop_recording()
        except Exception:
            pass

    # 最后清理共享音频管理器（会停止 PyAudio stream）
    try:
        from audio_manager import get_audio_manager
        get_audio_manager().cleanup()
    except Exception:
        pass

# ============================================================
# 🚀 主程序
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='智能视频分析与人脸追踪整合系统')
    parser.add_argument('--video', '-v', type=str, help='视频文件路径')
    parser.add_argument('--camera', '-c', type=int, default=0, help='摄像头ID (默认0)')
    parser.add_argument('--obs', action='store_true', help='使用OBS流（虚拟摄像头或RTMP）')
    parser.add_argument('--obs-url', type=str, default='rtmp://localhost/live', 
                       help='OBS RTMP流地址')
    parser.add_argument('--ai', action='store_true', help='启用AI分析（需要API Key）')
    parser.add_argument('--port', type=int, default=8080, help='Web服务器端口')
    parser.add_argument('--no-face', action='store_true', help='禁用人脸识别')
    parser.add_argument('--no-window', action='store_true', help='禁用本地OpenCV窗口(仅使用Web界面)')
    parser.add_argument('--no-browser', action='store_true', help='不自动打开浏览器')
    
    args = parser.parse_args()
    
    print("╔════════════════════════════════════════════════════════╗")
    print("║   🎬 智能视频分析与人脸追踪整合系统                   ║")
    print("║   ONE_KEY + multi_person_tracker                      ║")
    print("╚════════════════════════════════════════════════════════╝\n")
    
    # 🚀 优先启动Web服务器(立即可访问界面)
    print("🌐 启动Web服务器...")
    web_thread = threading.Thread(target=start_web_server, args=(args.port,), daemon=True)
    web_thread.start()
    time.sleep(0.5)  # 减少等待时间
    
    # 自动打开浏览器
    web_url = f"http://localhost:{args.port}/integrated%20final.html"
    if not args.no_browser:
        print(f"✅ Web服务已就绪: {web_url}")
        print("💡 提示: 浏览器打开后,系统将在后台加载模型...")
        webbrowser.open(web_url)
    else:
        print(f"✅ Web服务已就绪: {web_url}")
    
    # 初始化人脸识别(延迟加载,不阻塞启动)
    face_app = None
    face_future = None
    if INSIGHTFACE_AVAILABLE and not args.no_face:
        def load_face_app():
            global FaceAnalysis
            try:
                print("🔧 后台加载InsightFace...")
                from insightface.app import FaceAnalysis as FA
                FaceAnalysis = FA
                # InsightFace 0.2.1版本 - 使用buffalo_l模型
                print("📥 首次使用需要下载模型文件(约200MB),请耐心等待...")
                face_app = FaceAnalysis(name='buffalo_l')
                face_app.prepare(ctx_id=-1, det_size=(640, 640))
                print("✅ InsightFace加载完成")
                return face_app
            except Exception as e:
                print(f"⚠️  InsightFace加载失败: {e}")
                print("💡 提示: 系统将继续使用纯YOLO追踪模式")
                return None
        
        # 在后台线程中加载
        import concurrent.futures
        face_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        face_future = face_executor.submit(load_face_app)
        print("💡 InsightFace将在后台加载...")
    
    # 打开视频源
    try:
        video_source_path = None  # 用于关键时刻音频提取
        
        if args.obs:
            print(f"📡 连接OBS流...")
            cap, fps = VideoSource.open_obs_stream(args.obs_url)
            print("✅ OBS流连接成功")
        elif args.video:
            print(f"📹 打开视频: {args.video}")
            cap, fps = VideoSource.open_video(args.video)
            video_source_path = args.video  # 保存视频源路径用于音频提取
            print(f"✅ 视频打开成功 (FPS: {fps:.1f})")
        else:
            print(f"📷 打开摄像头 #{args.camera}...")
            cap, fps = VideoSource.open_camera(args.camera)
            print("✅ 摄像头打开成功")
        
        if not cap.isOpened():
            print("❌ 无法打开视频源")
            return
        
        # 等待人脸识别加载（如果还在加载）
        if face_future is not None:
            try:
                print("⏳ 等待InsightFace加载完成...")
                face_app = face_future.result(timeout=60)  # 最多等待60秒
                if face_app is None:
                    print("⚠️  人脸识别加载失败，将使用纯视觉模式")
                else:
                    print("✅ 人脸识别已就绪")
            except Exception as e:
                print(f"⚠️  等待人脸识别超时: {e}")
        
        # 开始处理 (传入是否显示窗口和视频源路径)
        show_window = not args.no_window
        try:
            process_video_stream(cap, fps, face_app, args.ai, show_window, video_source_path)
        except KeyboardInterrupt:
            print("\n✅ 用户中断 (Ctrl+C)，正在停止后台服务...")
            try:
                shutdown_background_services()
            except Exception:
                pass
            # macOS 下常见：PyAudio/OpenCV 等 native 资源在解释器收尾时触发 SIGTRAP。
            # 这里做一次“清理后强退”，避免 Trace/BPT trap: 5。
            # 在Linux上也使用 os._exit(0) 以确保所有线程（如ASR、LLM）立即终止，防止挂起
            os._exit(0)
            return
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()
        try:
            shutdown_background_services()
        except Exception:
            pass

if __name__ == '__main__':
    main()
