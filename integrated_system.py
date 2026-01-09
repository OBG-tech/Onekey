#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
�9�0 ������Ƶ����������׷������ϵͳ
��� ONE_KEY �����ܷ��� + multi_person_tracker ��ʵʱ׷��
֧��: ������Ƶ������ͷ��OBSʵʱ��
"""

print("�7�7 ϵͳ������...", end="\r")

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

print("�7�7 ���غ���ģ��...", end="\r")

# YOLO������ (�ӳٵ���,ֻ��ʹ��ʱ����ģ��)
from ultralytics import YOLO

# ��ѡ: InsightFace����ʶ�� - ������ʹ�ô�YOLO׷��ģʽ
INSIGHTFACE_AVAILABLE = False
FaceAnalysis = None
# try:
#     # �ӳٵ���,ֻ����Ҫʱ����
#     import insightface
#     INSIGHTFACE_AVAILABLE = True
#     print("�7�3 InsightFace ����ʶ�����")
# except (ImportError, Exception) as e:
#     INSIGHTFACE_AVAILABLE = False
#     print(f"�7�2�1�5  InsightFace ������: {e}")
print("�9�5 ʹ�ô�YOLO׷��ģʽ (InsightFace�ѽ���)")

# ============================================================
# �9�2 ASR ���ѡ�� (Qwen/DashScope vs FireRedASR)
# ============================================================

# ASR_PROVIDER:
# - qwen: ʹ�� DashScope/Qwen �������� (ͨ��ǧ���ƶ�ʵʱASR���Ƽ�)
# - funasr: ʹ�� FunASR ����ʶ�� (���ֶ���װģ��)
# - fireredasr: ʹ�ñ��� FireRedASR-AED (���������������ƣ�CPUģʽ����)
# Ĭ��ʹ��ͨ��ǧ���ƶ�ʵʱASR���ٶȿ졢׼ȷ�ʸߡ��Զ���㣩
ASR_PROVIDER = os.environ.get("ASR_PROVIDER", "qwen").strip().lower()

# FireRedASR ���ã����� ASR_PROVIDER=fireredasr ʱ��Ч��
FIREREDASR_MODEL_DIR = os.environ.get("FIREREDASR_MODEL_DIR", "pretrained_models/FireRedASR-AED-L")
FIREREDASR_ASR_TYPE = os.environ.get("FIREREDASR_ASR_TYPE", "aed").strip().lower()  # aed | llm
FIREREDASR_USE_GPU = os.environ.get("FIREREDASR_USE_GPU", "0").strip() in {"1", "true", "yes"}
FIREREDASR_BEAM_SIZE = int(os.environ.get("FIREREDASR_BEAM_SIZE", "3"))
FIREREDASR_NBEST = int(os.environ.get("FIREREDASR_NBEST", "1"))

_fireredasr_model_cache = None

def _get_fireredasr_model():
    """�ӳټ��� FireRedASR ģ�ͣ��������棩"""
    global _fireredasr_model_cache
    if _fireredasr_model_cache is not None:
        return _fireredasr_model_cache
    try:
        from fireredasr.models.fireredasr import FireRedAsr
    except Exception:
        # ���ݣ���Ŀ��Ŀ¼��ֱ�� git clone FireRedASR������ pip install��
        project_dir = Path(__file__).parent
        candidates = [project_dir / "FireRedASR", project_dir / "vendor" / "FireRedASR"]
        for c in candidates:
            if c.exists() and str(c) not in sys.path:
                sys.path.insert(0, str(c))
        try:
            from fireredasr.models.fireredasr import FireRedAsr
        except Exception as e:
            raise ImportError(
                "δ��װ fireredasr��FireRedASR����\n"
                "�ο�: https://github.com/FireRedTeam/FireRedASR\n"
                "���ٽ��뷽ʽ����ѡһ����\n"
                "1) ֱ���ڱ���ĿĿ¼��ִ��: git clone https://github.com/FireRedTeam/FireRedASR.git\n"
                "   Ȼ������ FIREREDASR_MODEL_DIR ָ��Ȩ��Ŀ¼��\n"
                "2) �� FireRedASR README �����价������װ������\n"
                f"ԭʼ����: {e}"
            ) from e

    model_dir = FIREREDASR_MODEL_DIR
    if not os.path.exists(model_dir):
        raise FileNotFoundError(
            f"FireRedASR ģ��Ŀ¼������: {model_dir}\n"
            "���ȴ� HuggingFace ����Ȩ�ز��ŵ���Ŀ¼������ FireRedTeam/FireRedASR-AED-L"
        )

    _fireredasr_model_cache = FireRedAsr.from_pretrained(FIREREDASR_ASR_TYPE, model_dir)
    print(f"�7�3 FireRedASR �Ѽ���: type={FIREREDASR_ASR_TYPE}, dir={model_dir}, gpu={FIREREDASR_USE_GPU}")
    return _fireredasr_model_cache

def transcribe_audio_with_fireredasr(wav_path: str) -> str:
    """ʹ�� FireRedASR-AED ����תд��

    ˵����FireRedASR ������ͨ��Ҫ�� 16kHz/mono �� WAV��
    Ϊ����������ϴ��� webm / ������Ƶ��ʽ��������ڱ�Ҫʱ�Զ�ת�롣
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
            print("�7�2�1�5 FireRedASR ��Ҫ WAV(16k/mono)���� ffmpeg ת��ʧ��")
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
        print(f"�7�2�1�5 FireRedASR תдʧ��: {e}")
        return ""
    finally:
        try:
            if converted_path and converted_path != wav_path and os.path.exists(converted_path):
                os.unlink(converted_path)
        except Exception:
            pass

def transcribe_audio(audio_path: str) -> str:
    """ͳһתд��ڣ����� ASR_PROVIDER ѡ���ˡ�"""
    if ASR_PROVIDER == "fireredasr":
        text = transcribe_audio_with_fireredasr(audio_path)
        if text and text.strip():
            return text
        # FireRedASR ������/ʧ��ʱ���������˵��ƶˣ����û������ã�
        return transcribe_audio_with_qwen(audio_path)
    return transcribe_audio_with_qwen(audio_path)

# ��ѡ: AI�������� (֧�� Qwen �� Claude)
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
                print("�7�3 Claude Haiku 4.5 API ����")
            else:
                print("�7�2�1�5  δ���� ANTHROPIC_API_KEY ����������AI�������ܲ�����")
        except ImportError:
            print("�7�2�1�5  Anthropic��δ��װ��pip install anthropic����AI�������ܲ�����")
    else:
        # Qwen provider (default)
        from openai import OpenAI
        if QWEN_API_KEY:
            ONEKEY_AI_AVAILABLE = True
            print("�7�3 Qwen API ����")
        else:
            print("�7�2�1�5  δ���� DASHSCOPE_API_KEY ����������AI�������ܲ�����")
except ImportError:
    print("�7�2�1�5  OpenAI��δ��װ��AI�������ܲ�����")

# �9�3 ˫��ؼ�ʱ��ʶ��ϵͳ
try:
    from key_moments_manager import KeyMomentsManager
    KEY_MOMENTS_AVAILABLE = True
    print("�7�3 �ؼ�ʱ�̹���������")
except ImportError:
    KEY_MOMENTS_AVAILABLE = False
    print("�7�2�1�5  �ؼ�ʱ�̹�����δ��װ")

# �9�2 ʵʱ����ʶ��ϵͳ
REALTIME_ASR_AVAILABLE = False
realtime_asr_engine = None
PYAUDIO_AVAILABLE = False
DASHSCOPE_ASR_AVAILABLE = False
FIREREDASR_ASR_AVAILABLE = False

try:
    from realtime_asr import RealtimeASR, PYAUDIO_AVAILABLE, DASHSCOPE_ASR_AVAILABLE, FIREREDASR_ASR_AVAILABLE
    if PYAUDIO_AVAILABLE and (DASHSCOPE_ASR_AVAILABLE or FIREREDASR_ASR_AVAILABLE):
        REALTIME_ASR_AVAILABLE = True
        print("�7�3 ʵʱ����ʶ�����")
    else:
        print("�7�2�1�5  ʵʱ����ʶ������������")
except (ImportError, Exception) as e:
    print(f"�7�2�1�5  ʵʱ����ʶ��ģ�鵼��ʧ��: {e}")

# �9�2 ��˷�¼��ϵͳ
MICROPHONE_AVAILABLE = False
microphone_recorder = None

try:
    from microphone_recorder import MicrophoneRecorder
    MICROPHONE_AVAILABLE = True
    print("�7�3 ��˷�¼�ƿ���")
except (ImportError, Exception) as e:
    print(f"�7�2�1�5  ��˷�¼��ģ�鵼��ʧ��: {e}")

# �9�5 AI�����Ҫϵͳ
MEETING_NOTES_AVAILABLE = False
meeting_notes_generator = None

try:
    from meeting_notes import MeetingNotesGenerator
    MEETING_NOTES_AVAILABLE = True
    print("�7�3 AI�����Ҫ����������")
except (ImportError, Exception) as e:
    print(f"�7�2�1�5  AI�����Ҫģ�鵼��ʧ��: {e}")

# �9�0 AIֱ����ϵͳ
AI_LIVE_AVAILABLE = False
ai_live_commentary = None

try:
    from ai_live_commentary import AILiveCommentary
    AI_LIVE_AVAILABLE = True
    print("�7�3 AIֱ�������")
except (ImportError, Exception) as e:
    print(f"�7�2�1�5  AIֱ����ģ�鵼��ʧ��: {e}")

# ============================================================
# �9�9 ������
# ============================================================

# ׷������
MODEL_PATH = os.path.expanduser("~/tracker_cache/yolo11n.pt")
if not os.path.exists(MODEL_PATH):
    MODEL_PATH = "models/yolo11n.pt"

# ����ʶ������
FACE_MATCH_THRESHOLD = 0.40
MIN_FACE_SIZE = 40
MIN_FACE_QUALITY = 0.3
SAMPLE_INTERVAL = 2  # ÿ2�����һ�������ͱ���ͼ��
KEYFRAME_INTERVAL = 30  # ÿ30�뱣��һ�ιؼ�֡

# ��ʾ����
DISPLAY_FRAME_SKIP = 2
MAX_TRAJECTORY_LENGTH = 30

# ��ɫ�� (BGR��ʽ)
COLOR_POOL = [
    (147, 20, 255),   # ���ɫ
    (0, 215, 255),    # ��ɫ
    (255, 144, 30),   # ������
    (180, 105, 255),  # �ȷ�ɫ
    (0, 255, 127),    # ����ɫ
    (203, 192, 255),  # ����ɫ
    (19, 69, 139),    # ������
    (255, 191, 0),    # ������
    (42, 42, 165),    # ��ɫ
    (147, 112, 219),  # ����ɫ
]

# Ŀ¼����
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "integrated_data"
FACE_DB_PATH = DATA_DIR / "face_database"
ANALYSIS_PATH = DATA_DIR / "analysis_results"
LOGS_PATH = DATA_DIR / "logs"
ANALYSIS_LOG_FILE = LOGS_PATH / "analysis.log"
KEYFRAME_PATH = DATA_DIR / "key_frames"
SNAPSHOT_PATH = DATA_DIR / "snapshots"
KEY_MOMENTS_PATH = DATA_DIR / "key_moments"  # �ؼ�ʱ��Ŀ¼

# ������ҪĿ¼
for path in [DATA_DIR, FACE_DB_PATH, ANALYSIS_PATH, KEYFRAME_PATH, SNAPSHOT_PATH, KEY_MOMENTS_PATH, LOGS_PATH]:
    path.mkdir(exist_ok=True, parents=True)

# ============================================================
# �9�4 ȫ��״̬
# ============================================================

is_running = True
current_frame_jpeg = None  # �洢��ǰ֡�� JPEG ����������Ƶ��
current_frame_seq = 0  # ÿ�θ���֡+1�����ڱ���MJPEG�ظ�����ͬһ֡
current_frame_raw = None   # �洢ԭʼ֡���ڹؼ�ʱ�̱��
frame_lock = threading.Lock()  # �߳���

# �9�0 ��Ƶ��Ƭ������ (���ڶ�ģ̬ AI ����)
# �ṹ: [{"ts": epoch_seconds, "frame_number": int, "frame": np.ndarray}, ...]
# ��Ҫ������ֻ�� 30 ֡�������� 30fps/ÿ10֡����=3fps �������ֻ���ǡ�10�룬
# �ᵼ�¡���Ƭ����������ʱ��㡱����Ƶ��ֻʣ���롢������ȫ����Ӧ��
video_slice_buffer = []

# Ĭ�ϣ�5fps ������3.5����=1050֡��Ϊ�˿����ڴ棬�洢���ֱ���֡
VIDEO_SLICE_SECONDS = float(os.environ.get("MULTIMODAL_SLICE_SECONDS", "210"))
VIDEO_SLICE_FPS = float(os.environ.get("MULTIMODAL_SLICE_FPS", "5"))  # ��ߵ�5fps�����ɸ�������30����Ƶ
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
    "key_moments_count": 0,     # �ؼ�ʱ������
    "user_anchors_count": 0,    # �û������
    "ai_detected_count": 0      # AIʶ����
}

track_trajectories = {}

# �9�3 �ؼ�ʱ�̹�����ʵ��
key_moments_manager = None

# ============================================================
# �9�6 �������ݿ�
# ============================================================

class FaceDatabase:
    """������������������IDӳ��"""
    def __init__(self):
        self.face_embeddings = []
        self.person_ids = []
        self.person_names = {}
        self.person_images = {}
        self.detection_history = defaultdict(list)
        self.next_person_id = 1
        # �9�4 ��ǰ�Ự��Ծ���� (ÿ������ʱ���)
        self.active_people_this_session = set()  # ֻ��¼���λỰ���ֵ� person_id
        
        # �9�3 ������ʶ��ϵͳ (Re-ID)
        self.person_features = {}  # person_id -> ���������б�
        self.track_to_person_map = {}  # track_id -> person_id ӳ��
        self.person_appearance_history = defaultdict(list)  # person_id -> [track_ids]
    
    def extract_simple_features(self, image):
        """��ȡ�򵥵��Ӿ���������Re-ID (��ɫֱ��ͼ + HOG)"""
        if image is None or image.size == 0:
            return None
        
        try:
            # ������С�Լӿ촦���ٶ�
            img_resized = cv2.resize(image, (128, 256))
            
            # 1. ��ɫֱ��ͼ (HSV�ռ�,���°����ֿ�)
            hsv = cv2.cvtColor(img_resized, cv2.COLOR_BGR2HSV)
            h, w = hsv.shape[:2]
            
            # �ϰ��� (�������·�)
            upper_hist = cv2.calcHist([hsv[:h//2]], [0, 1], None, [30, 32], [0, 180, 0, 256])
            upper_hist = cv2.normalize(upper_hist, upper_hist).flatten()
            
            # �°��� (�����ǿ���)
            lower_hist = cv2.calcHist([hsv[h//2:]], [0, 1], None, [30, 32], [0, 180, 0, 256])
            lower_hist = cv2.normalize(lower_hist, lower_hist).flatten()
            
            # 2. �򵥵��������� (��Ե�ܶ�)
            gray = cv2.cvtColor(img_resized, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 50, 150)
            edge_density = np.sum(edges > 0) / edges.size
            
            # 3. ��������
            brightness = np.mean(gray) / 255.0
            
            # �ϲ�����
            feature = np.concatenate([
                upper_hist * 0.5,  # �ϰ�����ɫȨ�ظ���
                lower_hist * 0.3,
                [edge_density, brightness]
            ])
            
            # L2��һ��
            feature = feature / (np.linalg.norm(feature) + 1e-6)
            
            return feature
        except Exception as e:
            print(f"�7�2�1�5 ������ȡʧ��: {e}")
            return None
    
    def find_matching_person(self, image, threshold=0.65):
        """ͨ���Ӿ���������ƥ���person_id"""
        feature = self.extract_simple_features(image)
        if feature is None:
            return None
        
        best_match_id = None
        best_similarity = 0
        
        for person_id, feature_list in self.person_features.items():
            if len(feature_list) == 0:
                continue
            
            # ������������������������ƶ�
            similarities = [np.dot(feature, f) for f in feature_list]
            max_sim = max(similarities)
            
            if max_sim > best_similarity:
                best_similarity = max_sim
                best_match_id = person_id
        
        if best_similarity >= threshold:
            return best_match_id
        
        return None
    
    def add_person_feature(self, person_id, image):
        """Ϊperson�����µ���������"""
        feature = self.extract_simple_features(image)
        if feature is not None:
            if person_id not in self.person_features:
                self.person_features[person_id] = []
            
            # ����ÿ�������5����������(ȡ��ͬ�Ƕ�/����)
            self.person_features[person_id].append(feature)
            if len(self.person_features[person_id]) > 5:
                self.person_features[person_id].pop(0)
    
    def map_track_to_person(self, track_id, person_id):
        """����track_id��person_id��ӳ��"""
        self.track_to_person_map[track_id] = person_id
        if track_id not in self.person_appearance_history[person_id]:
            self.person_appearance_history[person_id].append(track_id)
    
    def load_from_disk(self):
        """�Ӵ��̼������е�����ͼƬ"""
        try:
            FACE_DB_PATH.mkdir(parents=True, exist_ok=True)
            
            # ɨ�� face_database Ŀ¼�е�����ͼƬ
            image_files = sorted(FACE_DB_PATH.glob("person_*.jpg"))
            
            for img_path in image_files:
                # ���ļ�����ȡ person_id: person_3.jpg -> 3
                filename = img_path.stem  # 'person_3'
                person_id = int(filename.split('_')[1])
                
                # ע��ͼƬ·��
                self.person_images[person_id] = str(img_path)
                
                # ע��Ĭ������
                if person_id not in self.person_names:
                    self.person_names[person_id] = f"Person_{person_id}"
                
                # ���� next_person_id
                if person_id >= self.next_person_id:
                    self.next_person_id = person_id + 1
            
            if len(self.person_images) > 0:
                print(f"�7�3 �Ѽ��� {len(self.person_images)} ������ͼƬ")
        except Exception as e:
            print(f"�7�2�1�5 ��������ͼƬʧ��: {e}")
    
    def find_match(self, embedding, threshold=FACE_MATCH_THRESHOLD):
        """����ƥ�������"""
        if len(self.face_embeddings) == 0:
            return None
        
        # �������ƶ�
        similarities = [np.dot(embedding, emb) for emb in self.face_embeddings]
        max_sim = max(similarities)
        
        if max_sim > threshold:
            max_idx = similarities.index(max_sim)
            return self.person_ids[max_idx]
        return None
    
    def add_face(self, embedding, person_id=None, frame_image=None):
        """����������"""
        if person_id is None:
            person_id = self.next_person_id
            self.next_person_id += 1
            self.person_names[person_id] = f"Person_{person_id}"
        
        self.face_embeddings.append(embedding)
        self.person_ids.append(person_id)
        
        # ��������ͼƬ
        if frame_image is not None:
            img_path = FACE_DB_PATH / f"person_{person_id}.jpg"
            cv2.imwrite(str(img_path), frame_image)
            self.person_images[person_id] = str(img_path)
        
        return person_id
    
    def record_detection(self, person_id, frame_num, bbox, snapshot=None):
        """��¼�����ʷ"""
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
        """ɾ�����Ｐ����������"""
        # ɾ����������
        indices_to_remove = [i for i, pid in enumerate(self.person_ids) if pid == person_id]
        for idx in sorted(indices_to_remove, reverse=True):
            self.face_embeddings.pop(idx)
            self.person_ids.pop(idx)
        
        # ɾ������ͼƬ
        if person_id in self.person_images:
            img_path = Path(self.person_images[person_id])
            if img_path.exists():
                img_path.unlink()
            del self.person_images[person_id]
        
        # ɾ����������
        if person_id in self.person_names:
            del self.person_names[person_id]
        
        # ɾ�������ʷ
        if person_id in self.detection_history:
            # ɾ������
            snapshot_dir = SNAPSHOT_PATH / f"person_{person_id}"
            if snapshot_dir.exists():
                import shutil
                shutil.rmtree(snapshot_dir)
            del self.detection_history[person_id]
        
        print(f"�7�3 ��ɾ������ {person_id} ����������")

face_db = FaceDatabase()
face_db.load_from_disk()  # ����ʱ�������е�����ͼƬ

# ============================================================
# �9�5�1�5  HTTP������ - �������ط��API
# ============================================================

class IntegratedHandler(SimpleHTTPRequestHandler):
    """����API����;�̬�ļ�"""
    
    def log_message(self, format, *args):
        """��д��־������ֻ��ʾ��API����ʹ���"""
        # ���˵�������API��ѯ���󣨽���args[0]���ַ���ʱ��
        if args and isinstance(args[0], str):
            if any(api in args[0] for api in ['/api/stats', '/api/people', '/api/key_moments', 
                                              '/api/realtime_asr/transcript', '/api/realtime_asr/status',
                                              '/api/meeting_notes/current', '/api/video_feed',
                                              '/api/face/', '/api/key_moment_image/', '/api/linkography',
                                              '/api/button_log']):
                return  # ��Ĭ��Щ��ƵAPI����
        # ��ʾ�����������ǹؼ�ʱ�̡�����ASR�ȣ��ʹ���
        super().log_message(format, *args)
    
    def do_GET(self):
        global is_running

        # ���ݴ� query ���������� /api/video_feed?t=...��
        # ���� path ��·��ƥ�䣻ͬʱ�� self.path ��һ�������⾲̬�ļ������� ? �����ļ���
        try:
            from urllib.parse import urlparse
            parsed = urlparse(self.path)
            # ���� query������Ҫ������ API ʹ��
            self._query_string = parsed.query or ""
            self.path = parsed.path
        except Exception:
            self._query_string = ""
        
        if self.path == '/api/stats':
            self.send_json_response(self._get_stats())
            
        elif self.path == '/api/stop':
            self._handle_stop()
            
        elif self.path == '/api/start':
            # ����������Ҫ�������нű�
            self.send_json_response({
                "status": "info",
                "message": "Please restart the script to start tracking again.",
                "command": "cd ~/onekey && source .venv/bin/activate && python3 integrated_system.py --camera 0 --no-window"
            })
            
        elif self.path == '/api/restart':
            # ������������ͻ��˿�������������
            import subprocess
            self.send_json_response({
                "status": "restarting",
                "message": "Restarting system..."
            })
            # �첽����
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
        
        # �9�3 �ؼ�ʱ�� API
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
        
        # �9�2 ����ת���� API
        elif self.path == '/api/transcript':
            self.send_json_response(self._get_transcript())
            
        elif self.path == '/api/meeting_notes':
            self.send_json_response(self._get_meeting_notes())
        
        # �9�2 ʵʱ ASR API
        elif self.path == '/api/realtime_asr/status':
            self.send_json_response(self._get_realtime_asr_status())
            
        elif self.path == '/api/realtime_asr/transcript':
            self.send_json_response(self._get_realtime_asr_transcript())
        # ʵʱ ASR ״̬ (for UI sync)
        elif self.path == '/api/realtime_asr/state':
            self.send_json_response(self._get_realtime_asr_state())
        
        # �9�5 AI�����Ҫ API
        elif self.path == '/api/meeting_notes/status':
            self.send_json_response(self._get_meeting_notes_status())
        
        elif self.path == '/api/meeting_notes/current':
            self.send_json_response(self._get_current_meeting_notes())
            
        else:
            # ��̬�ļ�����
            super().do_GET()

    def _get_query_params(self) -> dict:
        """���� query string �������� do_GET ���ѱ��浽 self._query_string����"""
        try:
            from urllib.parse import parse_qs
            raw = getattr(self, "_query_string", "") or ""
            qs = parse_qs(raw, keep_blank_values=False)
            # ֻȡ��һ��ֵ
            return {k: (v[0] if isinstance(v, list) and v else "") for k, v in qs.items()}
        except Exception:
            return {}
    
    def do_POST(self):
        """���� POST ����"""
        if self.path == '/api/mark_moment' or self.path == '/api/mark_key_moment':
            self._handle_mark_moment()
        elif self.path == '/api/transcribe':
            self._handle_transcribe()
        elif self.path == '/api/generate_notes':
            self._handle_generate_notes()
        # �9�2 ʵʱ ASR ���� API
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
        
        # �9�5 �����б����� API
        elif self.path == '/api/people/clear':
            self._handle_clear_people()
        
        # �9�5 AI�����Ҫ���� API
        elif self.path == '/api/meeting_notes/start':
            self._handle_meeting_notes_start()
        elif self.path == '/api/meeting_notes/stop':
            self._handle_meeting_notes_stop()
        
        # �9�0 AIֱ���� API
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
        """���� OPTIONS ���� (CORS Ԥ��)"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_DELETE(self):
        """���� DELETE ����"""
        print(f"�9�9�1�5  DELETE����: {self.path}")
        
        # ɾ���ؼ�ʱ��: /api/key_moments/{moment_id}
        if self.path.startswith('/api/key_moments/') and '/frame/' not in self.path:
            try:
                moment_id = self.path.split('/')[-1]
                print(f"�9�8 ɾ���ؼ�ʱ��: {moment_id}")
                if KEY_MOMENTS_AVAILABLE and key_moments_manager:
                    key_moments_manager.delete_moment(moment_id)
                    self.send_json_response({
                        "status": "success",
                        "message": f"Moment {moment_id} deleted"
                    })
                    print(f"�7�3 �ɹ�ɾ���ؼ�ʱ�� {moment_id}")
                else:
                    self.send_json_response({
                        "status": "error",
                        "message": "Key moments manager not available"
                    })
            except Exception as e:
                print(f"�7�4 ɾ���ؼ�ʱ�̳���: {e}")
                self.send_json_response({
                    "status": "error",
                    "message": str(e)
                })
        # ɾ�������¼: /api/people/{person_id}
        elif self.path.startswith('/api/people/'):
            try:
                person_id = int(self.path.split('/')[-1])
                face_db.delete_person(person_id)
                self.send_json_response({
                    "status": "success",
                    "message": f"Person {person_id} deleted"
                })
            except Exception as e:
                print(f"�7�4 ɾ���������: {e}")
                self.send_json_response({
                    "status": "error",
                    "message": str(e)
                })
        # ɾ�� timeline ֡: /api/timeline/{person_id}/frame/{frame_num}
        elif '/api/timeline/' in self.path and '/frame/' in self.path:
            try:
                parts = self.path.split('/')
                person_id = int(parts[3])
                frame_num = int(parts[5])
                
                # ɾ���ؼ�ʱ���еĸ�֡
                if KEY_MOMENTS_AVAILABLE and key_moments_manager:
                    key_moments_manager.delete_frame_from_timeline(person_id, frame_num)
                
                self.send_json_response({
                    "status": "success",
                    "message": f"Frame {frame_num} deleted"
                })
            except Exception as e:
                print(f"�7�4 ɾ��֡����: {e}")
                self.send_json_response({
                    "status": "error",
                    "message": str(e)
                })
        else:
            print(f"�7�2�1�5  δƥ���DELETE·��: {self.path}")
            self.send_json_response({
                "status": "error",
                "message": "Not Found"
            })
    
    def _handle_stop(self):
        """����ֹͣ���� - ��ȫֹͣϵͳ"""
        global is_running, realtime_asr_engine, key_moments_manager
        
        print("�0�5 �յ�ֹͣ��������ֹͣ���з���...")
        
        # 1. ֹͣ��Ƶ����ѭ��
        is_running = False
        current_stats["status"] = "stopped"
        
        # 2. ֹͣʵʱ����ʶ��
        if REALTIME_ASR_AVAILABLE and realtime_asr_engine is not None:
            try:
                realtime_asr_engine.stop()
                print("   �7�3 ����ʶ����ֹͣ")
            except Exception as e:
                print(f"   �7�2�1�5 ֹͣ����ʶ��ʱ����: {e}")
        
        # 3. ����ؼ�ʱ������
        if KEY_MOMENTS_AVAILABLE and key_moments_manager is not None:
            try:
                key_moments_manager._save_moments()
                stats = key_moments_manager.get_stats()
                print(f"   �7�3 �ؼ�ʱ���ѱ��� (�� {stats.get('total_moments', 0)} ��)")
            except Exception as e:
                print(f"   �7�2�1�5 ����ؼ�ʱ��ʱ����: {e}")
        
        print("�0�5 ϵͳ����ȫֹͣ")
        
        self.send_json_response({
            "status": "stopped",
            "message": "System completely stopped",
            "saved": True
        })
    
    def send_json_response(self, data):
        """����JSON��Ӧ"""
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def _get_stats(self):
        """��ȡʵʱͳ��"""
        stats = current_stats.copy()
        stats['known_people'] = face_db.get_person_count()
        return stats
    
    def _get_people(self):
        """��ȡ��ʶ����Ա�б� (�����λỰ���ֵ�����)"""
        people = []
        seen_person_ids = set()
        
        # 1. ���λỰ��ʶ�������֪����
        for person_id in face_db.active_people_this_session:
            if person_id in face_db.person_images and person_id not in seen_person_ids:
                # �������person_id������track_ids
                all_tracks = face_db.person_appearance_history.get(person_id, [])
                people.append({
                    "id": person_id,
                    "name": face_db.person_names.get(person_id, f"Person_{person_id}"),
                    "detections": len(all_tracks),
                    "type": "face",
                    "track_count": len(all_tracks)  # ׷�ٴ���
                })
                seen_person_ids.add(person_id)
        
        # 2. ��ǰ��Ծ��׷�ٶ��� - ӳ�䵽��Ӧ��person_id
        current_track_ids = current_stats.get("track_ids", [])
        for track_id in current_track_ids:
            # ��ȡ���track_id��Ӧ��person_id
            person_id = face_db.track_to_person_map.get(track_id, track_id)
            
            # ������person_id��û�����б���
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
        """�ṩ����ͼƬ"""
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
        """��ȡ����ʱ����"""
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
        """�ṩ�ؼ�֡ͼƬ"""
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
        """��ȡAI�����Ĺؼ�֡"""
        import datetime
        keyframes = []
        if KEYFRAME_PATH.exists():
            for kf in sorted(KEYFRAME_PATH.glob("*.jpg")):
                # ��ȡ�ļ��޸�ʱ��
                mtime = os.path.getmtime(kf)
                time_str = datetime.datetime.fromtimestamp(mtime).strftime("%H:%M:%S")
                
                # ���ļ�����ȡ֡��
                frame_num = kf.stem.replace("keyframe_", "")
                
                keyframes.append({
                    "filename": kf.name,
                    "url": f"/api/keyframe/{kf.name}",
                    "timestamp": f"Frame {int(frame_num)} @ {time_str}"
                })
        return {"keyframes": keyframes[-20:], "count": len(keyframes)}  # ��෵��20������
    
    def _serve_keyframe_image(self):
        """�ṩ�ؼ�֡ͼƬ"""
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
        """�ṩ��ƵԴ��Ϣ"""
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
        """�ṩ��Ƶ�ļ�����֧�� Range ������ʵ���϶���������"""
        global key_moments_manager
        try:
            if not key_moments_manager:
                self.send_error(500, "Key moments manager not initialized")
                return
            
            video_path = getattr(key_moments_manager, 'video_source', None)
            if not video_path or not os.path.exists(str(video_path)):
                self.send_error(404, "Video file not found")
                return
            
            # ��ȡ�ļ���С
            file_size = os.path.getsize(video_path)
            
            # ֧�� Range ����
            range_header = self.headers.get('Range')
            if range_header:
                # ���� Range ͷ
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
            
            # ����ļ�����
            if str(video_path).endswith('.mkv'):
                content_type = 'video/x-matroska'
            elif str(video_path).endswith('.mp4'):
                content_type = 'video/mp4'
            elif str(video_path).endswith('.webm'):
                content_type = 'video/webm'
            else:
                content_type = 'video/mp4'  # Ĭ��
            
            self.send_header('Content-type', content_type)
            self.send_header('Accept-Ranges', 'bytes')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Cache-Control', 'no-cache')  # ��Ϊ no-cache ������Ƶ��������
            self.end_headers()
            
            # �ֿ鴫�䣨������ļ�һ���Զ�ȡ��
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
                        # �ͻ��˶Ͽ�����
                        break
                    remaining -= len(chunk)
        except Exception as e:
            print(f"Error serving video source file: {e}")
            import traceback
            traceback.print_exc()
            self.send_error(400)
    
    # ============================================================
    # �9�3 �ؼ�ʱ�� API (˫��ʶ��ϵͳ)
    # ============================================================
    
    def _get_key_moments(self):
        """��ȡ���йؼ�ʱ�� (�û���� + AIʶ��)"""
        global key_moments_manager
        if key_moments_manager is None:
            return {"moments": [], "count": 0, "error": "Key moments manager not initialized"}
        
        # Safety: 如果 moments 为空，则尝试从磁盘重新加载
        if not key_moments_manager.moments:
            try:
                print("⚠️ Key moments list empty, attempting reload from disk...")
                key_moments_manager._load_moments()
            except Exception as e:
                print(f"❌ Failed to reload moments: {e}")

        moments = key_moments_manager.get_moments()
        
        # �0�8 Force Show ALL moments (Disable filtering to match 8084 viewer)
        filtered_moments = moments
        skipped_count = 0

        
        # ����ͼƬ����Ƶ URL
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
        """��ȡbutton_log.txt�ļ������ذ�ť��ѹ��¼"""
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
                    
                    # ������ʽ: "2025-12-15 22:52:19 - ��ť: 1"
                    try:
                        parts = line.split(' - ')
                        if len(parts) >= 2:
                            timestamp_str = parts[0].strip()
                            button_part = parts[1].strip()
                            
                            # ��ȡ��ť����
                            if '��ť:' in button_part or '��ť��' in button_part:
                                button_num = button_part.replace('��ť:', '').replace('��ť��', '').strip().rstrip('.')
                                
                                # ת��ʱ���ΪUnixʱ���
                                from datetime import datetime
                                dt = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                                unix_timestamp = dt.timestamp()
                                
                                button_presses.append({
                                    'timestamp': unix_timestamp,
                                    'datetime': timestamp_str,
                                    'button': button_num
                                })
                    except Exception as e:
                        print(f"������ť��־��ʧ��: {line}, ����: {e}")
                        continue
            
            self.send_json_response(button_presses)
        
        except Exception as e:
            print(f"�7�4 ��ȡ��ť��־ʧ��: {e}")
            self.send_json_response([])
    
    def _handle_analysis_log(self):
        """���ط�����־��analysis.log����ĩβ����"""
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
            print(f"�7�2�1�5 ��ȡ������־ʧ��: {e}")
            self.send_json_response({"lines": [], "path": str(ANALYSIS_LOG_FILE)})
    
    def _handle_key_moments_stats(self):
        """��װͳ�Ʒ���"""
        self.send_json_response(self._get_key_moments_stats())
    
    def _handle_narrative_generation(self):
        """��װ�������ɷ���"""
        self.send_json_response(self._generate_narrative())
    
    def _get_key_moments_stats(self):
        """��ȡ�ؼ�ʱ��ͳ��"""
        global key_moments_manager
        if key_moments_manager is None:
            return {"error": "Key moments manager not initialized"}
        return key_moments_manager.get_stats()
    
    def _generate_narrative(self):
        """�����Ŷ�����"""
        global key_moments_manager
        if key_moments_manager is None:
            return {"error": "Key moments manager not initialized"}
        return key_moments_manager.generate_narrative()

    def _get_linkography(self):
        """���� Linkography ͼ���ݣ�LLM ���ڿ�Ƭ����Ѱ�ҿ�ʱ�̹�ϵ����"""
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
        # ��֤ʱ�����򣬲����ƹ�ģ��Ĭ��ȡ���� N �������� prompt ������
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
        """�ṩ�ؼ�ʱ��ͼƬ"""
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
        """�ṩ�ؼ�ʱ����ƵƬ��"""
        global key_moments_manager
        try:
            moment_id = self.path.split('/')[-1]
            if key_moments_manager is None:
                self.send_error(500, "Key moments manager not initialized")
                return
            
            video_path = key_moments_manager.get_moment_video_path(moment_id)
            if video_path and os.path.exists(video_path):
                # ��ȡ�ļ���С
                file_size = os.path.getsize(video_path)
                
                # ֧�� Range ���� (������Ƶ����)
                range_header = self.headers.get('Range')
                if range_header:
                    # ���� Range ͷ
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
                            # �ͻ��˶Ͽ����ӣ�������������������Ƶseek����ͣ��
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
        """�����û���ǹؼ�ʱ�� (The Anchor - 0.5����ͼê��)"""
        global key_moments_manager, current_frame_raw
        
        try:
            # ��ȡ������
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
            
            # ��ȡ��ǰ֡
            with frame_lock:
                frame = current_frame_raw.copy() if current_frame_raw is not None else None
            
            if frame is None:
                self.send_json_response({
                    "success": False,
                    "error": "No frame available"
                })
                return
            
            # ��ȡ���������תд����
            global transcript_buffer
            now_ts = time.time()

            # 1) ��Ƭ�Σ����ڼ�ʱչʾ������Ϊȫ�������ģ�
            recent_items = transcript_buffer[-10:] if transcript_buffer else []
            recent_transcript = " ".join([
                (t.get("text", "") or "").strip()
                for t in recent_items
                if (t.get("text", "") or "").strip()
            ])

            # ��ע���ף��û�ûд��עʱ���á����ڶ�תд����Ϊ��Ƭ����������ǰ�˳��� No description
            effective_user_note = (user_note or "").strip() or (recent_transcript or "").strip()

            # 2) �������ģ����ں���AI��������д�� moment_id_context.txt��
            # ���ԣ�����ȡ��� N ���ӣ���������/�ַ����޽ضϡ�
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
                # ���ݾ����ݣ�û�� timestamp�����˻������200��
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

            # �����ضϣ�ȡĩβ���������ӽ����������ݣ�
            if len(context_lines) > context_max_lines:
                context_lines = context_lines[-context_max_lines:]

            context_transcript = "\n".join(context_lines)
            if len(context_transcript) > context_max_chars:
                context_transcript = context_transcript[-context_max_chars:]
                context_transcript = "[...context truncated...]\n" + context_transcript

            print(f"�9�0 [�ؼ�ʱ��] ��������(��): {len(recent_transcript)} ��")
            if recent_transcript:
                print(f"�9�0 [�ؼ�ʱ��] ����: {recent_transcript[:100]}...")
            
            # ��ǹؼ�ʱ��
            moment = key_moments_manager.mark_user_anchor(
                frame=frame,
                frame_number=current_stats.get("frame_count", 0),
                person_count=current_stats.get("person_count", 0),
                track_ids=current_stats.get("track_ids", []),
                user_note=effective_user_note,
                transcript=recent_transcript,
                context_transcript=context_transcript
            )
            
            if not moment:
                print("�7�4 Failed to create KeyMoment")
                self.send_json_response({
                    "success": False,
                    "error": "Failed to create moment object"
                })
                return

            # �� AFTER ����롰������(ǰ��)תд�����ùؼ�ʱ�������ܿ����� 15 �����ݡ�
            # ͬʱ�Ѹô���д�� moment.transcript�����������ؼ�ʱ�̶���ASR������������ʵʱ����
            try:
                before_s = float(os.environ.get("KEY_MOMENT_BEFORE_SECONDS", "15"))
                after_s = float(os.environ.get("KEY_MOMENT_AFTER_SECONDS", "15"))

                moment_id = moment.id
                mark_ts = float(moment.timestamp)

                def _delayed_patch_anchor_text():
                    try:
                        # �ȴ�����Ρ������� buffer
                        time.sleep(max(0.0, after_s) + 1.0)

                        start_ts = mark_ts - max(0.0, before_s)
                        print(f"�7�4 [�ӳ��߳�] �ȴ� {after_s} ����봰��תд...")
                        end_ts = mark_ts + max(0.0, after_s)

                        items = transcript_buffer if transcript_buffer else []
                        print(f"�7�4 [�ӳ��߳�] ɸѡʱ�䴰��: [{start_ts:.1f}, {end_ts:.1f}]")
                        window = []
                        for t in items:
                            ts_epoch = t.get("timestamp")
                            try:
                                ts_val = float(ts_epoch)
                            except (TypeError, ValueError):
                                continue
                            if start_ts <= ts_val <= end_ts:
                                window.append(t)
                        print(f"�7�4 [�ӳ��߳�] ɸѡ���: buffer�ܹ� {len(items)} ��, ������ {len(window)} ��")

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

                        # ASR Ԫ��Ϣ��ȡʵʱ ASR ��״̬��������ã�
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
            
            # ����ͳ��
            stats = key_moments_manager.get_stats()
            current_stats["key_moments_count"] = stats.get("total_moments", 0)
            current_stats["user_anchors_count"] = stats.get("user_anchors", 0)
            current_stats["ai_detected_count"] = stats.get("ai_detected", 0)
            
            self.send_json_response({
                "success": True,
                "moment": moment.to_dict(),
                "message": f"�9�2 �ؼ�ʱ���ѱ��: {moment.time_str}"
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
    # �9�2 ����ת���� API
    # ============================================================
    
    def _handle_transcribe(self):
        """������Ƶתд����"""
        global transcript_buffer
        
        try:
            # ���� multipart ��������
            content_type = self.headers.get('Content-Type', '')
            
            if 'multipart/form-data' not in content_type:
                self.send_json_response({"success": False, "error": "��Ҫ multipart/form-data"})
                return
            
            # ��ȡ boundary
            boundary = content_type.split('boundary=')[1] if 'boundary=' in content_type else None
            if not boundary:
                self.send_json_response({"success": False, "error": "ȱ�� boundary"})
                return
            
            # ��ȡ����
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            
            # �򵥽��� multipart ���ݣ���ȡ��Ƶ
            boundary_bytes = f'--{boundary}'.encode()
            parts = body.split(boundary_bytes)
            
            audio_data = None
            for part in parts:
                if b'audio' in part and b'\r\n\r\n' in part:
                    header_end = part.find(b'\r\n\r\n')
                    audio_data = part[header_end + 4:]
                    # �Ƴ���β�� \r\n--
                    if audio_data.endswith(b'\r\n'):
                        audio_data = audio_data[:-2]
                    if audio_data.endswith(b'--'):
                        audio_data = audio_data[:-2]
                    break
            
            if not audio_data:
                self.send_json_response({"success": False, "error": "δ�ҵ���Ƶ����"})
                return
            
            # ������ʱ��Ƶ�ļ�
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as f:
                f.write(audio_data)
                temp_path = f.name
            
            # ���� Qwen ASR ����תд
            text = transcribe_audio(temp_path)
            
            # ɾ����ʱ�ļ�
            os.unlink(temp_path)
            
            if text:
                # ���ӵ�תд������
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
            print(f"תд����: {e}")
            import traceback
            traceback.print_exc()
            self.send_json_response({
                "success": False,
                "error": str(e)
            })
    
    def _handle_generate_notes(self):
        """�������ɻ����Ҫ����"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length).decode('utf-8')
            data = json.loads(body) if body else {}
            
            transcript = data.get('transcript', '')
            mode = data.get('mode', 'realtime')
            
            if len(transcript) < 20:
                self.send_json_response({
                    "success": False,
                    "error": "תд����̫��"
                })
                return
            
            # ���� LLM ���ɻ����Ҫ
            notes = generate_meeting_notes_with_llm(transcript, mode)
            
            if notes:
                self.send_json_response({
                    "success": True,
                    "notes": notes
                })
            else:
                self.send_json_response({
                    "success": False,
                    "error": "����ʧ��"
                })
                
        except Exception as e:
            print(f"���ɻ����Ҫ����: {e}")
            self.send_json_response({
                "success": False,
                "error": str(e)
            })
    
    def _get_transcript(self):
        """��ȡ��ǰתд����"""
        global transcript_buffer
        return {
            "transcript": transcript_buffer,
            "count": len(transcript_buffer)
        }
    
    def _get_meeting_notes(self):
        """��ȡ���ܻ����Ҫ - ��Ϲؼ�ʱ�̺�����תд���ۻ�����"""
        global meeting_notes_cache, meeting_notes_history, key_moments_manager, transcript_buffer
        
        # ����� key_moments_manager��ʹ����������
        if KEY_MOMENTS_AVAILABLE and key_moments_manager is not None:
            try:
                # �������ܻ����Ҫ
                notes = key_moments_manager.generate_meeting_notes(transcript_buffer)
                
                # ���¼�Ҫ���ӵ���ʷ��¼��
                if notes and notes.get("summary"):
                    # ����ʱ���
                    notes["update_time"] = datetime.now().strftime("%H:%M:%S")
                    
                    # ����Ƿ��������� (�����ظ�)
                    if not meeting_notes_history or \
                       meeting_notes_history[-1].get("summary") != notes.get("summary"):
                        meeting_notes_history.append(notes.copy())
                        # �������20����ʷ��¼
                        if len(meeting_notes_history) > 20:
                            meeting_notes_history.pop(0)
                
                meeting_notes_cache = notes
                
                # ���ذ�����ʷ��������Ҫ
                return {
                    "current": notes,
                    "history": meeting_notes_history,
                    "total_updates": len(meeting_notes_history),
                    "status": "active"
                }
            except Exception as e:
                print(f"�7�2�1�5 ���ɻ����Ҫʧ��: {e}")
                
        # ���˵�����������Ҫ
        if meeting_notes_cache:
            return {
                "current": meeting_notes_cache,
                "history": meeting_notes_history,
                "total_updates": len(meeting_notes_history),
                "status": "cached"
            }
            
        return {
            "current": {
                "summary": "��������У���Ҫ�������㹻���ݺ�����...",
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
    # �9�2 ʵʱ ASR API ����
    # ============================================================
    
    def _get_realtime_asr_status(self):
        """��ȡʵʱ ASR ״̬"""
        global realtime_asr_engine
        
        if not REALTIME_ASR_AVAILABLE:
            return {
                "available": False,
                "error": "ʵʱ����ʶ��ģ�鲻���ã��밲װ pyaudio �� dashscope"
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
        """��ȡʵʱתд����"""
        global realtime_asr_engine, transcript_buffer
        
        if realtime_asr_engine is None:
            return {
                "success": False,
                "transcript": "",
                "segments": [],
                "error": "ASR engine not started"
            }
        
        state = realtime_asr_engine.get_status()
        
        # ��transcript_buffer��ȡ����ʵʱתд����
        realtime_segments = [t for t in transcript_buffer if t.get("source") == "realtime"]
        transcript_text = "\n".join([f"[{s['time']}] {s['text']}" for s in realtime_segments])
        
        # ����е�ǰ����ʶ����ı�,Ҳ��ʾ����
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
        """����ʵʱ ASR"""
        global realtime_asr_engine, transcript_buffer
        
        if not REALTIME_ASR_AVAILABLE:
            self.send_json_response({
                "success": False,
                "error": "ʵʱ����ʶ�𲻿���"
            })
            return
        
        try:
            # ��������������
            if realtime_asr_engine is None:
                realtime_asr_engine = RealtimeASR()
                
                # ���ûص� - ��תд���ͬ���� transcript_buffer
                def on_transcript_update(text: str, is_final: bool, timestamp: float = None):
                    global transcript_buffer
                    if not text.strip():
                        return
                    
                    from datetime import datetime
                    ts = timestamp if timestamp is not None else time.time()

                    # ͳһʹ�á���ԻỰ��㡱��ʱ�䣬���� 16:03:43 vs 00:09:57 ������
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
                        # ���ս�����Ƴ����һ����ʱ��¼������У����������ռ�¼
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
                        # ��ʱ��������»�������ʱ��¼
                        if transcript_buffer and transcript_buffer[-1].get("is_temporary"):
                            # �������һ����ʱ��¼
                            transcript_buffer[-1]["text"] = text.strip()
                            transcript_buffer[-1]["time"] = time_str
                            transcript_buffer[-1]["time_wall"] = wall_time_str
                            transcript_buffer[-1]["timestamp"] = ts
                        else:
                            # �����µ���ʱ��¼
                            transcript_buffer.append({
                                "time": time_str,
                                "time_wall": wall_time_str,
                                "timestamp": ts,
                                "text": text.strip(),
                                "source": "realtime",
                                "is_temporary": True
                            })
                
                realtime_asr_engine.on_transcript_update = on_transcript_update
            
            # ����
            success = realtime_asr_engine.start()
            
            self.send_json_response({
                "success": success,
                "message": "Real-time ASR started" if success else "Start failed"
            })
            
        except Exception as e:
            print(f"����ʵʱ ASR ����: {e}")
            import traceback
            traceback.print_exc()
            self.send_json_response({
                "success": False,
                "error": str(e)
            })
    
    def _handle_realtime_asr_stop(self):
        """ֹͣʵʱ ASR"""
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
        """��ͣʵʱ ASR"""
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
        """�ָ�ʵʱ ASR"""
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
        """���תд��¼"""
        global realtime_asr_engine, transcript_buffer
        
        if realtime_asr_engine:
            realtime_asr_engine.clear_transcript()
        
        # ͬʱ��� transcript_buffer �е�ʵʱתд
        transcript_buffer = [t for t in transcript_buffer if t.get("source") != "realtime"]
        
        self.send_json_response({
            "success": True,
            "message": "Transcript cleared"
        })

    def _get_realtime_asr_state(self):
        """����ʵʱ ASR ��ǰ����״̬������ǰ�˶�ͻ���ͬ��"""
        global realtime_asr_engine, transcript_buffer
        try:
            running = bool(realtime_asr_engine and getattr(realtime_asr_engine, 'is_recording', False))
            current_text = getattr(realtime_asr_engine, 'current_text', "") if realtime_asr_engine else ""
        except Exception:
            running = False
            current_text = ""

        # Calculate segment count from buffer
        realtime_segments = [t for t in transcript_buffer if t.get("source") == "realtime"]
        segment_count = len(realtime_segments)

        return {
            "success": True,
            "running": running,
            "segment_count": segment_count,
            "current_text": current_text
        }
    
    def _handle_clear_people(self):
        """��յ�ǰ�Ự�������б�"""
        global face_db
        
        try:
            # ��ձ��λỰ�Ļ�Ծ�����б�
            cleared_count = len(face_db.active_people_this_session)
            face_db.active_people_this_session.clear()
            
            print(f"�9�4 ����������б� (��� {cleared_count} ��)")
            
            self.send_json_response({
                "success": True,
                "message": f"����������б� (��� {cleared_count} ��)",
                "cleared_count": cleared_count
            })
        except Exception as e:
            print(f"�7�4 ��������б�ʧ��: {e}")
            self.send_json_response({
                "success": False,
                "error": str(e)
            })
    
    def _get_meeting_notes_status(self):
        """��ȡ�����Ҫ������״̬"""
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
        """��ȡ��ǰ�����Ҫ"""
        global meeting_notes_generator
        
        if meeting_notes_generator is None:
            return {
                "success": False,
                "error": "�����Ҫ������δ����"
            }
        
        notes = meeting_notes_generator.get_current_notes()
        return {
            "success": True,
            **notes
        }
    
    def _handle_meeting_notes_start(self):
        """����AI�����Ҫ����"""
        global meeting_notes_generator, realtime_asr_engine
        
        if not MEETING_NOTES_AVAILABLE:
            self.send_json_response({
                "success": False,
                "error": "AI meeting notes unavailable"
            })
            return
        
        try:
            # ȷ��ASR����������
            if realtime_asr_engine is None or not realtime_asr_engine.is_recording:
                self.send_json_response({
                    "success": False,
                    "error": "��������ʵʱ����ʶ��"
                })
                return
            
            # ���������Ҫ������
            if meeting_notes_generator is None:
                meeting_notes_generator = MeetingNotesGenerator(
                    output_dir=DATA_DIR / "meeting_notes",
                    asr_engine=realtime_asr_engine
                )
            
            # ��������
            success = meeting_notes_generator.start()
            
            self.send_json_response({
                "success": success,
                "message": "AI meeting notes generation started" if success else "Start failed"
            })
            
        except Exception as e:
            print(f"���������Ҫ���ɴ���: {e}")
            import traceback
            traceback.print_exc()
            self.send_json_response({
                "success": False,
                "error": str(e)
            })
    
    def _handle_meeting_notes_stop(self):
        """ֹͣAI�����Ҫ����"""
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
        """����AIֱ����"""
        global ai_live_commentary
        
        if not AI_LIVE_AVAILABLE:
            self.send_json_response({
                "success": False,
                "error": "AIֱ���䲻����"
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
        """ֹͣAIֱ����"""
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
        """����AI����"""
        global ai_live_commentary, transcript_buffer, key_moments_manager
        
        if not AI_LIVE_AVAILABLE or ai_live_commentary is None:
            self.send_json_response({
                "success": False,
                "error": "AIֱ����δ����"
            })
            return
        
        try:
            # ��ȡ���תд�����30�룩
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
            
            # �������Ƿ��йؼ�ʱ�̣�60���ڣ�
            key_moment_detected = False
            latest_moment_desc = ""
            if KEY_MOMENTS_AVAILABLE and key_moments_manager:
                try:
                    moments = key_moments_manager.get_moments()
                    if moments:
                        # ������¹ؼ�ʱ��
                        latest = moments[-1]
                        moment_time = latest.get('timestamp', 0)
                        if isinstance(moment_time, (int, float)) and (time.time() - moment_time < 60):
                            key_moment_detected = True
                            latest_moment_desc = latest.get('description', '') or latest.get('tagline', '')
                except Exception:
                    pass
            
            # ����������
            context = {
                'recent_transcript': recent_transcript,
                'key_moment_detected': key_moment_detected,
                'key_moment_desc': latest_moment_desc  # �������ؼ�ʱ������
            }
            
            # ��������
            result = ai_live_commentary.generate_commentary(context)
            
            # ת��ΪJSON�����л���ʽ
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
            print(f"����AI���۴���: {e}")
            import traceback
            traceback.print_exc()
            self.send_json_response({
                "success": False,
                "error": str(e)
            })
    
    def _handle_ai_live_status(self):
        """��ȡAIֱ����״̬"""
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
        """�ṩ MJPEG ��Ƶ��"""
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
                
                # �����û��֡����˯�ߵȴ�
                if frame_data is None:
                    time.sleep(min(0.05, interval))
                    continue

                # �����ظ�����ͬһ֡���������������ѹ�������͡���/�����Ĺ۸У�
                if seq == last_sent_seq:
                    time.sleep(min(0.02, interval))
                    continue

                # ������Ŀ��FPS������˷��ͽ�����ȣ�
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
            pass  # �ͻ��˶Ͽ�����


# ============================================================
# �9�2 ����ת���ֹ��� (Qwen ASR)
# ============================================================

transcript_buffer = []  # תд������
meeting_notes_cache = {}  # �����Ҫ����
meeting_notes_history = []  # �9�5 ��Ҫ��ʷ��¼ (�ۻ�����)

def transcribe_audio_with_qwen(audio_path: str) -> str:
    """ʹ�� Qwen ASR תд��Ƶ"""
    if not ONEKEY_AI_AVAILABLE:
        print("�7�2�1�5 Qwen API �����ã�����תд")
        return ""
    
    try:
        import subprocess
        
        # ��ת��Ϊ wav ��ʽ
        wav_path = audio_path.replace('.webm', '.wav')
        result = subprocess.run([
            'ffmpeg', '-y', '-i', audio_path, 
            '-ar', '16000', '-ac', '1', '-f', 'wav', wav_path
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode != 0:
            print(f"ffmpeg ת��ʧ��: {result.stderr}")
            return ""
        
        # ����ļ���С
        file_size = os.path.getsize(wav_path)
        if file_size < 1000:  # С��1KB˵������û����
            os.unlink(wav_path)
            return ""
        
        # ����1: ʹ�� DashScope ԭ�� Paraformer ASR API
        try:
            import dashscope
            from dashscope.audio.asr import Transcription
            
            dashscope.api_key = QWEN_API_KEY
            
            # ʹ�ñ����ļ�תд
            task = Transcription.async_call(
                model='paraformer-v2',
                file_urls=[f'file://{wav_path}'],
                language_hints=['zh', 'en']
            )
            
            # �ȴ����
            result = Transcription.wait(task)
            
            if result.status_code == 200:
                text = ""
                for r in result.output.get('results', []):
                    text += r.get('transcription_text', '')
                
                os.unlink(wav_path)
                
                if text.strip():
                    print(f"�9�2 תд: {text[:50]}...")
                    return text.strip()
                return ""
            else:
                print(f"ASR ʧ��: {result.message}")
        except ImportError:
            print("dashscope δ��װ��ʹ�ñ��÷���")
        except Exception as e:
            print(f"DashScope ASR ����: {e}")
        
        # ����2: ʹ�� Qwen-Audio-Turbo (���� OpenAI ��ʽ)
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
                model=os.environ.get("AUDIO_MODEL", "qwen2-audio-instruct"),
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "audio_url", "audio_url": {"url": f"data:audio/wav;base64,{audio_base64}"}},
                            {"type": "text", "text": "�뽫�����ƵתдΪ���֡�ֻ���תд���������ݣ���Ҫ�����κν��͡�"}
                        ]
                    }
                ],
                max_tokens=500,
                timeout=30
            )
            
            text = response.choices[0].message.content.strip()
            os.unlink(wav_path)
            
            # ������Ч���
            invalid_responses = ['��', '��', 'û������', '����������', '', '�����Ƶû����������', '�޷�ʶ��']
            if any(inv in text for inv in invalid_responses):
                return ""
            
            print(f"�9�2 תд: {text[:50]}...")
            return text
            
        except Exception as e:
            print(f"Qwen Audio תд����: {e}")
            if os.path.exists(wav_path):
                os.unlink(wav_path)
            return ""
        
    except Exception as e:
        print(f"תд����: {e}")
        import traceback
        traceback.print_exc()
        return ""


def generate_meeting_notes_with_llm(transcript: str, mode: str = 'realtime') -> dict:
    """ʹ�� LLM ���ɻ����Ҫ��֧�� Qwen �� Claude��"""
    global meeting_notes_cache
    
    if not ONEKEY_AI_AVAILABLE:
        provider_name = "Claude" if LLM_PROVIDER.startswith("claude") else "Qwen"
        return {"error": f"{provider_name} API ������"}
    
    try:
        # ���� prompt
        if mode == 'realtime':
            prompt = f"""��������»���תд���ݣ����ɼ���ʵʱ�����Ҫ��

תд����:
{transcript}

���� JSON ��ʽ����:
{{
    "summary": "һ�仰������ǰ��������",
    "key_points": ["Ҫ��1", "Ҫ��2"],
    "action_items": ["��������1"],
    "decisions": ["����1"]
}}

ֻ���� JSON����Ҫ�������ݡ��������̫���޷���ȡ�����ؿ����顣"""
        else:
            prompt = f"""�����������������תд���ݣ�������ϸ�Ļ����Ҫ��

תд����:
{transcript}

���� JSON ��ʽ����:
{{
    "summary": "��������ժҪ��2-3�仰��",
    "key_points": ["����Ҫ��1", "����Ҫ��2", "����Ҫ��3"],
    "action_items": ["��������1: ������", "��������2: ������"],
    "decisions": ["����1", "����2"],
    "participants_insights": ["�����߹۵�1", "�����߹۵�2"]
}}

ֻ���� JSON����Ҫ�������ݡ�"""
        
        # ���� provider ���ò�ͬ�� API
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
                timeout=30  # ��ʽ���ó�ʱ
            )
            result_text = response.choices[0].message.content.strip()
        
        # ���� JSON
        if result_text.startswith("```"):
            result_text = result_text.split("```")[1]
            if result_text.startswith("json"):
                result_text = result_text[4:]
        
        notes = json.loads(result_text)
        
        # ������
        meeting_notes_cache = notes
        meeting_notes_cache["updated_at"] = datetime.now().isoformat()
        
        print(f"�9�5 �����Ҫ������")
        return notes
        
    except Exception as e:
        print(f"���ɻ����Ҫ����: {e}")
        return {"error": str(e)}


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    """���߳� HTTP ��������֧��ͬʱ�����������"""
    daemon_threads = True

def start_web_server(port=8080):
    """����Web�����������̣߳�"""
    os.chdir(str(BASE_DIR))
    server = ThreadingHTTPServer(('0.0.0.0', port), IntegratedHandler)
    print(f"�9�4 Web����: http://localhost:{port}/integrated%20final.html")
    server.serve_forever()

# ============================================================
# �9�3 ��ƵԴ���� - ֧��OBS
# ============================================================

class VideoSource:
    """ͳһ����ƵԴ����"""
    
    @staticmethod
    def open_camera(camera_id=0):
        """������ͷ"""
        cap = cv2.VideoCapture(camera_id)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        current_stats["stream_mode"] = "camera"
        return cap, 30
    
    @staticmethod
    def open_video(video_path):
        """����Ƶ�ļ�"""
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        current_stats["stream_mode"] = "video"
        return cap, fps
    
    @staticmethod
    def open_obs_stream(url="rtmp://localhost/live"):
        """
        ��OBS����
        OBS����:
        1. ���� -> ����
        2. ����: �Զ���
        3. ������: rtmp://localhost/live
        4. ������Կ: stream
        
        ��ʹ����������ͷ:
        OBS -> ���� -> ��������ͷ -> ����
        """
        import glob
        import subprocess
        
        # ��ʽ1: RTMP�� (��Ҫnginx-rtmp��������ý�������)
        cap = cv2.VideoCapture(url)
        
        # ��ʽ2: OBS��������ͷ (����)
        if not cap.isOpened():
            print("�7�2�1�5  RTMP������ʧ�ܣ�����OBS��������ͷ...")
            
            # ���� v4l2loopback �豸 (OBS ��������ͷ)
            video_devices = sorted(glob.glob("/dev/video*"), key=lambda x: int(x.replace("/dev/video", "")))
            obs_device_path = None
            obs_device_idx = None
            
            # ����ͨ����������ʶ�� v4l2loopback �豸
            for device in video_devices:
                try:
                    idx = int(device.replace("/dev/video", ""))
                    # ʹ�� v4l2-ctl �����������
                    result = subprocess.run(
                        ["v4l2-ctl", "-d", device, "--info"],
                        capture_output=True, text=True, timeout=2
                    )
                    if "v4l2 loopback" in result.stdout.lower() or "obs" in result.stdout.lower():
                        obs_device_path = device
                        obs_device_idx = idx
                        print(f"�9�3 ��⵽ OBS ��������ͷ: {device}")
                        break
                except Exception:
                    continue
            
            # �9�9 �� Jetson Orin ��ƽ̨�ϣ�ʹ�� GStreamer pipeline ���� YUYV ��ʽ
            if obs_device_path is not None:
                # ����1: ʹ�� GStreamer pipeline (��� YUYV ��ʽ��������)
                gst_pipeline = (
                    f"v4l2src device={obs_device_path} ! "
                    "video/x-raw,format=YUY2 ! "
                    "videoconvert ! "
                    "video/x-raw,format=BGR ! "
                    "appsink drop=1"
                )
                print(f"�0�4 ���� GStreamer pipeline: {obs_device_path}")
                cap = cv2.VideoCapture(gst_pipeline, cv2.CAP_GSTREAMER)
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        print(f"�7�3 GStreamer �ɹ��� OBS ��������ͷ (�豸 {obs_device_idx})")
                        current_stats["stream_mode"] = "obs"
                        return cap, 30
                    cap.release()
                    print("�7�2�1�5  GStreamer �򿪳ɹ����޷���ȡ֡")
                else:
                    print("�7�2�1�5  GStreamer pipeline ��ʧ�ܣ�����ֱ�� V4L2...")
                
                # ����2: ֱ��ʹ�� V4L2 (��ͳ��ʽ)
                cap = cv2.VideoCapture(obs_device_idx, cv2.CAP_V4L2)
                if cap.isOpened():
                    # ���ý�С�ķֱ�������߼�����
                    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
                    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
                    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # ���ٻ����ӳ�
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        print(f"�7�3 V4L2 �ɹ��� OBS ��������ͷ (�豸 {obs_device_idx})")
                        current_stats["stream_mode"] = "obs"
                        return cap, 30
                    cap.release()
                
                # ����3: ��ָ����� (OpenCV �Զ�ѡ��)
                cap = cv2.VideoCapture(obs_device_idx)
                if cap.isOpened():
                    ret, frame = cap.read()
                    if ret and frame is not None:
                        print(f"�7�3 �ɹ��� OBS ��������ͷ (�豸 {obs_device_idx})")
                        current_stats["stream_mode"] = "obs"
                        return cap, 30
                    cap.release()
            
            # �󱸣��Ӹ��豸�ſ�ʼ���ԣ�v4l2loopback ͨ���ڽϸ��豸�ţ�
            for i in range(15, -1, -1):
                try:
                    # ����ʹ�� GStreamer
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
                            print(f"�7�3 GStreamer �ҵ���������ͷ (�豸 {i})")
                            current_stats["stream_mode"] = "obs"
                            return cap, 30
                        cap.release()
                    
                    # ��ֱ�Ӵ�
                    cap = cv2.VideoCapture(i)
                    if cap.isOpened():
                        ret, frame = cap.read()
                        if ret and frame is not None:
                            print(f"�7�3 �ҵ���������ͷ (�豸 {i})")
                            current_stats["stream_mode"] = "obs"
                            return cap, 30
                        cap.release()
                except Exception:
                    continue
        
        if cap.isOpened():
            current_stats["stream_mode"] = "obs"
            return cap, 30
        
        raise ValueError("�޷�����OBS������ȷ��OBS��������ͷ������")

# ============================================================
# �9�3 ����ʶ����
# ============================================================

def process_face_recognition(frame, boxes, frame_count, face_app):
    """��������ʶ��"""
    if not INSIGHTFACE_AVAILABLE or face_app is None or boxes is None:
        return {}
    
    person_face_map = {}
    
    for box in boxes:
        x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
        track_id = int(box.id.cpu().numpy().item()) if box.id is not None else None
        
        if track_id is None:
            continue
        
        # ��ȡ��������
        person_crop = frame[y1:y2, x1:x2]
        if person_crop.size == 0:
            continue
        
        # �������
        faces = face_app.get(person_crop)
        if len(faces) == 0:
            continue
        
        # ȡ�������
        face = max(faces, key=lambda x: (x.bbox[2] - x.bbox[0]) * (x.bbox[3] - x.bbox[1]))
        
        # �����������
        face_width = face.bbox[2] - face.bbox[0]
        face_height = face.bbox[3] - face.bbox[1]
        
        if face_width < MIN_FACE_SIZE or face_height < MIN_FACE_SIZE:
            continue
        if hasattr(face, 'det_score') and face.det_score < MIN_FACE_QUALITY:
            continue
        
        # ��ȡ��������
        embedding = face.embedding
        embedding = embedding / np.linalg.norm(embedding)
        
        # ����ƥ��
        person_id = face_db.find_match(embedding)
        
        if person_id is None:
            # ��ȡ����ͼ��
            fx1, fy1, fx2, fy2 = map(int, face.bbox)
            fx1, fy1 = max(0, fx1), max(0, fy1)
            fx2 = min(person_crop.shape[1], fx2)
            fy2 = min(person_crop.shape[0], fy2)
            face_crop = person_crop[fy1:fy2, fx1:fx2]
            
            if face_crop.size > 0:
                person_id = face_db.add_face(embedding, frame_image=face_crop)
                print(f"�9�5 New person found: Person_{person_id}")
        
        # ��¼���
        snapshot = frame.copy() if frame_count % 30 == 0 else None
        face_db.record_detection(person_id, frame_count, (x1, y1, x2, y2), snapshot)
        person_face_map[track_id] = person_id
        current_stats['face_detections'] += 1
        
        # �9�4 ���Ϊ���λỰ��Ծ����
        face_db.active_people_this_session.add(person_id)
    
    return person_face_map

# ============================================================
# �9�0 ������ѭ��
# ============================================================

# ȫ��ģ�ͻ���
_yolo_model_cache = None
YOLO_DEVICE = "cpu"

def get_yolo_model():
    """�ӳټ���YOLOģ��(����ģʽ)���Զ�ʹ��GPU����"""  
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
            print(f"�7�2�1�5 OpenVINO Check Error: {e}")

        # 2. Device Selection
        if hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
            YOLO_DEVICE = "mps"
            print("�0�4 �״μ���YOLOģ��(MPS GPU����)...")
            _yolo_model_cache = YOLO(MODEL_PATH)
            _yolo_model_cache.to(YOLO_DEVICE)
        elif torch.cuda.is_available():
            YOLO_DEVICE = "cuda"
            print("�0�4 �״μ���YOLOģ��(CUDA GPU����)...")
            _yolo_model_cache = YOLO(MODEL_PATH)
            _yolo_model_cache.to(YOLO_DEVICE)
        elif use_openvino:
            print(f"�0�4 �״μ���YOLOģ��(OpenVINO AMD GPU����)...")
            # MODEL_PATH usually models/yolo11n.pt
            # Export path usually models/yolo11n_openvino_model
            ov_path = os.path.splitext(MODEL_PATH)[0] + "_openvino_model"
            
            if not os.path.exists(ov_path):
                print(f"�7�2�1�5 ���ڵ��� OpenVINO ģ��: {ov_path}")
                try:
                    YOLO(MODEL_PATH).export(format="openvino")
                except Exception as e:
                    print(f"�7�4 ����ʧ��: {e}, ���˵�CPU")
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
            print("�0�4 �״μ���YOLOģ��(CPU)...")
            _yolo_model_cache = YOLO(MODEL_PATH)
            _yolo_model_cache.to(YOLO_DEVICE)
        
        print(f"�7�3 YOLOģ�ͼ������ (Device: {YOLO_DEVICE})")
    return _yolo_model_cache

def process_video_stream(cap, video_fps, face_app=None, enable_ai=False, show_window=True, video_source_path=None):
    """������Ƶ��"""
    global is_running, key_moments_manager, current_frame_raw, microphone_recorder
    
    # �ӳټ���YOLOģ��
    model = get_yolo_model()
    
    # �9�2 ������˷�¼�ƣ�����ͷģʽ��
    if MICROPHONE_AVAILABLE and not video_source_path:
        try:
            microphone_recorder = MicrophoneRecorder(output_dir=DATA_DIR / "audio")
            if microphone_recorder.start_recording():
                print("�7�3 ��˷�¼��������")
        except Exception as e:
            print(f"�7�2�1�5  ��˷�����ʧ��: {e}")
            microphone_recorder = None
    
    # �9�3 ��ʼ���ؼ�ʱ�̹����� (������ƵԴ������Ƶ��ȡ)
    if KEY_MOMENTS_AVAILABLE:
        key_moments_manager = KeyMomentsManager(
            data_dir=DATA_DIR,
            video_source=video_source_path,
            microphone_recorder=microphone_recorder,  # ������˷�¼����
            video_fps=video_fps
        )
    
    frame_count = 0
    fps_start_time = time.time()
    fps_frame_count = 0
    current_fps = 0
    last_sample_time = 0
    process_start_time = time.time()
    
    is_video_file = current_stats["stream_mode"] == "video"
    
    print(f"�7�3 ϵͳ����!")
    print(f"�9�6 ��ƵԴ: {current_stats['stream_mode']}")
    print(f"�9�3 ����ʶ��: {'����' if INSIGHTFACE_AVAILABLE else '����'}")
    print(f"�0�6 AI����: {'����' if enable_ai and ONEKEY_AI_AVAILABLE else '����'}")
    print(f"�9�2 �ؼ�ʱ�̱��: {'����' if KEY_MOMENTS_AVAILABLE else '����'}")
    print("�9�4 �� 'q' �˳� | Web����ɲ鿴ʵʱ����")
    
    current_stats["status"] = "running"

    while cap.isOpened() and is_running:
        success, frame = cap.read()
        
        if not success:
            print("�7�4 ��ȡ֡ʧ��")
            break
        
        frame_count += 1
        fps_frame_count += 1
        
        # ����ԭʼ֡���ڹؼ�ʱ�̱��
        with frame_lock:
            current_frame_raw = frame.copy()
        
        # ����FPS
        if fps_frame_count >= 30:
            elapsed = time.time() - fps_start_time
            current_fps = fps_frame_count / elapsed if elapsed > 0 else 0
            fps_start_time = time.time()
            fps_frame_count = 0
        
        # YOLO׷��
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
        
        # ����ʶ�����
        current_time = time.time()
        person_face_map = {}
        
        if current_time - last_sample_time >= SAMPLE_INTERVAL and person_count > 0:
            person_face_map = process_face_recognition(frame, boxes, frame_count, face_app)
            last_sample_time = current_time
            
            # �9�5 ��YOLOģʽ + Re-ID: ����ƥ��ͱ�������ͼ��
            if not INSIGHTFACE_AVAILABLE and boxes is not None:
                # print(f"�9�3 �������: {len(boxes)} ������, Track IDs: {track_ids}")
                
                # ��¼��ǰ֡�ѷ����person_id����ֹͬһ֡����ͬһ����
                assigned_person_ids_this_frame = set()
                
                for box in boxes:
                    if box.id is not None:
                        track_id = int(box.id.cpu().numpy().item())
                        
                        # �ü�����ͼ��
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
                        
                        # �9�3 Re-ID: ����Ƿ��Ѿ����������
                        if track_id in face_db.track_to_person_map:
                            # ��֪��track_id,ֱ��ʹ��ӳ���person_id
                            person_id = face_db.track_to_person_map[track_id]
                            # ����������
                            face_db.add_person_feature(person_id, person_crop)
                        else:
                            # �µ�track_id,����ͨ���Ӿ�����ƥ����֪����
                            # �����ֵ�� 0.75 �Լ�����ƥ��
                            matched_person_id = face_db.find_matching_person(person_crop, threshold=0.75)
                            
                            # �ؼ�����: ���ƥ�䵽�����Ѿ��ڵ�ǰ֡���ֹ������ܸ��ø�ID (����Լ��)
                            if matched_person_id is not None and matched_person_id in assigned_person_ids_this_frame:
                                matched_person_id = None
                            
                            if matched_person_id is not None:
                                # �ҵ�ƥ��!����һ����֪����
                                person_id = matched_person_id
                                face_db.map_track_to_person(track_id, person_id)
                                face_db.add_person_feature(person_id, person_crop)
                                print(f"�9�3 Re-IDƥ��: Track#{track_id} -> Person_{person_id}")
                            else:
                                # ȫ�µ�����,������ID
                                person_id = track_id  # ʹ��track_id��Ϊperson_id
                                # �����ID�ѱ�ռ��(�������),������
                                while person_id in face_db.person_names or person_id in assigned_person_ids_this_frame:
                                    person_id += 1000
                                    
                                face_db.map_track_to_person(track_id, person_id)
                                face_db.add_person_feature(person_id, person_crop)
                                
                                # �����һ�γ��ֵ�ͼ��
                                img_path = FACE_DB_PATH / f"person_{person_id}.jpg"
                                cv2.imwrite(str(img_path), person_crop)
                                face_db.person_images[person_id] = str(img_path)
                                face_db.person_names[person_id] = f"Person_{person_id}"
                                face_db.active_people_this_session.add(person_id)
                                print(f"�9�4 New person: Person_{person_id} (Track#{track_id})")
                            
                            # ����person_face_map���ں�������
                            person_face_map[track_id] = person_id
                        
                        # ��¼��֡��ʹ�õ�person_id
                        assigned_person_ids_this_frame.add(person_id)
            
            # ����ؼ�֡������⵽����ʱ��
            if person_count > 0:
                keyframe_path = KEYFRAME_PATH / f"keyframe_{frame_count:06d}.jpg"
                cv2.imwrite(str(keyframe_path), frame)
                current_stats["keyframe_count"] = len(list(KEYFRAME_PATH.glob("*.jpg")))
        
        # �9�3 ���¹ؼ�ʱ�̹����� (ÿ֡����Ƿ���Ҫ AI ����)
        if KEY_MOMENTS_AVAILABLE and key_moments_manager is not None:
            # �9�0 ��֡���ӵ������� (����������ƵƬ��)
            key_moments_manager.add_frame_to_buffer(frame, frame_count)
            
            # �9�3 ��track_idsת��Ϊͳһ��person_ids
            unified_person_ids = [face_db.track_to_person_map.get(tid, tid) for tid in track_ids]
            
            key_moments_manager.update_frame(
                frame=frame,
                frame_number=frame_count,
                person_count=person_count,
                track_ids=unified_person_ids  # ʹ��ͳһ��person_ids
            )
            # ���¹ؼ�ʱ��ͳ��
            km_stats = key_moments_manager.get_stats()
            current_stats["key_moments_count"] = km_stats.get("total_moments", 0)
            current_stats["user_anchors_count"] = km_stats.get("user_anchors", 0)
            current_stats["ai_detected_count"] = km_stats.get("ai_detected", 0)
        
        # �9�2�9�1 ��ģ̬���� (�����Ƶתд + ��Ƶ��Ƭ)
        # ����Ƭ���ڴ������Ϸ�����Ĭ��2���ӣ����� MULTIMODAL_SLICE_SECONDS ������
        global last_multimodal_analysis_time, transcript_buffer, video_slice_buffer, video_slice_start_time
        if KEY_MOMENTS_AVAILABLE and key_moments_manager is not None:
            if not hasattr(process_video_stream, '_last_mm_time'):
            # ������������������һ�Ρ���תд/����֡������Ƭ����
                process_video_stream._last_mm_time = float(current_time)

            if not hasattr(process_video_stream, '_slice_last_ts'):
                process_video_stream._slice_last_ts = 0.0
            
            # Ĭ�ϸ�Ϊ 120�� (2����)�����㡰ÿ2��������һ�ſ�Ƭ��������
            slice_seconds = float(VIDEO_SLICE_SECONDS) if VIDEO_SLICE_SECONDS and VIDEO_SLICE_SECONDS > 1e-6 else 120.0

            # �9�0 ���ӵ�ǰ֡����Ƶ��Ƭ����������ʱ�����������������Ƭ����
            # ����֡�洢Ϊ���ֱ��ʣ������ڴ汬ը��
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
            
            # ����Ƭ���ڴ���һ�η���
            if current_time - process_video_stream._last_mm_time >= slice_seconds and len(video_slice_buffer) > 0:
                # ��ȡ�����Ƭ���ڵ�תд�ı�
                recent_transcript = ""
                cutoff_time = current_time - slice_seconds
                if transcript_buffer:
                    recent_texts = [t.get('text', '') for t in transcript_buffer 
                                   if t.get('timestamp', 0) > cutoff_time]
                    recent_transcript = ' '.join(recent_texts)
                
                # �9�3 ת��Ϊͳһ��person_ids
                unified_person_ids = [face_db.track_to_person_map.get(tid, tid) for tid in track_ids]
                
                # �첽ִ�ж�ģ̬����(ʹ����Ƶ��Ƭ)
                def do_video_slice_analysis(frames_slice, transcript_text_5m, fn, pc, ti, curr_time):
                    try:
                        print(f"�9�0 ��ʼ��Ƶ��Ƭ���� ({int(slice_seconds)}s) (֡ {fn}, {len(frames_slice)} �ؼ�֡, ����: {len(transcript_text_5m)} ��)")

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

                        # ����Ĭ��ֵ�����ڡ�����ģ̬�ж���תд���ڡ�
                        before_s = float(os.environ.get("MULTIMODAL_BEFORE_SECONDS", "15"))
                        after_s = float(os.environ.get("MULTIMODAL_AFTER_SECONDS", "15"))

                        # ��Ƶ���ڿ��Ա�תд���ڸ���Ĭ�ϸ���תд���ڣ�
                        video_before_s = float(os.environ.get("MULTIMODAL_VIDEO_BEFORE_SECONDS", str(before_s)))
                        video_after_s = float(os.environ.get("MULTIMODAL_VIDEO_AFTER_SECONDS", str(after_s)))

                        # ���嶨λ������ 5 ����ȫ��תд������ѡʱ��㣬�ٻص���Щʱ�����������֡
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

                        # �0�4 Fallback: ���û�л��������ĺ�ѡʱ�̣����羲��������ǿ������һ������ʱ��ĺ�ѡ
                        if not candidates:
                            print("�7�2�1�5 δ����������ѡʱ�̣�ʹ��ʱ�䶵�� (Periodic Check)")
                            # ȡ��Ƭ���ڵ��м��
                            mid_ts = float(curr_time) - (float(slice_seconds) / 2.0)
                            candidates.append({
                                'timestamp': mid_ts,
                                'reason': 'Periodic visual check (Silent)',
                                'time_str': 'Auto'
                            })

                        def _video_window_frames(center_ts: float, before: float, after: float):
                            out = []
                            try:
                                start_ts = float(center_ts) - float(before)
                                end_ts = float(center_ts) + float(after)
                                print(f"�9�3 [DEBUG] ɸѡ��Ƭ: frames_slice={len(frames_slice)}, Ŀ�괰��=[{start_ts:.1f}, {end_ts:.1f}]")
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
                            
                            # print(f"�9�3 [DEBUG] ɸѡ���: {len(out)} ֡ (�� {count_valid} ֡��)")
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
                        
                        # �� ���ߡ����嶨λ������֡����ģ̬�ж���
                        for cand in candidates:
                            # ����� periodic fallback��ǿ�ƿ���
                            is_fallback = cand.get('time_str') == 'Auto'
                                
                            try:
                                frame_item, delta = _nearest_frame_by_ts(float(cand.get('timestamp')))
                                if not frame_item:
                                    continue
                                frame_sample = frame_item.get("frame")
                                frame_no = int(frame_item.get("frame_number", fn))
                                frame_ts = float(frame_item.get("ts", curr_time))

                                window_transcript = _transcript_window(frame_ts, before_s=before_s, after_s=after_s)

                                # �0�4 ����� Periodic Check (����ʱ��ǿ�ƴ��)��ֱ�ӵ���ģ�ⰴ��
                                if is_fallback:
                                    print(f"�0�6 [Auto] �����������Զ���� (ģ�ⰴ��)")
                                    # ֱ��ģ��һ�ΰ����������Ϊ AI ��Դ
                                    # ע�⣺KeyMomentsManager.mark_user_anchor �Ѹ���֧�� source ����
                                    key_moments_manager.mark_user_anchor(
                                        frame=frame_sample,
                                        frame_number=frame_no,
                                        person_count=pc,
                                        track_ids=ti,
                                        user_note="Periodic Auto-Snapshot",
                                        transcript=window_transcript[:200],
                                        context_transcript=window_transcript,
                                        source="ai_detected"
                                    )
                                    found_count += 1
                                    continue # ��������LLM��������Ϊ�Ѿ�������

                                if os.environ.get('MULTIMODAL_DEBUG', '0') == '1':
                                    print(f"�0�1 Locator pick [{cand.get('time_str','--')}] ��t={delta:.1f}s reason={cand.get('reason','')[:60]}")

                                result = key_moments_manager.analyze_with_multimodal(
                                    frame=frame_sample,
                                    frame_number=frame_no,
                                    timestamp=frame_ts,
                                    transcript_text=window_transcript,
                                    person_count=pc,
                                    track_ids=ti,
                                    video_frames=_video_window_frames(frame_ts, video_before_s, video_after_s),
                                )
                                
                                # �����⵽�ؼ�ʱ��(��Ҫ�� > 0.2)
                                if result:
                                    print(f"�7�8 ���ֹؼ�ʱ��! ��Ҫ��: {result.get('importance', 0):.2f}")
                                    print(f"   ����: {result.get('description', 'N/A')[:100]}")
                                    found_count += 1
                                    
                                    # �9�9 ���봰��תд��ֻ��ʾǰ��15���תд������������Ƭ��
                                    try:
                                        # ��ȡ���´����Ĺؼ�ʱ��
                                        moments = key_moments_manager.get_moments()
                                        if moments:
                                            latest_moment = moments[-1]
                                            moment_id = latest_moment.get('id', '')
                                            moment_ts = float(latest_moment.get('timestamp', frame_ts))
                                            
                                            # ���㴰��
                                            before_s = float(os.environ.get("MULTIMODAL_BEFORE_SECONDS", "15"))
                                            after_s = float(os.environ.get("MULTIMODAL_AFTER_SECONDS", "15"))
                                            start_ts = moment_ts - before_s
                                            end_ts = moment_ts + after_s
                                            
                                            # ��transcript_bufferɸѡ����תд
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
                                            
                                            # ����moment��תдΪ����תд
                                            if window_text and key_moments_manager and hasattr(key_moments_manager, "update_user_anchor_text"):
                                                key_moments_manager.update_user_anchor_text(
                                                    moment_id=moment_id,
                                                    user_note="",
                                                    transcript=window_text,
                                                    context_transcript=transcript_text_5m,
                                                    asr_meta={},
                                                )
                                                print(f"   �7�3 �Ѳ��봰��תд: {len(window)} ��Ƭ��, �� {len(window_text)} ��")
                                    except Exception as patch_err:
                                        print(f"   �7�2�1�5 ���봰��תдʧ��: {patch_err}")

                                    # ͬһ����Ƭ���������ж����Ĭ��1����
                                    if found_count >= max_hits:
                                        break
                            except Exception:
                                continue

                            if found_count >= max_hits:
                                break

                        # �� ���ף�������嶨λû�к�ѡ/û���У��������֡����ɨ�裨����ԭ��Ϊ��
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
                                    print(f"�7�8 ���ֹؼ�ʱ��! ��Ҫ��: {result.get('importance', 0):.2f}")
                                    print(f"   ����: {result.get('description', 'N/A')[:100]}")
                                    found_count += 1
                                    if found_count >= max_hits:
                                        break

                        if found_count == 0:
                            print("�0�8 ������Ƭ��δ���йؼ�ʱ�̣��ɴ� MULTIMODAL_DEBUG=1 �鿴ÿ���ж�ϸ�ڣ�")
                        
                        print(f"�7�3 ��Ƶ��Ƭ�������")
                    except Exception as e:
                        print(f"�7�2�1�5 ��Ƶ��Ƭ��������: {e}")
                        import traceback
                        traceback.print_exc()
                
                threading.Thread(
                    target=do_video_slice_analysis,
                    args=(video_slice_buffer.copy(), recent_transcript, frame_count, person_count, unified_person_ids, current_time),
                    daemon=True
                ).start()
                
                print(f"�0�6 ����AI ��Ƭ���� ({int(slice_seconds)}s) (֡ {frame_count}, ��Ƶ֡: {len(video_slice_buffer)}, ����: {len(recent_transcript)} ��)")
                
                # ���û�����
                video_slice_buffer = []
                process_video_stream._last_mm_time = current_time
        
        # ����ͳ��
        current_stats.update({
            "frame_count": frame_count,
            "person_count": person_count,
            "track_ids": track_ids,
            "fps": round(current_fps, 1)
        })
        
        # ���ƽ��
        annotated_frame = frame.copy()
        
        # Ϊÿ��person_id������ɫ
        person_colors = {}
        for person_id in range(1, face_db.get_person_count() + 1):
            person_colors[person_id] = COLOR_POOL[(person_id - 1) % len(COLOR_POOL)]
        
        # ����ÿ������
        if boxes is not None:
            for box in boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0].cpu().numpy())
                track_id = int(box.id.cpu().numpy().item()) if box.id is not None else None
                conf = float(box.conf.cpu().numpy().item())
                
                # ȷ����ɫ�ͱ�ǩ
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
                
                # ���Ʊ߿�
                cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 3)
                
                # ���Ʊ�ǩ
                label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
                label_y = max(y1 - 10, label_size[1] + 10)
                cv2.rectangle(annotated_frame, 
                             (x1, label_y - label_size[1] - 5), 
                             (x1 + label_size[0] + 5, label_y + 5), 
                             color, -1)
                cv2.putText(annotated_frame, label, (x1 + 2, label_y), 
                           cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)
                
                # ���¹켣
                if track_id is not None:
                    center_x = (x1 + x2) // 2
                    center_y = (y1 + y2) // 2
                    
                    if track_id not in track_trajectories:
                        track_trajectories[track_id] = []
                    
                    track_trajectories[track_id].append((center_x, center_y))
                    
                    if len(track_trajectories[track_id]) > MAX_TRAJECTORY_LENGTH:
                        track_trajectories[track_id].pop(0)
                    
                    # ���ƹ켣
                    if len(track_trajectories[track_id]) > 1:
                        points = track_trajectories[track_id]
                        for j in range(1, len(points)):
                            alpha = j / len(points)
                            thickness = max(1, int(3 * alpha))
                            cv2.line(annotated_frame, points[j-1], points[j], color, thickness)
        
        # ��ʾͳ����Ϣ
        info_text = f"Frame: {frame_count} | FPS: {current_fps:.1f} | People: {person_count} | Known: {face_db.get_person_count()}"
        cv2.putText(annotated_frame, info_text, (10, 30), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        
        # ��ʾģʽ
        mode_text = f"Mode: {current_stats['stream_mode'].upper()}"
        cv2.putText(annotated_frame, mode_text, (10, 60), 
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
        
        # ������Ƶ��֡ (������ҳ��ʾ)
        # ˵������ҳ��MJPEG�����̫��/ѹ��̫�ݣ�����֡��� + ������������������������޿���
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
        
        # ��ʾ���ش��� (�������)
        if show_window:
            should_display = True
            if is_video_file:
                should_display = (frame_count % DISPLAY_FRAME_SKIP == 0)
            
            if should_display:
                try:
                    cv2.imshow("Integrated System (��q�˳�)", annotated_frame)
                    key = cv2.waitKey(1) & 0xFF
                    if key == ord('q'):
                        is_running = False
                        break
                except Exception as e:
                    if frame_count == 1:
                        print(f"�7�2�1�5  �޷���ʾ����: {e}")
        else:
            # ��ʹ����ʾ����,Ҳ��Ҫ�����¼����⿨��
            cv2.waitKey(1)
        
        # ÿ100֡��ӡ
        # if frame_count % 100 == 0:
        #     print(f"�9�6 ֡ {frame_count}: {person_count} ��, ��֪ {face_db.get_person_count()} ��")
    
    # ����
    current_stats["status"] = "stopped"
    cap.release()
    cv2.destroyAllWindows()

    # ֹͣ��̨���񣬱��� Ctrl+C �˳�ʱ���� native ����/����
    try:
        shutdown_background_services()
    except Exception:
        pass
    
    print("\n" + "="*60)
    print("�9�6 ����ͳ��:")
    print(f"  ��֡��: {frame_count}")
    print(f"  ��ʶ������: {face_db.get_person_count()}")
    print(f"  ����������: {current_stats['face_detections']}")
    print("="*60)
    print("\n�9�4 Web�������������У��ɲ鿴���")
    print("�7�2�1�5  �� Ctrl+C ��ȫ�˳�")
    
    # ���ַ��������У����ڲ鿴�������Ctrl+C ʱ��һ�θɾ��˳�
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n�7�3 �û��˳�")
        try:
            shutdown_background_services()
        except Exception:
            pass
        return


def shutdown_background_services():
    """�����ɾ���ֹͣ��̨�߳�/��Ƶ��Դ�������˳������� BPT trap��"""
    global realtime_asr_engine, meeting_notes_generator, key_moments_manager, microphone_recorder

    print("�9�2 Stopping services...", end="\r")

    # ����ֹͣ������I/O�ܼ���ֹͣ����������رա��ļ����棩
    import concurrent.futures
    stop_tasks = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        # 1. ֹͣ�����Ҫ
        if meeting_notes_generator is not None:
            stop_tasks.append(executor.submit(lambda: meeting_notes_generator.stop() if hasattr(meeting_notes_generator, 'stop') else None))

        # 2. ֹͣʵʱASR
        if realtime_asr_engine is not None:
            stop_tasks.append(executor.submit(lambda: realtime_asr_engine.stop() if hasattr(realtime_asr_engine, 'stop') else None))

        # 3. ֹͣ�ؼ�ʱ�̹����� (�����漰�ļ�д�룬�����Գ���ʱ)
        if key_moments_manager is not None:
            def stop_km():
                for meth in ("stop", "cleanup"):
                    if hasattr(key_moments_manager, meth):
                        try:
                            getattr(key_moments_manager, meth)()
                        except Exception:
                            pass
            stop_tasks.append(executor.submit(stop_km))

        # 4. ֹͣ��˷�
        if microphone_recorder is not None:
            stop_tasks.append(executor.submit(lambda: microphone_recorder.stop_recording() if hasattr(microphone_recorder, 'stop_recording') else None))

        # �ȴ�����������ɣ���ʱ1.5�루���⿨����
        # �󲿷� stop Ӧ�úܿ죬�����סֱ�ӷ���
        _, _ = concurrent.futures.wait(stop_tasks, timeout=2.0)

    # �������������Ƶ����������ֹͣ PyAudio stream��
    try:
        from audio_manager import get_audio_manager
        get_audio_manager().cleanup()
    except Exception:
        pass

# ============================================================
# �0�4 ������
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='������Ƶ����������׷������ϵͳ')
    parser.add_argument('--video', '-v', type=str, help='��Ƶ�ļ�·��')
    parser.add_argument('--camera', '-c', type=int, default=0, help='����ͷID (Ĭ��0)')
    parser.add_argument('--obs', action='store_true', help='ʹ��OBS������������ͷ��RTMP��')
    parser.add_argument('--obs-url', type=str, default='rtmp://localhost/live', 
                       help='OBS RTMP����ַ')
    parser.add_argument('--ai', action='store_true', help='����AI��������ҪAPI Key��')
    parser.add_argument('--port', type=int, default=8080, help='Web�������˿�')
    parser.add_argument('--no-face', action='store_true', help='��������ʶ��')
    parser.add_argument('--no-window', action='store_true', help='���ñ���OpenCV����(��ʹ��Web����)')
    parser.add_argument('--no-browser', action='store_true', help='���Զ��������')
    
    args = parser.parse_args()
    
    print("�X�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�[")
    print("�U   �9�0 ������Ƶ����������׷������ϵͳ                   �U")
    print("�U   ONE_KEY + multi_person_tracker                      �U")
    print("�^�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�T�a\n")
    
    # �0�4 ��������Web������(�����ɷ��ʽ���)
    print("�9�4 ����Web������...")
    web_thread = threading.Thread(target=start_web_server, args=(args.port,), daemon=True)
    web_thread.start()
    time.sleep(0.5)  # ���ٵȴ�ʱ��
    
    # �Զ��������
    web_url = f"http://localhost:{args.port}/integrated%20final.html"
    if not args.no_browser:
        print(f"�7�3 Web�����Ѿ���: {web_url}")
        print("�9�5 ��ʾ: ������򿪺�,ϵͳ���ں�̨����ģ��...")
        webbrowser.open(web_url)
    else:
        print(f"�7�3 Web�����Ѿ���: {web_url}")
    
    # ��ʼ������ʶ��(�ӳټ���,����������)
    face_app = None
    face_future = None
    if INSIGHTFACE_AVAILABLE and not args.no_face:
        def load_face_app():
            global FaceAnalysis
            try:
                print("�9�9 ��̨����InsightFace...")
                from insightface.app import FaceAnalysis as FA
                FaceAnalysis = FA
                # InsightFace 0.2.1�汾 - ʹ��buffalo_lģ��
                print("�9�3 �״�ʹ����Ҫ����ģ���ļ�(Լ200MB),�����ĵȴ�...")
                face_app = FaceAnalysis(name='buffalo_l')
                face_app.prepare(ctx_id=-1, det_size=(640, 640))
                print("�7�3 InsightFace�������")
                return face_app
            except Exception as e:
                print(f"�7�2�1�5  InsightFace����ʧ��: {e}")
                print("�9�5 ��ʾ: ϵͳ������ʹ�ô�YOLO׷��ģʽ")
                return None
        
        # �ں�̨�߳��м���
        import concurrent.futures
        face_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        face_future = face_executor.submit(load_face_app)
        print("�9�5 InsightFace���ں�̨����...")
    
    # ����ƵԴ
    try:
        video_source_path = None  # ���ڹؼ�ʱ����Ƶ��ȡ
        
        if args.obs:
            print(f"�9�9 ����OBS��...")
            cap, fps = VideoSource.open_obs_stream(args.obs_url)
            print("�7�3 OBS�����ӳɹ�")
        elif args.video:
            print(f"�9�3 ����Ƶ: {args.video}")
            cap, fps = VideoSource.open_video(args.video)
            video_source_path = args.video  # ������ƵԴ·��������Ƶ��ȡ
            print(f"�7�3 ��Ƶ�򿪳ɹ� (FPS: {fps:.1f})")
        else:
            print(f"�9�1 ������ͷ #{args.camera}...")
            cap, fps = VideoSource.open_camera(args.camera)
            print("�7�3 ����ͷ�򿪳ɹ�")
        
        if not cap.isOpened():
            print("�7�4 �޷�����ƵԴ")
            return
        
        # �ȴ�����ʶ����أ�������ڼ��أ�
        if face_future is not None:
            try:
                print("�7�7 �ȴ�InsightFace�������...")
                face_app = face_future.result(timeout=60)  # ���ȴ�60��
                if face_app is None:
                    print("�7�2�1�5  ����ʶ�����ʧ�ܣ���ʹ�ô��Ӿ�ģʽ")
                else:
                    print("�7�3 ����ʶ���Ѿ���")
            except Exception as e:
                print(f"�7�2�1�5  �ȴ�����ʶ��ʱ: {e}")
        
        # ��ʼ���� (�����Ƿ���ʾ���ں���ƵԴ·��)
        show_window = not args.no_window
        try:
            process_video_stream(cap, fps, face_app, args.ai, show_window, video_source_path)
        except KeyboardInterrupt:
            # �9�7 ���Ʒ�ֹͣ��ص��������ֹˢ��
            class FilteredStream:
                def __init__(self, original):
                    self.original = original
                def write(self, text):
                    # �ؼ��ʰ�������ֻ����������Щ�ʵ���־���
                    keywords = ["Stop", "stop", "Shut", "shut", "Clos", "clos", 
                                "��", "ͣ", "��", "Exit", "exit", "End", "end", 
                                "Saved", "saved", "��", "¼", # ����¼��/���������ʾ
                                "Server", "server", "����", "Cleaning", "clean"]
                    # �޸������ٷ��д��հ׷���text.strip() == ""������ֹCtrl+C�����޻س�ˢ��
                    if any(k in text for k in keywords):
                        self.original.write(text)
                def flush(self):
                    self.original.flush()
            
            # �滻��׼���
            sys.stdout = FilteredStream(sys.stdout)
            sys.stderr = FilteredStream(sys.stderr)

            print("\n�7�3 �û��ж� (Ctrl+C)������ֹͣ��̨����...")
            try:
                shutdown_background_services()
            except Exception:
                pass
            # macOS �³�����PyAudio/OpenCV �� native ��Դ�ڽ�������βʱ���� SIGTRAP��
            # ������һ�Ρ�������ǿ�ˡ������� Trace/BPT trap: 5��
            # ��Linux��Ҳʹ�� os._exit(0) ��ȷ�������̣߳���ASR��LLM��������ֹ����ֹ����
            os._exit(0)
            return
        
    except Exception as e:
        print(f"�7�4 ����: {e}")
        import traceback
        traceback.print_exc()
        try:
            shutdown_background_services()
        except Exception:
            pass

if __name__ == '__main__':
    main()
