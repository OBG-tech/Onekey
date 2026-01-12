#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎯 双轨关键时刻识别系统 (Dual-Track Key Moments Manager)

两种识别来源:
1. 用户主动标记 (The Anchor) - 物理按钮/快捷键, 0.5秒意图锚定
2. AI 自动识别 (Smart Mirror) - 每3.5分钟切片, Qwen-VL 分析

输出: LLM 纪录片导演式叙事 (Oeuvre)
"""
import os
import sys
import json
import time
import re
import base64
import threading
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from enum import Enum

KEY_MOMENT_BEFORE_SECONDS = float(os.environ.get("KEY_MOMENT_BEFORE_SECONDS", "15"))
KEY_MOMENT_AFTER_SECONDS = float(os.environ.get("KEY_MOMENT_AFTER_SECONDS", "15"))
# ============================================================
# ? 数据结构
# ============================================================

class MomentSource(Enum):
    """关键时刻来源"""
    USER_ANCHOR = "user_anchor"      # 用户按钮标记
    AI_DETECTED = "ai_detected"      # AI �Զ�ʶ��
    AI_HIGHLIGHT = "ai_highlight"    # AI ʶ��ĸ߹�ʱ��


@dataclass
class KeyMoment:
    """关键时刻数据结构"""
    id: str                          # ���0�5ID: timestamp_source
    timestamp: float                 # Unix ʱ���
    frame_number: int                # ֡��
    source: str                      # �1�7�1�7�0�6: user_anchor / ai_detected
    frame_path: str                  # �ؼ�֡ͼƬ·��
    
    # 视频片段
    video_path: str = ""             # 视频片段路径 (前后各5秒)
    video_duration: float = 0        # 视频时长(秒)
    
    # 元数据
    time_str: str = ""               # ֻ��ʱ�� HH:MM:SS
    duration_seconds: float = 0      # 从开始到这一刻的秒数
    
    # 用户输入 (从 user_anchor)
    user_note: str = ""              # 用户备注 (可选)
    
    # 语音数据
    transcript: str = ""             # 语音转文字内容

    # 语音/模型元信息（用于回答“现在ASR是什么模型”）
    asr_provider: str = ""           # fireredasr | dashscope | ...
    asr_model: str = ""              # ���� aed:FireRedASR-AED-L �� paraformer-realtime-v2
    asr_model_dir: str = ""          # FireRedASR 模型目录（如适用）
    
    # AI 分析结果 (从 ai_detected)
    ai_description: str = ""         # AI 对这一刻的描述
    ai_tagline: str = ""             # AI 短标题（用于贴纸/短标识；可选）
    ai_importance: float = 0.0       # AI 评估的重要性 0-1
    ai_tags: List[str] = field(default_factory=list)  # AI ��ȡ�ı�ǩ
    ai_framework_tags: str = ""      # 协作学习框架标题（如[R2]论证、Eng-Flow等）
    analysis: str = ""               # AI 综合分析/总结

    # LLM 元信息
    llm_provider: str = ""           # qwen | claude
    llm_model: str = ""              # 实际调用的模型（此处多为 vision_model）

    # Debug info (optional)
    last_error: str = ""             # 最近一次 AI/ASR 失败的错误信息（便于 UI 排查）
    
    # 场景信息
    person_count: int = 0            # 当前画面人数
    track_ids: List[int] = field(default_factory=list)  # ��Ծ��׷��ID
    
    # 叙事元素 (由 LLM 生成)
    narrative_role: str = ""         # �������еĽ�ɫ: opening/rising/climax/falling/resolution
    narrative_text: str = ""         # 叙事文本
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        d = asdict(self)
        # 统一处理字段：避免前端用 `||` 做兜底时，纯空白字符串“看起来像没内容”。
        for k in (
            "user_note",
            "transcript",
            "ai_description",
            "ai_tagline",
            "analysis",
            "asr_provider",
            "asr_model",
            "asr_model_dir",
            "llm_provider",
            "llm_model",
        ):
            v = d.get(k)
            if v is None:
                d[k] = ""
            elif isinstance(v, str):
                d[k] = v.strip()
        return d


# ============================================================
# 🎞️ 关键时刻管理器
# ============================================================

class KeyMomentsManager:
    """双轨关键时刻管理器"""

    def _rebuild_moments_index_from_dir(self) -> int:
        """从 key_moments 目录重建 moments.json（兜底）。

        触发条件：moments.json 不存在、为空、或 moments 列表为空但目录中存在 anchor_* 文件。

        返回：重建写入的 moments 数量。
        """
        try:
            km_dir = self.moments_dir
            if not km_dir.exists():
                return 0

            # 约定文件名：anchor_<unix>_<rand>.jpg/mp4/context.txt
            jpgs = sorted(km_dir.glob("anchor_*.jpg"))
            if not jpgs:
                return 0

            rebuilt: List[KeyMoment] = []
            for jpg in jpgs:
                stem = jpg.stem  # anchor_....
                # 尽量同时绑定 mp4（可选）
                mp4 = km_dir / f"{stem}.mp4"

                ts = 0.0
                frame_num = 0
                try:
                    parts = stem.split("_")
                    # anchor, unix, rand
                    if len(parts) >= 3:
                        ts = float(parts[1])
                        # history moment 的 frame_number 不一定可得，保持 0
                except Exception:
                    ts = 0.0

                moment = KeyMoment(
                    id=stem,
                    timestamp=ts,
                    frame_number=frame_num,
                    source=MomentSource.USER_ANCHOR.value,
                    frame_path=str(jpg),
                    video_path=str(mp4) if mp4.exists() else "",
                )
                rebuilt.append(moment)

            # 基于文件系统重建 stats
            self.moments = rebuilt
            self.stats["total_moments"] = len(rebuilt)
            # 不强行判断 ai_detected/user_anchors；先把 total 拉起来，避免 UI 空白
            self.stats["user_anchors"] = max(int(self.stats.get("user_anchors", 0)), len(rebuilt))

            self._save_moments()
            print(f"🛠️ 已从目录重建 moments.json: {len(rebuilt)} 条")
            return len(rebuilt)
        except Exception as e:
            print(f"⚠️ 重建 moments 索引失败: {e}")
            return 0

    def _try_load_env_file(self) -> None:
        """Best-effort load env vars from `.env.local`/`.env`.

        Why: In many runs, the start scripts don't `export` API keys into the process
        environment, but a `.env.local` exists (used by tests). If the key isn't loaded,
        the AI summary path always falls back to `[AI Analysis Failed]`.
        """
        # already have a key -> nothing to do
        if (os.environ.get("DASHSCOPE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY")):
            return

        # 1) prefer python-dotenv if installed
        try:
            from dotenv import load_dotenv  # type: ignore

            root = Path(__file__).parent
            for name in (".env.local", ".env"):
                p = root / name
                if p.exists():
                    load_dotenv(dotenv_path=p, override=False)
                    break
            return
        except Exception:
            pass

        # 2) minimal parser (KEY=VALUE, ignore comments)
        root = Path(__file__).parent
        for name in (".env.local", ".env"):
            p = root / name
            if not p.exists():
                continue
            try:
                for raw in p.read_text(encoding="utf-8").splitlines():
                    line = raw.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k and v and k not in os.environ:
                        os.environ[k] = v
            except Exception:
                continue
            break

    def _normalize_qwen_text_model(self, model_name: str) -> str:
        """Guardrail for DashScope(OpenAI-compatible) usage.

        Users sometimes export `LLM_MODEL=gpt-*` from other experiments. DashScope will
        return 404 for unknown models, which then looks like a generic "AI Analysis Failed".
        """
        m = (model_name or "").strip()
        if not m:
            return "qwen-max"
        low = m.lower()
        # allow common qwen text models
        if low.startswith("qwen"):
            return m
        # known bad / other vendors
        return "qwen-max"

    def _normalize_qwen_vision_model(self, model_name: str) -> str:
        m = (model_name or "").strip()
        if not m:
            return "qwen-vl-max-latest"
        low = m.lower()
        if low.startswith("qwen-vl"):
            return m
        # if user put a text model into vision slot, or gpt/claude/anything else
        return "qwen-vl-max-latest"
    
    def __init__(self, data_dir: Path = None, api_key: str = None,
                 video_source: str = None, audio_source: str = None, microphone_recorder=None,
                 video_fps: float = None):
        """
        初始化管理器
        
        Args:
            data_dir: 数据存储目录
            api_key: DashScope API Key (���� Qwen-VL)
            video_source: 原始视频文件路径或摄像头ID (用于提取音频)
            audio_source: 音频源路径 (可选, 如果与视频不同)
            microphone_recorder: 麦克风录制器实例 (摄像头模式使用)
        """
        self.data_dir = data_dir or Path(__file__).parent / "integrated_data"
        self.moments_dir = self.data_dir / "key_moments"
        self.moments_dir.mkdir(parents=True, exist_ok=True)
        
        # 麦克风录制器
        self.microphone_recorder = microphone_recorder

        # API ���� (LLM provider: qwen | claude)
        # 兼容：如果用户把 key 写在 `.env.local` 里，但不是通过 shell 导出环境变量，
        # 这里尝试自动加载（不强依赖 python-dotenv）。
        self._try_load_env_file()
        self.dashscope_api_key = api_key or os.environ.get("DASHSCOPE_API_KEY", "")
        self.claude_api_key = os.environ.get("ANTHROPIC_API_KEY", "") or os.environ.get("CLAUDE_API_KEY", "")
        self.llm_provider = os.environ.get("LLM_PROVIDER", "qwen").lower()
        self.text_model = os.environ.get("LLM_MODEL") or ("claude-3-5-haiku-20241022" if self.llm_provider.startswith("claude") else "qwen-max")
        self.vision_model_fast = os.environ.get("VISION_MODEL_FAST") or ("claude-3-5-haiku-20241022" if self.llm_provider.startswith("claude") else "qwen-vl-plus")
        self.vision_model = os.environ.get("VISION_MODEL") or ("claude-3-5-haiku-20241022" if self.llm_provider.startswith("claude") else "qwen-vl-max-latest")

        # 修复：防止用户把不属于 DashScope 的模型名（例如 gpt-*）写进环境变量，导致 404
        # 对 qwen provider 强制校验/回退到已知可用的 qwen 模型。
        if not self.llm_provider.startswith("claude"):
            self.text_model = self._normalize_qwen_text_model(self.text_model)
            self.vision_model_fast = self._normalize_qwen_vision_model(self.vision_model_fast)
            self.vision_model = self._normalize_qwen_vision_model(self.vision_model)

        # FireRedASR 模型缓存（关键时刻转写会频繁触发；避免每次 from_pretrained 导致卡顿/高延迟）
        self._fireredasr_lock = threading.Lock()
        self._fireredasr_model = None

        # moments 的并发更新（用户标记线程 / after 扩展线程 / AI线程都可能写入）
        self._moments_lock = threading.Lock()

        # 重任务限流：关键时刻"提取音频→ASR→多模态AI"会占用较多 CPU/GIL。
        # 默认串行，避免点击标记后把实时 ASR 拖到高延迟。
        heavy_n = int(os.environ.get("KEY_MOMENT_HEAVY_CONCURRENCY", "1"))
        if heavy_n < 1:
            heavy_n = 1
        self._heavy_job_sema = threading.Semaphore(heavy_n)

        # 记录最近一次 ASR 调用的元信息，便于写入 moment
        self._last_asr_meta: Dict[str, str] = {}
        self.llm_api_key = self.claude_api_key if self.llm_provider.startswith("claude") else self.dashscope_api_key
        self.api_key = self.dashscope_api_key  # 兼容旧字段（主要用于语音/音频调用）
        self.qwen_available = bool(self.llm_api_key)
        
        # 📹 视频/音频源配置 (用于提取音频轨道)
        self.video_source = video_source  # 原始视频文件路径
        self.audio_source = audio_source or video_source  # 音频源 (默认与视频相同)
        self.video_fps = float(video_fps) if video_fps else None
        
        # ״̬
        self.moments: List[KeyMoment] = []
        self.start_time: float = time.time()
        self.frame_count: int = 0
        
    # 📹 视频帧缓冲区（用于录制关键时刻前后的视频片段）
        self.frame_buffer: list = []      # �洢 (frame, frame_num, timestamp) Ԫ��
        # 缓冲区最大保留秒数（需要覆盖关键时刻窗口 + AI 分析延迟 + 余量）
        # 从 60 秒提升到 120 秒，以适配 AI 分析延迟（约 60 秒）
        self.buffer_max_seconds = int(max(120, KEY_MOMENT_BEFORE_SECONDS + KEY_MOMENT_AFTER_SECONDS + 90))
        # 按最大可能 FPS(60) 估算，确保 FPS 波动时仍能覆盖 120 秒
        self.buffer_fps = 60.0
        self.buffer_max_frames = int(self.buffer_max_seconds * self.buffer_fps)
        print(f"   �1�70�1�78 [BUFFER] Config: max_seconds={self.buffer_max_seconds}, fps={self.buffer_fps}, max_frames={self.buffer_max_frames}, format=JPEG")
        self.buffer_lock = threading.Lock()

        # 🎧 音频缓冲区（用于录制对应的音频片段）
        self.audio_buffer: list = []      # �洢 (audio_chunk, timestamp) Ԫ��
        self.audio_buffer_lock = threading.Lock()

        # AI 分析配置
        self.ai_interval_seconds = 210  # 3.5 分钟一次切片
        self.last_ai_analysis_time: float = 0
        self.ai_analysis_buffer: List[tuple] = []  # (frame, frame_num, timestamp)
        
        # 统计信息（必须在加载历史数据前初始化）
        self.stats = {
            "user_anchors": 0,
            "ai_detected": 0,
            "total_moments": 0
        }
        
        # 加载历史数据
        self._load_moments()
        
        # 简化初始化日志
        audio_status = "❌ 无音频"
        if self.microphone_recorder:
            audio_status = "✅ 系统麦克风"
        elif self.audio_source:
            audio_status = "✅ 文件音频"
        
        print("🎬 KeyMomentsManager 已启动")
        print(f"   �9�7 �洢: {self.moments_dir}")
        print(f"   �9�5 ��Ƶ: {audio_status}")
        if self.qwen_available:
            provider_label = "Claude Haiku 4.5" if self.llm_provider.startswith("claude") else "Qwen"
            print(f"   🤖 AI分析: 已启用 ({provider_label}, model={self.text_model})")
        else:
            print("   🤖 AI分析: 未配置 LLM API Key")
            
        try:
            with open("debug_startup.log", "a") as f:
                f.write(f"\n[{datetime.now()}] Init:\n")
                f.write(f"CWD: {os.getcwd()}\n")
                f.write(f"Data Dir: {self.moments_dir}\n")
                f.write(f"Moments Loaded: {len(self.moments)}\n")
                f.write(f"Qwen Available: {self.qwen_available}\n")
                f.write(f"API Key: {str(self.api_key)[:5]}***\n")
        except Exception as e:
            print(f"Failed to write debug log: {e}")
    
    def _load_moments(self):
        """加载历史关键时刻"""
        moments_file = self.moments_dir / "moments.json"
        if moments_file.exists():
            try:
                with open(moments_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.moments = [KeyMoment(**m) for m in data.get('moments', [])]
                    self.stats = data.get('stats', self.stats)

                # 兜底：如果 JSON 里 moments 为空，但目录里有实际文件，则自动重建
                if not self.moments:
                    self._rebuild_moments_index_from_dir()

                # 轻量迁移：历史数据里可能存在 moment 的 ai_description 其实是“短标题”(<=14字)。
                # 而 analysis 里包含“详细描述：…”，会导致卡片信息密度下降；这里自动修正一次。
                upgraded = False
                for m in self.moments:
                    try:
                        if (m.ai_tagline or "").strip():
                            continue
                        if not (m.analysis or "").strip():
                            continue
                        existing_desc = (m.ai_description or "").strip()
                        if not existing_desc:
                            continue
                        if len(existing_desc) > 16:
                            continue
                        detail = self._extract_detail_description(m.analysis)
                        if detail and len(detail) >= 20:
                            m.ai_tagline = existing_desc
                            m.ai_description = detail
                            upgraded = True
                    except Exception:
                        continue
                if upgraded:
                    self._save_moments()
                
                # 为历史数据补充tags并保存
                tags_updated = False
                for m in self.moments:
                    # 🏷️ 自动生成tags（如果不存在）
                    if not m.ai_tags or len(m.ai_tags) == 0:
                        import re
                        text_for_tags = m.ai_tagline or m.ai_description or m.transcript or ""
                        # 移除 emoji：使用稳定的 Unicode 范围，避免历史乱码导致 `bad character range`
                        try:
                            clean_text = re.sub(r'[\U00010000-\U0010ffff]', '', text_for_tags)
                        except re.error:
                            # 极端情况下（某些窄字符构建），降级为原始文本
                            clean_text = text_for_tags
                        # 按标点和空格切分
                        clean_text = re.sub(r'[，。！？、：“”‘’（）【】\s]+', '|', clean_text)
                        words = [w.strip() for w in clean_text.split('|') if w.strip()]
                        
                        # 过滤：只保留2-8字的短词
                        stopwords = {
                            '的', '了', '和', '与', '在', '是', '有', '就', '都', '很', '也', '而', '及', '或', '被', '把',
                            '我们', '你们', '他们', '她们', '它们', '这里', '那里', '这个', '那个', '一个', '一些',
                        }
                        filtered = [w for w in words if 2 <= len(w) <= 8 and w not in stopwords]
                        
                        tags = filtered[:3]
                        if not tags:
                            tags = []
                        m.ai_tags = tags
                        tags_updated = True
                
                if tags_updated:
                    print("   🏷️ 为历史数据补充了 tags")
                    self._save_moments()
                
                # print(f"   已加载 {len(self.moments)} 条历史关键时刻")
            except Exception as e:
                print(f"   ❌ 加载历史数据失败: {e}")
                # JSON 读取/解析失败，也尝试从目录重建一次
                self._rebuild_moments_index_from_dir()
        else:
            # moments.json 不存在时，尝试从目录重建
            self._rebuild_moments_index_from_dir()
    
    def _save_moments(self):
        """保存关键时刻到文件"""
        moments_file = self.moments_dir / "moments.json"
        try:
            # print(f"�1�79�1�74 [DEBUG] Saving moments... count={len(self.moments)} (stats={self.stats})")
            # if len(self.moments) > 0:
            #     print(f"�1�79�1�74 [DEBUG] Sample moment: {self.moments[0].to_dict()}")
            
            data = {
                'moments': [m.to_dict() for m in self.moments],
                'stats': self.stats,
                'last_updated': datetime.now().isoformat()
            }
            with open(moments_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print("�1�70�1�78 [DEBUG] Save complete.")
        except Exception as e:
            print(f"❌ 保存关键时刻失败: {e}")
            import traceback
            traceback.print_exc()

    def _build_llm_client(self):
        """根据提供者创建 LLM 客户端"""
        if not self.llm_api_key:
            raise RuntimeError("LLM API Key δ����")
        # 避免网络抖动/限流导致请求无限期卡住
        llm_timeout = float(os.environ.get("LLM_TIMEOUT_SECONDS", "45"))
        if self.llm_provider.startswith("claude"):
            try:
                from anthropic import Anthropic
            except ImportError as e:
                raise ImportError("���Ȱ�װ anthropic ��: pip install anthropic") from e
            # anthropic 的 timeout 配置在不同版本差异较大；此处先保持兼容，仅控制 OpenAI 路径
            return Anthropic(api_key=self.llm_api_key)
        try:
            from openai import OpenAI
        except ImportError as e:
            raise ImportError("���Ȱ�װ openai ��: pip install openai>=1.0.0") from e
        # 禁用httpx的代理自动检测（trust_env=False），避免GNOME系统socks代理导致错误
        try:
            import httpx
            http_client = httpx.Client(trust_env=False, timeout=llm_timeout)
        except Exception:
            http_client = None
        return OpenAI(
            api_key=self.llm_api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            timeout=llm_timeout,
            http_client=http_client,
        )

    # ============================================================
    # 🧪 LLM Trace（打印 Prompt/返回/判定依据）
    # ============================================================

    def _llm_trace_mode(self) -> str:
        """Trace 输出等级：off / meta / compact / full

        - off: 不打印
        - meta: 只打印 meta（不打印 prompt/response）
        - compact: 打印 meta + response/decision，但隐藏 prompt（避免刷屏/泄露提示词）
        - full: ��ӡ meta + prompt + response
        """
        # 显式 LLM_TRACE=1 时才认为用户要看 trace；默认给 compact，避免 prompt 刷屏
        flag = (os.environ.get("LLM_TRACE", "") or "").strip().lower()
        if flag in {"1", "true", "yes", "y", "on"}:
            mode = (os.environ.get("LLM_TRACE_MODE", "") or "").strip().lower() or "compact"
            return mode if mode in {"off", "meta", "compact", "full"} else "compact"

        # 兼容：打开 MULTIMODAL_DEBUG 也启用 trace，但只打印 meta
        dbg = (os.environ.get("MULTIMODAL_DEBUG", "0") or "0").strip().lower()
        if dbg in {"1", "true", "yes", "y", "on"}:
            return "meta"
        return "off"

    def _llm_trace_enabled(self) -> bool:
        return self._llm_trace_mode() != "off"

    def _llm_trace_full(self) -> bool:
        flag = (os.environ.get("LLM_TRACE_FULL", "") or "").strip().lower()
        return flag in {"1", "true", "yes", "y", "on"}

    def _llm_trace_max_chars(self) -> int:
        try:
            n = int(os.environ.get("LLM_TRACE_MAX_CHARS", "2500"))
            return max(200, min(n, 20000))
        except Exception:
            return 2500

    def _llm_trace_print(self, title: str, content: str):
        mode = self._llm_trace_mode()
        if mode == "off":
            return

        # meta 模式：只打印 meta
        if mode == "meta" and title != "meta":
            return

        # compact 模式：隐藏 prompt（保留 response/decision）
        if mode == "compact" and (" prompt" in title or title.endswith("prompt")):
            content = "<hidden prompt; set LLM_TRACE_MODE=full to show>"

        txt = (content or "")
        if not self._llm_trace_full():
            mx = self._llm_trace_max_chars()
            if len(txt) > mx:
                txt = txt[:mx] + f"\n... (truncated, {len(content)} chars total; set LLM_TRACE_FULL=1 to print all)"
        print("\n" + ("=" * 88))
        print(f"�1�70�1�78 LLM TRACE | {title}")
        print("-" * 88)
        print(txt)
        print(("=" * 88) + "\n")

    def _llm_trace_meta(self, kind: str, model: str, temperature: float, max_tokens: int, system: str = ""):
        if not self._llm_trace_enabled():
            return
        meta = {
            "provider": self.llm_provider,
            "kind": kind,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        self._llm_trace_print("meta", json.dumps(meta, ensure_ascii=False, indent=2))
        if system:
            self._llm_trace_print(f"{kind} system", system)

    def _llm_trace_decision(self, title: str, data: Dict[str, Any]):
        if not self._llm_trace_enabled():
            return
        try:
            self._llm_trace_print(title, json.dumps(data, ensure_ascii=False, indent=2))
        except Exception:
            self._llm_trace_print(title, str(data))

    def update_user_anchor_text(
        self,
        moment_id: str,
        user_note: str = "",
        transcript: str = "",
        context_transcript: str = "",
        asr_meta: Optional[Dict[str, str]] = None,
    ) -> bool:
        """在用户标记后（尤�? AFTER 秒之后）补齐/�?正展示文�?�?

        - user_note: 用于卡片�?描述（前�?优先展示�?
        - transcript: 用于详情页�1�7�Transcription�?
        - context_transcript: 会写�? *_context.txt，供后续 AI 分析引用
        """
        asr_meta = asr_meta or {}
        updated = False
        with self._moments_lock:
            for m in self.moments:
                if m.id != moment_id:
                    continue
                if user_note and not (m.user_note or "").strip():
                    m.user_note = user_note
                    updated = True
                # transcript锛氫紭鍏堚�滅獥鍙ｈ浆鍐欌�濓紙甯︽椂闂存埑鐨勫?氳?岋級锛屽嵆浣垮畠姣旀棫鏂囨湰鐭?涔熷簲瑕嗙洊銆?
                if transcript:
                    incoming = transcript.strip()
                    existing = (m.transcript or "").strip()
                    looks_like_window = (
                        "\n" in incoming
                        or "[00:" in incoming
                        or "[0" in incoming  # ��1�7?? [0:xx] / [00:xx]
                    )
                    if looks_like_window:
                        if incoming and incoming != existing:
                            m.transcript = transcript
                            updated = True
                    else:
                        # 非窗口文�?：仍按�1�7�更长则覆盖”的规则
                        if len(incoming) > len(existing):
                            m.transcript = transcript
                            updated = True

                provider = (asr_meta.get("provider") or "").strip()
                model = (asr_meta.get("model") or "").strip()
                model_dir = (asr_meta.get("model_dir") or "").strip()
                if provider and not (m.asr_provider or "").strip():
                    m.asr_provider = provider
                    updated = True
                if model and not (m.asr_model or "").strip():
                    m.asr_model = model
                    updated = True
                if model_dir and not (m.asr_model_dir or "").strip():
                    m.asr_model_dir = model_dir
                    updated = True
                break

            if updated:
                self._save_moments()

        # 同步写入 context 文件（供 AI 分析证据引用）
        if context_transcript:
            try:
                context_path = self.moments_dir / f"{moment_id}_context.txt"
                # 追加写入，不覆盖已有 header/user_note
                with open(context_path, "a", encoding="utf-8") as f:
                    f.write("\n=== transcript_context ===\n")
                    f.write(context_transcript.strip())
                    f.write("\n")
            except Exception:
                pass
        return updated

    @staticmethod
    def _extract_anthropic_text(message):
        """提取 Anthropic 消息中的文本"""
        return "".join([block.text for block in getattr(message, "content", []) if getattr(block, "type", None) == "text"]).strip()

    @staticmethod
    def _extract_tagline(text: str) -> tuple[str, str]:
        """从模型输出中抽取短标语（用于卡片/贴纸）和正文。支持中英文格式。"""
        if not text:
            return "", ""
        lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
        tagline = ""
        body_lines = []
        for ln in lines:
            # 支持中文/英文字段名
            if (ln.startswith("标题：") or ln.startswith("标题:") or ln.startswith("標題：") or ln.startswith("標題:")
                or ln.lower().startswith("label:")):
                tagline = re.split(r"[:�1�7�1�7]", ln, maxsplit=1)[-1].strip()
                continue
            body_lines.append(ln)

        # 兜底：如果没有显式“标题/label”，取第一行
        if not tagline:
            first = lines[0] if lines else ""
            tagline = first

        tagline = tagline.replace("\"", "").strip()
        if len(tagline) > 50:  # 英文标题可能更长，增大限制
            tagline = tagline[:50]
        body = "\n".join(body_lines).strip()
        if not body:
            body = text.strip()
        return tagline, body

    @staticmethod
    def _extract_detail_description(body: str) -> str:
        """从正文中抽取"详细描述"段落。支持中英文格式，兼容Markdown。"""
        if not body:
            return ""
        lines = [ln.strip() for ln in body.splitlines()]
        
        start = None
        # Regex for "Detailed Description:"
        # Matches: **Detailed Description:**, Detailed Description:, ��ϸ������, etc.
        desc_pattern = re.compile(r"^[\*\#\-\s]*(?:Detailed Description|详细描述|詳細描述)[^\n]*[:：]", re.IGNORECASE)
        
        for i, ln in enumerate(lines):
            if desc_pattern.match(ln):
                start = i
                break
        
        if start is None:
            return ""

        def _strip_prefix(s: str) -> str:
            # Use regex to strip the key part
            return re.sub(r"^[\*\#\-\s]*(?:Detailed Description|详细描述|詳細描述)[^\n]*[:：]\s*", "", s, flags=re.IGNORECASE).strip()

        out = []
        first = _strip_prefix(lines[start])
        if first:
            out.append(first)
            
        # Stop patterns (next section headers)
        stop_pattern = re.compile(r"^[\*\#\-\s]*(?:Context Positioning|上下文定位|Evidence Excerpt|证据摘录|Label|标题|Card Summary|卡片摘要|Analysis Framework Label|分析框架标签)[^\n]*[:：]", re.IGNORECASE)

        for ln in lines[start + 1 :]:
            if not ln:
                continue
            if stop_pattern.match(ln):
                break
            out.append(ln)
            
        return " ".join(out).strip()
    
    @staticmethod
    def _extract_card_summary(body: str) -> str:
        """从正文中抽取“卡片摘要”字段（用于卡片展示）。支持中英文格式。"""
        if not body:
            return ""
        lines = [ln.strip() for ln in body.splitlines()]
        for ln in lines:
            # 支持中文/英文字段名
            if (ln.startswith("��ƬժҪ��") or ln.startswith("��ƬժҪ:")
                or ln.lower().startswith("card summary:")):
                return re.split(r"[:�1�7�1�7]", ln, maxsplit=1)[-1].strip()
        return ""
    
    @staticmethod
    def _extract_framework_tags(body: str) -> str:
        """从正文中抽取“分析框架标签”字段。支持中英文格式。"""
        if not body:
            return ""
        lines = [ln.strip() for ln in body.splitlines()]
        for i, ln in enumerate(lines):
            # 支持中文/英文字段名
            if (ln.startswith("分析框架标签：") or ln.startswith("分析框架标签:")
                or ln.startswith("框架标签：") or ln.startswith("框架标签:")
                or ln.lower().startswith("analysis framework label:")):
                return re.split(r"[:�1�7�1�7]", ln, maxsplit=1)[-1].strip()
        return ""


    def _run_text_llm(self, prompt: str, system: str = "", model_override: str = None,
                      temperature: float = 0.3, max_tokens: int = 1500) -> str:
        """运行文本 LLM（支持 Qwen / Claude）"""
        model_name = model_override or self.text_model
        self._llm_trace_meta("text", model=model_name, temperature=temperature, max_tokens=max_tokens, system=system or "")
        print(f"\n[DEBUG] Qwen Prompt (len={len(prompt)}):\n{prompt[:500]}... [truncated]\n")
        self._llm_trace_print("text prompt", prompt)
        client = self._build_llm_client()
        if self.llm_provider.startswith("claude"):
            response = client.messages.create(
                model=model_name,
                system=system or "",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            out = self._extract_anthropic_text(response)
            self._llm_trace_print("text response", out)
            return out
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=120.0  # 120秒超时,应对复杂分析
            )
            out = response.choices[0].message.content.strip()
            print(f"\n[DEBUG] Qwen Response (len={len(out)}):\n{out}\n[DEBUG] END Response\n")
            self._llm_trace_print("text response", out)
            return out
        except Exception as e:
            error_msg = f"❌ LLM API调用失败: {str(e)}"
            print(error_msg)
            if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                print("🕰️ 提示: API超时,请检查网络或增加timeout值")
            return ""  # 返回空字符串,让调用方处理fallback逻辑

    def _run_vision_llm(self, image_base64: str, prompt: str, model_override: str = None,
                         temperature: float = 0.7, max_tokens: int = 500) -> str:
        """运行多模态/视觉 LLM"""
        model_name = model_override or self.vision_model
        # 只打印图片长度，避免把base64刷屏
        if self._llm_trace_enabled():
            self._llm_trace_meta("vision", model=model_name, temperature=temperature, max_tokens=max_tokens, system="")
            self._llm_trace_print("vision image", f"<image_base64 chars={len(image_base64 or '')}>")
            self._llm_trace_print("vision prompt", prompt)
        client = self._build_llm_client()
        if self.llm_provider.startswith("claude"):
            response = client.messages.create(
                model=model_name,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_base64}},
                        {"type": "text", "text": prompt}
                    ]
                }],
                max_tokens=max_tokens,
                temperature=temperature,
            )
            out = self._extract_anthropic_text(response)
            self._llm_trace_print("vision response", out)
            return out
        response = client.chat.completions.create(
            model=model_name,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
                    {"type": "text", "text": prompt}
                ]
            }],
            max_tokens=max_tokens,
            temperature=temperature
        )
        out = response.choices[0].message.content.strip()
        self._llm_trace_print("vision response", out)
        return out

    def suggest_key_moment_candidates(
        self,
        transcript_items: List[Dict[str, Any]],
        max_candidates: int = 3,
        base_timestamp: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """浠庝竴娈佃浆鍐欙紙閫氬父涓烘渶杩? 5 鍒嗛挓锛夐噷鎸戝嚭鏈�鍙?鑳界殑鍏抽敭鏃跺埢鍊欓�夈�?

        Args:
            transcript_items: [{"timestamp": epoch(float), "time": "HH:MM:SS", "text": str, ...}, ...]
            max_candidates: 返回候�1�7�数量上�?
            base_timestamp: 用于�? epoch 映射到相对时间（None 则自动用 transcript_items 朄1�7�? timestamp�?

        Returns:
            [{"timestamp": float, "time_str": str, "reason": str}, ...]
        """
        if not transcript_items or max_candidates <= 0:
            return []
        if not self.qwen_available:
            return []

        # 鑻? time 涓虹┖鎴栦粛鏄?鈥滅粷瀵规椂闂?(HH:MM:SS)鈥濆?艰嚧姝т箟锛屽彲鐢? base_timestamp 鐢熸垚鐩稿?规椂闂?
        base_ts = None
        try:
            if isinstance(base_timestamp, (int, float)):
                base_ts = float(base_timestamp)
            else:
                ts_list = [float(it.get("timestamp")) for it in transcript_items if it.get("timestamp") is not None and isinstance(it.get("timestamp"), (int, float))]
                base_ts = min(ts_list) if ts_list else None
        except Exception:
            base_ts = None

        def _format_rel(ts: float) -> str:
            if base_ts is None:
                return ""
            sec = max(0, int(round(float(ts) - float(base_ts))))
            hh = sec // 3600
            mm = (sec % 3600) // 60
            ss = sec % 60
            return f"{hh:02d}:{mm:02d}:{ss:02d}"

        # 鍙?鍙栨湁鏃堕棿+鏂囨湰鐨勮?岋紝閬垮厤鏃犳剰涔夊櫔澹?
        lines: List[str] = []
        line_by_time: Dict[str, str] = {}
        for it in transcript_items:
            ts = it.get("timestamp")
            tstr = (it.get("time") or "").strip()
            txt = (it.get("text") or "").strip()
            if not txt:
                continue
            if not isinstance(ts, (int, float)):
                continue
            if not tstr:
                tstr = _format_rel(float(ts))
            if not tstr:
                continue
            # 鎺у埗鍗曡?岄暱搴?
            if len(txt) > 120:
                txt = txt[:120] + "�1�7?"
            line = f"[{tstr}] {txt}"
            lines.append(line)
            line_by_time.setdefault(tstr, line)

        if not lines:
            return []

        # 控制 prompt 长度：最�? 220 �?
        if len(lines) > 220:
            lines = lines[-220:]

        # [Important] Force Chinese for reasoning
        zh_sys_instruction = "Output reason in Simplified Chinese."

        system = (
            f"[{zh_sys_instruction}] "
            "浣犳槸涓�涓?璇惧爞/璁茶В鍐呭?圭殑鍏抽敭鏃跺埢瀹氫綅鍣ㄣ�?"
            "浠诲姟锛氫粠缁欏畾鐨勫甫鏃堕棿鎴宠浆鍐欎腑锛屾寫鍑烘渶鍙?鑳藉�煎緱鍋氣�樺叧閿?鏃跺埢鍗＄墖鈥欑殑鏃堕棿鐐广�?"
            "鍏抽敭鏃跺埢閫氬父鍖呭惈锛氬畾涔?/缁撹?恒�侀噸瑕佹暟鎹?/瀵规瘮銆佹帹鐞嗚浆鎶樸�佹�荤粨鍗囧崕銆佹牳蹇冭?傜偣銆佸己鐑堟儏缁?/绗戠偣銆?"
            "涓嶈?佷负浜嗘壘鑰屾壘锛涘?傛灉纭?瀹炴病鏈夋槑鏄惧叧閿?鐐癸紝杩斿洖绌烘暟缁勩�?"
            "必须给出证据：evidence 必须�?从原�?写中逐字摘录的短片�?�（不允许编造）�?"
            "杈撳嚭蹇呴』鏄?涓ユ牸 JSON锛堜笉瑕佷唬鐮佸潡銆佷笉瑕侀?濆?栨枃瀛楋級銆?"
        )
        prompt = (
            f"璇蜂粠浠ヤ笅杞?鍐欎腑閫夊嚭鏈�澶? {max_candidates} 涓?鍊欓�夊叧閿?鏃跺埢銆俓n"
            "�����ʽ��[{\"time_str\":\"HH:MM:SS\",\"reason\":\"...\",\"evidence\":\"...\"}, ...]\n"
            "time_str 必须与转写里的时间戳完全丄1�7致�1�7�\n\n"
            + "\n".join(lines)
        )

        try:
            raw = self._run_text_llm(prompt=prompt, system=system, temperature=0.2, max_tokens=600)
            txt = (raw or "").strip()
            if txt.startswith("```"):
                parts = txt.split("```")
                txt = parts[1].strip() if len(parts) > 1 else txt
                if txt.startswith("json"):
                    txt = txt[4:].strip()

            data = json.loads(txt)
            if isinstance(data, dict):
                data = data.get("candidates") or data.get("items") or []
            if not isinstance(data, list):
                return []

            # time_str -> timestamp 映射（若 time 为空，使�? base_ts 生成的相对时间）
            time_to_ts: Dict[str, float] = {}
            for it in transcript_items:
                ts = it.get("timestamp")
                if not isinstance(ts, (int, float)):
                    continue
                tstr = (it.get("time") or "").strip() or _format_rel(float(ts))
                if tstr:
                    time_to_ts.setdefault(tstr, float(ts))

            out: List[Dict[str, Any]] = []
            for obj in data:
                if not isinstance(obj, dict):
                    continue
                tstr = (obj.get("time_str") or obj.get("time") or "").strip()
                if not tstr:
                    continue
                ts = time_to_ts.get(tstr)
                if ts is None:
                    continue
                reason = (obj.get("reason") or obj.get("why") or "").strip()
                evidence = (obj.get("evidence") or obj.get("quote") or "").strip()

                # 璇佹嵁蹇呴』鑳藉湪瀵瑰簲鏃堕棿鎴抽偅涓�琛屼腑鎵惧埌锛岄伩鍏嶁�滅紪浜嗕竴涓?鍏抽敭鍙ュ瓙鈥?
                if evidence:
                    src_line = line_by_time.get(tstr, "")
                    if evidence not in src_line:
                        continue

                out.append({"timestamp": float(ts), "time_str": tstr, "reason": reason, "evidence": evidence})
                if len(out) >= max_candidates:
                    break
            return out
        except Exception:
            return []

    def _save_video_clip_from_provided_frames(self, moment_id: str, provided_frames: List[Dict[str, Any]], 
                                                frame_number: int = 0, frame=None, 
                                                center_timestamp: Optional[float] = None) -> tuple:
        """鐢ㄨ皟鐢ㄦ柟鎻愪緵鐨勪竴娈靛抚搴忓垪鐢熸垚瑙嗛?戠墖娈点�?

        涓昏?佺敤浜庘�?5鍒嗛挓鍒囩墖鍒嗘瀽鈥濆満鏅?锛歠rame_buffer 鍙?淇濈暀鍑犲崄绉掞紝鏃ф椂闂寸偣浼氳繃鏈熴�?
        provided_frames ��Ԫ�ظ�ʽΪ {"frame": np.ndarray, "frame_number": int, "ts": float}�1�7?
        
        Args:
            center_timestamp: 如果提供，则�?使用该时间戳前后的帧（默认�?10秒）
        """
        if not provided_frames:
            return None, 0

        clip_frames = []
        for it in provided_frames:
            if not isinstance(it, dict):
                continue
            fr = it.get("frame")
            fn = it.get("frame_number")
            ts = it.get("ts")
            if fr is None or ts is None:
                continue
            try:
                clip_frames.append((fr, int(fn) if fn is not None else 0, float(ts)))
            except Exception:
                continue
        if len(clip_frames) < 2:
            return None, 0

        clip_frames.sort(key=lambda x: x[2])
        
        # 🎯 如果提供了center_timestamp，只保留该时间前后的�?
        if center_timestamp is not None:
            import os
            window_before = float(os.environ.get("MULTIMODAL_BEFORE_SECONDS", "15"))
            window_after = float(os.environ.get("MULTIMODAL_AFTER_SECONDS", "15"))
            
            start_ts = center_timestamp - window_before
            end_ts = center_timestamp + window_after
            
            filtered_frames = [f for f in clip_frames if start_ts <= f[2] <= end_ts]
            # 修复 f-string 乱码导致的 SyntaxError
            print(f"   �9�6�1�5 [��Ƶ֡ɸѡ] ԭʼ֡��: {len(clip_frames)}, ɸѡ��: {len(filtered_frames)}, ����: ǰ{window_before}s + ��{window_after}s = {window_before + window_after}s")
            if filtered_frames:
                clip_frames = filtered_frames
            else:
                # 如果过滤后为空，�?能是时间窗太窄或帧太少，尝试找最近的�?
                closest_frame = min(clip_frames, key=lambda f: abs(f[2] - center_timestamp))
                clip_frames = [closest_frame]
            
            if len(clip_frames) < 2: # �?保至少有两帧才能形成视�??
                return None, 0

        # 鍑嗗?囧啓鍏ヨ?嗛??
        video_filename = f"{moment_id}.mp4"
        video_path = self.moments_dir / video_filename

        try:
            import subprocess
            first_frame = clip_frames[0][0]
            h, w = first_frame.shape[:2]

            time_span = float(clip_frames[-1][2]) - float(clip_frames[0][2])
            est_fps = (len(clip_frames) / time_span) if time_span > 1e-6 else 10.0
            # 鎻愰珮鏈�灏廸ps鍒?5锛屾渶澶у埌60锛屼笌鎵嬪姩鏍囪?颁繚鎸佷竴鑷达紝纭?淇濈敾璐ㄦ祦鐣?
            est_fps = min(max(est_fps, 5.0), 60.0)

            video_duration = len(clip_frames) / est_fps

            ffmpeg_cmd = [
                'ffmpeg', '-y',
                '-f', 'rawvideo', '-pix_fmt', 'bgr24',
                '-s', f'{w}x{h}', '-r', f'{est_fps:.3f}',
                '-i', 'pipe:0',
                '-c:v', 'libx264',
                '-preset', 'slow',  # slow提供更好的压缩质量（比medium�?但质量更高）
                '-crf', '15',  # 降低�?15获得更高画质�?0-51，越小越好，18�?默�?�高质量�?
                '-b:v', '5M',  # 明确设置码率�?5Mbps，确保高质量
                '-pix_fmt', 'yuv420p',
                '-movflags', '+faststart',
                str(video_path)
            ]
            process = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            for fr, _, _ in clip_frames:
                process.stdin.write(fr.tobytes())
            process.stdin.close()
            process.wait(timeout=30)

            if video_path.exists() and video_path.stat().st_size > 1000:
                print(f"   💾 视频片段已保存(切片帧): {video_filename} ({len(clip_frames)}帧, {video_duration:.1f}秒, fps≈{est_fps:.1f})")
                # 尝试补音频（如果麦克风录制器可用，会按 epoch 对齐截音）
                try:
                    self._add_audio_to_video(moment_id, str(video_path), frame_number, float(video_duration), frame)
                except Exception:
                    pass
                return str(video_path), float(video_duration)
        except Exception:
            return None, 0

        return None, 0
    
    def reset_session(self):
        """重置会话 (新的录制)"""
        self.moments = []
        self.start_time = time.time()
        self.frame_count = 0
        self.last_ai_analysis_time = 0
        self.ai_analysis_buffer = []
        self.stats = {"user_anchors": 0, "ai_detected": 0, "total_moments": 0}
    print("🔄 KeyMomentsManager 会话已重置")

    def delete_frame_from_timeline(self, person_id: int, frame_num: int):
        """删除 timeline �?的特定帧
        
        �?前实现为空操作，因为 timeline 数据来自 face_db.detection_history
        真�?�的删除�? FaceDatabase.delete_person() �?处理
        """
        # Timeline 数据来自 face_db，所以删除由后�??�? face_db �?处理
        print(f"�? 已从 timeline 删除 Frame {frame_num}")
    
    def delete_moment(self, moment_id: str):
        """删除丄1�7�?关键时刻
        
        Args:
            moment_id: 关键时刻 ID
        """
        # 从列表中删除
        self.moments = [m for m in self.moments if m.id != moment_id]
        
        # 删除对应的文�?
        moment_dir = self.moments_dir / moment_id
        if moment_dir.exists():
            import shutil
            shutil.rmtree(moment_dir)
            print(f"�? 已删除关�?时刻 {moment_id}")
        
        # 重新保存
        self._save_moments()
        print(f"�? 已更新关�?时刻数据")
    
    # ============================================================
    # 🔴 用户标�?? (The Anchor)
    # ============================================================
    
    def add_frame_to_buffer(self, frame, frame_number: int):
        """
        将帧添加到缓冲区 (每帧调用)
        
        Args:
            frame: ��ǰ�1�7? (numpy array)
            frame_number: ֡��
        """
        import cv2
        
        # 閽堝?归珮鍒嗚鲸鐜?(濡?8083澶氭憚)浼樺寲锛氬?傛灉鍒嗚鲸鐜囪繃楂橈紝缂╁皬瀛樺偍浠ラ槻姝?OOM鍜屽崱椤?
        frame_to_store = frame
        h, w = frame.shape[:2]
        if w > 1920:
            scale = 1920 / w
            new_h = int(h * scale)
            frame_to_store = cv2.resize(frame, (1920, new_h))
        
        # 使用 JPEG 压缩存储以节省内�? (1280x720 raw=2.7MB, jpeg~=200KB)
        # 降低 quality �? 80 以进丄1�7步优�?
        success, buffer = cv2.imencode('.jpg', frame_to_store, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not success:
            return
            
        with self.buffer_lock:
            # �洢��ʽ: (jpeg_buffer, frame_num, timestamp)
            self.frame_buffer.append((buffer, frame_number, time.time()))
            # 保持缓冲区大小在限制�?
            while len(self.frame_buffer) > self.buffer_max_frames:
                if len(self.frame_buffer) % 500 == 0:
                     print(f"   �1�70�1�78 [BUFFER] Popping frame! Size={len(self.frame_buffer)}, Max={self.buffer_max_frames}")
                self.frame_buffer.pop(0)
    
    def add_audio_frame_to_buffer(self, audio_chunk: bytes, timestamp: float = None):
        """
        将音频帧添加到缓冲区 (实时调用)
        
        Args:
            audio_chunk: 音�?�数�?�? (bytes)
            timestamp: 时间�? (如果为None，使用当前时�?)
        """
        if timestamp is None:
            timestamp = time.time()
        
        with self.audio_buffer_lock:
            self.audio_buffer.append((audio_chunk, timestamp))
            # 保持音�?�缓冲区大小在限制内�?25秒音�? @16kHz 16-bit�?
            # 估�?�每�? 16000 * 2 = 32KB
            while len(self.audio_buffer) > self.buffer_max_frames * 32768:  
                self.audio_buffer.pop(0)
    
    def _add_audio_to_video(self, moment_id: str, video_path: str, frame_number: int, video_duration: float,
                            frame=None, center_timestamp: float = None, window_before: float = None, window_after: float = None):
        """
        娣诲姞闊抽?戝埌瑙嗛?戯紙楹﹀厠椋庢垨瑙嗛?戞簮锛?
        
        Args:
            moment_id: 关键时刻ID
            video_path: 视�?�路�?
            frame_number: ֡��
            video_duration: 视�?�时�?
            frame: 关键帧图�? (用于AI分析)
        """
        import math

        # 优先使用麦克风录制的音�??
        if self.microphone_recorder:
            print("   🎤 从麦克风保存音频...")
            # 为避免截�?，取 ceil + 1 �?
            fallback_seconds = int(math.ceil(float(video_duration))) + 1

            audio_path = None
            if center_timestamp is not None and window_before is not None and window_after is not None:
                # 鍏抽敭鏃跺埢瀹屾暣瑙嗛?戯細鎸夊悓涓�鏃堕棿绐楀?归綈闊抽??
                try:
                    audio_path = self.microphone_recorder.save_audio_around(
                        center_timestamp=float(center_timestamp),
                        before_seconds=float(window_before),
                        after_seconds=float(window_after),
                        fallback_seconds=float(fallback_seconds),
                    )
                except Exception:
                    audio_path = None
            if not audio_path:
                # 鍏朵粬鍦烘櫙锛氬洖閫�涓衡�滄渶杩慛绉掆�?
                audio_path = self.microphone_recorder.save_audio_clip(duration_seconds=fallback_seconds)
            if audio_path:
                self._merge_audio_to_video_async(moment_id, video_path, audio_path, frame, video_duration=video_duration)
            else:
                print(f"   ⚠️ 麦克风音频保存失败，跳过�?音转文字")
        # 鍚﹀垯浠庤?嗛?戞簮鎻愬彇闊抽??
        elif self.audio_source and Path(self.audio_source).exists():
            print("   🎧 从视频源提取音频...")
            self._extract_and_merge_audio_async(moment_id, video_path, frame_number, video_duration, frame)
        else:
            print(f"   ⚠️ 无可用音频源 (麦克�?: {bool(self.microphone_recorder)}, 视�?�源: {self.audio_source})")
            print(f"   ℹ️ 视�?�将�?包含画面，�??音转文字功能不可�?")
            # 即使无音频，也应触发�?视�?�AI分析 / 模拟按键后的处理
            print("   🤖 触发无音频模式的 AI 分析...")
            if frame is not None:
                # 放在后台线程避免阻�??
                threading.Thread(
                    target=self._process_video_with_multimodal_analysis,
                    args=(moment_id, video_path, frame),
                    daemon=True
                ).start()
    
    def _merge_audio_to_video_async(self, moment_id: str, video_path: str, audio_path: str, frame=None, video_duration: float = None):
        """寮傛?ュ悎骞堕煶棰戝拰瑙嗛?戯紝瀹屾垚鍚庤繘琛岃??闊宠浆鏂囧瓧鍜孉I鍒嗘瀽"""
        def merge_task():
            try:
                import subprocess
                import math
                temp_video = Path(video_path).parent / f"{moment_id}_temp.mp4"
                Path(video_path).rename(temp_video)
                
                print("   🧾 [DEBUG] 合并命令:")
                print(f"      �ӄ1�7??: {temp_video}")
                print(f"      ��1�7??: {audio_path}")
                print(f"      ���: {video_path}")
                
                # 鍏抽敭鐐癸細涓嶈?佺敤 -shortest锛屽惁鍒欎細鎶婅緭鍑鸿?佸埌鏇寸煭鐨勯偅涓�璺?锛屽?艰嚧鈥滃彧璇嗗埆涓�鍗?/瑙嗛?戝彉鐭?鈥濄�?
                # 这里固定输出为�?��?�时长，并用 apad 在需要时给音频补静音�?
                duration = None
                try:
                    if video_duration is not None and float(video_duration) > 0:
                        duration = float(video_duration)
                except Exception:
                    duration = None

                cmd = ['ffmpeg', '-y', '-loglevel', 'error', '-i', str(temp_video), '-i', audio_path]
                cmd += ['-map', '0:v:0', '-map', '1:a:0?']
                cmd += ['-c:v', 'copy', '-c:a', 'aac', '-b:a', '128k']
                if duration is not None:
                    # apad 让音频不足时补静音，-t 固定输出时长
                    cmd += ['-af', f"apad=pad_dur={max(0.1, duration):.3f}", '-t', f"{duration:.3f}"]
                cmd += ['-movflags', '+faststart', str(video_path)]
                
                print(f"   �0�8 [DEBUG] FFmpeg����: {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                
                if result.returncode == 0:
                    print(f"   �? [后台] 音�?�合并成�?")
                    temp_video.unlink()
                    Path(audio_path).unlink()  # 清理临时音�?�文�?
                    
                    # 🎤📹 触发�?音转文字 + AI多模态分�?
                    print(f"   🎤 弄1�7始�??音转文字和AI分析...")
                    self._process_video_with_multimodal_analysis(moment_id, video_path, frame)
                else:
                    print(f"   �? [后台] FFmpeg返回错�??�?: {result.returncode}")
                    print(f"   �1�7? stderr: {result.stderr}")
                    print(f"   ⚠️ [后台] 恢�?�原视�??")
                    temp_video.rename(video_path)
            except Exception as e:
                print(f"   ⚠️ [后台] 音�?�合并异�?: {e}")
                import traceback
                traceback.print_exc()
        
        thread = threading.Thread(target=merge_task, daemon=True)
        thread.start()
    
    def _extract_and_merge_audio_async(self, moment_id: str, video_path: str, frame_number: int, video_duration: float, frame=None):
        """
        鍚庡彴寮傛?ユ彁鍙栬?嗛?戞枃浠朵腑鐨勯煶棰戝苟鍚堝苟鍒板凡淇濆瓨鐨勮?嗛?戯紝瀹屾垚鍚庤繘琛岃??闊宠浆鏂囧瓧鍜孉I鍒嗘瀽
        
        Args:
            moment_id: 关键时刻ID
            video_path: 已保存的视�?�路�?
            frame_number: 帧号（用于�?�算时间位置�?
            video_duration: 视�?�时�?
            frame: 关键帧图�? (用于AI分析)
        """
        def merge_task():
            try:
                import subprocess
                
                # 璁＄畻鍦ㄦ簮瑙嗛?戜腑鐨勪綅缃?锛堝敖閲忎娇鐢ㄧ湡瀹? fps锛?
                assumed_fps = self.video_fps if (self.video_fps and self.video_fps > 1e-6) else 30.0
                source_start_time = frame_number / float(assumed_fps)
                
                print(f"   🔊 [后台] 从源视�?�提取音�? (�?{frame_number} = {source_start_time:.1f}s)...")
                
                # 涓存椂闊抽?戞枃浠?
                audio_path = Path(video_path).parent / f"{moment_id}_audio.m4a"
                output_path = Path(video_path).parent / f"{moment_id}_with_audio.mp4"
                
                # 姝ラ??1: 浠庢簮瑙嗛?戞彁鍙栭煶棰?
                cmd_extract = [
                    'ffmpeg', '-y', '-loglevel', 'error',
                    '-ss', str(source_start_time),
                    '-t', str(video_duration + 1),  # 多提�?1秒作为缓�?
                    '-i', str(self.audio_source),
                    '-vn',
                    '-map', '0:a:0?',
                    '-c:a', 'aac', '-b:a', '128k',
                    str(audio_path)
                ]
                
                result = subprocess.run(cmd_extract, timeout=30)

                def _maybe_backfill_transcript_from_source():
                    """当合并音频失败时，仍尝试从源视�?�直接提�? WAV 并做 ASR，避�? transcript 为空�?"""
                    try:
                        wav_path = Path(video_path).parent / f"{moment_id}_asr_fallback.wav"
                        cmd_wav = [
                            'ffmpeg', '-y', '-loglevel', 'error',
                            '-ss', str(source_start_time),
                            '-t', str(video_duration + 1),
                            '-i', str(self.audio_source),
                            '-vn',
                            '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1',
                            str(wav_path)
                        ]
                        r = subprocess.run(cmd_wav, timeout=60)
                        if r.returncode != 0 or not wav_path.exists() or wav_path.stat().st_size < 2000:
                            return
                        transcript = self._transcribe_audio(wav_path)
                        try:
                            wav_path.unlink()
                        except Exception:
                            pass
                        if not transcript:
                            return
                        for moment in self.moments:
                            if moment.id == moment_id:
                                # �?在缺失时回填，避免�?�盖更完整结�?
                                if not (moment.transcript or "").strip():
                                    moment.transcript = transcript
                                    moment.asr_provider = (self._last_asr_meta.get("provider") or "")
                                    moment.asr_model = (self._last_asr_meta.get("model") or "")
                                    moment.asr_model_dir = (self._last_asr_meta.get("model_dir") or "")
                                    self._save_moments()
                                break
                        if frame is not None:
                            try:
                                self._analyze_moment_with_ai(frame, moment_id, transcript)
                            except Exception:
                                pass
                    except Exception:
                        pass

                if result.returncode != 0 or (not audio_path.exists()) or audio_path.stat().st_size < 500:
                    print(f"   ⚠️ [后台] 音�?�提取失�?")
                    _maybe_backfill_transcript_from_source()
                    return
                
                print(f"   �? [后台] 音�?�提取成�?")
                
                # 姝ラ??2: 鍚堝苟闊宠?嗛??
                cmd_merge = [
                    'ffmpeg', '-y', '-loglevel', 'error',
                    '-i', str(video_path),
                    '-i', str(audio_path),
                    '-map', '0:v:0', '-map', '1:a:0?',
                    '-c:v', 'copy', '-c:a', 'aac', '-b:a', '128k',
                    '-af', f"apad=pad_dur={max(0.1, float(video_duration)):.3f}",
                    '-t', f"{float(video_duration):.3f}",
                    '-movflags', '+faststart',
                    str(output_path)
                ]
                
                result = subprocess.run(cmd_merge, timeout=60)
                
                if result.returncode == 0 and output_path.exists():
                    # 鐢ㄥ悎骞跺悗鐨勮?嗛?戞浛鎹㈠師瑙嗛??
                    Path(video_path).unlink()
                    output_path.rename(video_path)
                    audio_path.unlink()
                    print(f"   �? [后台] 音�?�合并成�?")
                    
                    # 🎤📹 触发�?音转文字 + AI多模态分�?
                    print(f"   🎤 弄1�7始�??音转文字和AI分析...")
                    self._process_video_with_multimodal_analysis(moment_id, video_path, frame)
                else:
                    print(f"   ⚠️ [后台] 音�?�合并失败，保留原�?��??")
                    _maybe_backfill_transcript_from_source()
                    
            except subprocess.TimeoutExpired:
                print(f"   ⚠️ [后台] 音�?��?�理超时")
            except Exception as e:
                print(f"   ⚠️ [后台] 音�?��?�理异常: {e}")
        
        # 鍚?鍔ㄥ悗鍙扮嚎绋?
        thread = threading.Thread(target=merge_task, daemon=True)
        thread.start()
    
    def _extract_audio_from_video(self, video_source: str, start_time: float, 
                                   duration: float, output_audio_path: str) -> bool:
        """
        浠庤?嗛?戞枃浠舵彁鍙栨寚瀹氭椂闂存?电殑闊抽??
        
        Args:
            video_source: 婧愯?嗛?戞枃浠惰矾寰?
            start_time: 寮�濮嬫椂闂? (绉?, 鐩稿?逛簬鏂囦欢寮�濮?)
            duration: 提取时长 (�?)
            output_audio_path: 输出音�?�文件路�?
            
        Returns:
            True 如果成功, False 如果失败
        """
        try:
            import subprocess
            
            # 使用 ffmpeg 提取音�??
            ffmpeg_cmd = [
                'ffmpeg', '-y', '-loglevel', 'error',
                '-ss', str(start_time),
                '-t', str(duration),
                '-i', str(video_source),
                '-vn',
                '-map', '0:a:0?',
                '-c:a', 'aac', '-b:a', '128k',
                str(output_audio_path)
            ]
            
            process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            returncode = process.wait(timeout=30)
            
            if returncode == 0 and Path(output_audio_path).exists():
                file_size = Path(output_audio_path).stat().st_size
                if file_size > 100:  # 至少100字节
                    print(f"   🔊 音�?�已提取: {Path(output_audio_path).name} ({file_size} bytes)")
                    return True
            
            return False
            
        except Exception as e:
            print(f"   ⚠️ 音�?�提取失�?: {e}")
            return False
    
    def _merge_audio_to_video(self, video_path: str, audio_path: str, 
                              output_path: str) -> bool:
        """
        灏嗛煶棰戣建閬撳悎骞跺埌瑙嗛?戞枃浠?
        
        Args:
            video_path: 瑙嗛?戞枃浠惰矾寰? (鍚?瑙嗛?戜絾鏃犻煶棰?)
            audio_path: 音�?�文件路�?
            output_path: 输出文件�?�?
            
        Returns:
            True 如果成功, False 如果失败
        """
        try:
            import subprocess
            
            # 使用 ffmpeg 合并音�?��??
            ffmpeg_cmd = [
                'ffmpeg', '-y',
                '-i', str(video_path),
                '-i', str(audio_path),
                '-c:v', 'copy',  # 直接复制视�?�流
                '-c:a', 'aac',   # 重新编码音�?�为AAC
                '-shortest',  # 以较�?的流长度为准
                '-n',  # 不�?�盖
                str(output_path)
            ]
            
            process = subprocess.Popen(
                ffmpeg_cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            returncode = process.wait(timeout=60)
            
            if returncode == 0 and Path(output_path).exists():
                original_size = Path(video_path).stat().st_size
                merged_size = Path(output_path).stat().st_size
                print(f"   🎬 音�?��?�已合并: {Path(output_path).name} ({merged_size} bytes)")
                
                # 删除临时文件
                try:
                    Path(video_path).unlink()
                    Path(audio_path).unlink()
                except:
                    pass
                
                return True
            
            return False
            
        except Exception as e:
            print(f"   鈿狅笍 闊宠?嗛?戝悎骞跺け璐?: {e}")
            return False
    
    def _save_video_clip(self, moment_id: str, clip_duration_before: float = 10.0,
                         clip_duration_after: float = 0.0, frame_number: int = 0, frame=None,
                         center_timestamp: Optional[float] = None) -> tuple:
        """
        浠庡抚缂撳啿鍖轰繚瀛樿?嗛?戠墖娈?
        
        Args:
            moment_id: 关键时刻ID
            clip_duration_before: 鏍囪?版椂鍒诲墠淇濈暀鐨勭?掓暟 (榛樿??10绉?)
            clip_duration_after: 标�?�时刻后等待的�?�数 (霄1�7要异步实�?)
            
        Returns:
            (video_path, duration) �? (None, 0) 如果失败
        """
        import cv2
        
        with self.buffer_lock:
            if len(self.frame_buffer) < 10:  # 至少霄1�7�?10�?
                print(f"   ⚠️ 帧缓冲区不足，无法生成�?��?? ({len(self.frame_buffer)} �?)")
                return None, 0
            
            # 🔍 调试：打印buffer状�1�7?
            if self.frame_buffer:
                buffer_start_ts = self.frame_buffer[0][2]
                buffer_end_ts = self.frame_buffer[-1][2]
                buffer_span = buffer_end_ts - buffer_start_ts
                print(f"   🔍 [DEBUG] Buffer状�1�7?: {len(self.frame_buffer)} �?, 时间跨度: {buffer_span:.1f}�?")
                print(f"   �1�79�1�73 [DEBUG] Buffer�1�7�1�7��: [{buffer_start_ts:.2f}, {buffer_end_ts:.2f}]")
            
            # 获取�? center_timestamp 为中心的帧（默�?�用当前时刻�?
            center_ts = float(center_timestamp) if isinstance(center_timestamp, (int, float)) else time.time()
            start_ts = center_ts - float(clip_duration_before)
            end_ts = center_ts + float(clip_duration_after)
            
            print(f"   �9�3 [DEBUG] �1�7?�괰�1�7?: [{start_ts:.2f}, {end_ts:.2f}], �1�7?�1�7?: {center_ts:.2f}")
            print(f"   �9�3 [DEBUG] ���ڿ���: {clip_duration_before:.1f}s (�1�7?) + {clip_duration_after:.1f}s (�1�7?) = {clip_duration_before + clip_duration_after:.1f}s")
            
            clip_frames = []
            for frame_buf, frame_num, ts in self.frame_buffer:
                if start_ts <= ts <= end_ts:
                    # 解码 JPEG
                    frame = cv2.imdecode(frame_buf, cv2.IMREAD_COLOR)
                    if frame is not None:
                        clip_frames.append((frame, frame_num, ts))
            
            print(f"   🔍 [DEBUG] 筛�1�7�结�?: 收集�? {len(clip_frames)} �?")
        
        if len(clip_frames) == 0:
            # timestamp不在buffer范围（历史时刻已过期），使用当前时间重试
            print(f"   ⚠️ 历史timestamp不在buffer范围，使用当前时间重新筛�?")
            center_ts = time.time()
            start_ts = center_ts - float(clip_duration_before)
            end_ts = center_ts + float(clip_duration_after)
            
            print(f"   �9�3 [RETRY] �´��1�7?: [{start_ts:.2f}, {end_ts:.2f}], �1�7?�1�7?: {center_ts:.2f}")
            
            # 先收集当前可用的�?
            for frame_buf, frame_num, ts in self.frame_buffer:
                if start_ts <= ts <= end_ts:
                    # 解码 JPEG
                    frame = cv2.imdecode(frame_buf, cv2.IMREAD_COLOR)
                    if frame is not None:
                        clip_frames.append((frame, frame_num, ts))
            
            print(f"   🔍 [RETRY] 初�?�筛选结�?: 收集�? {len(clip_frames)} �?")
            
            # 如果霄1�7要后�?帧，等待buffer收集
            if clip_duration_after > 0 and len(clip_frames) < 1800:
                wait_seconds = float(clip_duration_after)
                print(f"   �? 等待 {wait_seconds:.0f}�? 收集后续�?...")
                time.sleep(wait_seconds)
                
                # 閲嶆柊绛涢�夛紝鍖呭惈鏂版敹闆嗙殑甯?
                clip_frames = []
                with self.buffer_lock:
                    for frame_buf, frame_num, ts in self.frame_buffer:
                        if start_ts <= ts <= end_ts:
                            frame = cv2.imdecode(frame_buf, cv2.IMREAD_COLOR)
                            if frame is not None:
                                clip_frames.append((frame, frame_num, ts))
                
                print(f"   🔍 [RETRY] 等待后筛选结�?: 收集�? {len(clip_frames)} �?")
        
        if len(clip_frames) < 10:
            # 濡傛灉浠嶇劧涓嶅?燂紙buffer鏈?韬?澶?灏忥級锛屼娇鐢ㄦ渶杩戜竴娈电紦鍐插尯鍏滃簳
            print(f"   ⚠️ 筛�1�7�帧数仍然不�? ({len(clip_frames)} < 10)，使用最�?300帧兜�?")
            # 同样霄1�7要解�?
            clip_frames = []
            for frame_buf, frame_num, ts in list(self.frame_buffer)[-300:]:
                frame = cv2.imdecode(frame_buf, cv2.IMREAD_COLOR)
                if frame is not None:
                    clip_frames.append((frame, frame_num, ts))
        
        if not clip_frames:
            return None, 0
        
        # 鍑嗗?囧啓鍏ヨ?嗛??
        video_filename = f"{moment_id}.mp4"
        video_path = self.moments_dir / video_filename
        
        try:
            import subprocess
            
            # 获取帧尺�?
            first_frame = clip_frames[0][0]
            h, w = first_frame.shape[:2]
            
            # 计算实际帧率
            time_span = clip_frames[-1][2] - clip_frames[0][2]
            actual_fps = len(clip_frames) / time_span if time_span > 0 else 30
            actual_fps = min(max(actual_fps, 15), 60)  # ���Ƅ1�7?15-60fps
            
            video_duration = len(clip_frames) / actual_fps
            
            # 方法1: 尝试使用 ffmpeg 管道直接输出 H.264 MP4
            try:
                # 使用 ffmpeg 从原始帧数据创建视�??
                ffmpeg_cmd = [
                    'ffmpeg', '-y',
                    '-f', 'rawvideo', '-pix_fmt', 'bgr24',
                    '-s', f'{w}x{h}', '-r', str(int(actual_fps)),
                    '-i', 'pipe:0',
                    '-c:v', 'libx264',
                    '-preset', 'slow',  # slow提供更好的压缩质�?
                    '-crf', '15',  # 高画�?（与LLM识别保持丄1�7致）
                    '-b:v', '5M',  # 5Mbps码率�?保高质量
                    '-pix_fmt', 'yuv420p',
                    '-movflags', '+faststart',
                    str(video_path)
                ]
                
                process = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, 
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                for frame, _, _ in clip_frames:
                    process.stdin.write(frame.tobytes())
                
                process.stdin.close()
                process.wait(timeout=30)
                
                if video_path.exists() and video_path.stat().st_size > 1000:
                    print(f"   🎬 视�?�片段已保存 (H.264): {video_filename} ({len(clip_frames)}�?, {video_duration:.1f}�?)")
                    
                    # 🔊 添加音�??
                    self._add_audio_to_video(moment_id, str(video_path), frame_number, video_duration, frame)
                    
                    return str(video_path), video_duration
                    
            except Exception as e:
                print(f"   ⚠️ ffmpeg 方法失败: {e}")
            
            # 鏂规硶2: 鍥為��鍒? OpenCV 淇濆瓨 (鍙?鑳芥棤娉曞湪娴忚?堝櫒鎾?鏀?)
            fourcc = cv2.VideoWriter_fourcc(*'avc1')  # ���� H.264
            writer = cv2.VideoWriter(str(video_path), fourcc, actual_fps, (w, h))
            
            if not writer.isOpened():
                # 如果 avc1 不可�?，使�? mp4v
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                writer = cv2.VideoWriter(str(video_path), fourcc, actual_fps, (w, h))
            
            for frame, _, _ in clip_frames:
                writer.write(frame)
            
            writer.release()
            
            print(f"   🎬 视�?�片段已保存 (OpenCV): {video_filename} ({len(clip_frames)}�?, {video_duration:.1f}�?)")
            
            # 🔊 添加音�??
            self._add_audio_to_video(moment_id, str(video_path), frame_number, video_duration, frame)
            
            return str(video_path), video_duration
            
        except Exception as e:
            print(f"   �? 保存视�?�失�?: {e}")
            import traceback
            traceback.print_exc()
            return None, 0
    
    def _add_audio_to_clip_async(self, moment_id: str, video_path: str, 
                                  start_timestamp: float, duration: float, frame_number: int = 0):
        """
        鍦ㄥ悗鍙扮嚎绋嬩腑浠庢簮瑙嗛?戜腑鎻愬彇闊抽?戝苟娣诲姞鍒板叧閿?鏃跺埢瑙嗛??
        姝ゅ嚱鏁板湪鍚庡彴杩愯?岋紝涓嶉樆濉炰富瑙嗛?戝?勭悊绾跨▼
        
        Args:
            moment_id: 关键时刻ID
            video_path: 视�?�文件路�? (不含音�??)
            start_timestamp: 视�?�片段在系统�?的开始时间戳 (用于日志)
            duration: 瑙嗛?戠墖娈垫椂闀? (绉?)
            frame_number: 关键时刻的帧�? (用于计算视�?�中的位�?)
        """
        try:
            print(f"   �9�0 [��̨�߳�Ū1�1�77ʼ] moment_id={moment_id}, audio_source={self.audio_source}")
            
            if not self.audio_source:
                print(f"   ⚠️ [后台线程] audio_source �? None")
                return
                
            if not Path(self.audio_source).exists():
                print(f"   ⚠️ [后台线程] 音�?�源不存�?: {self.audio_source}")
                return
            
            # 计算在源视�?�中的起始时�? (基于帧号和尽量真实的FPS)
            assumed_fps = self.video_fps if (self.video_fps and self.video_fps > 1e-6) else 30.0
            source_start_time = frame_number / float(assumed_fps)
            
            # 提取音�??
            audio_path = Path(video_path).parent / f"{moment_id}_audio.m4a"
            
            print(f"   🎬 [后台] 正在从源视�?�提取音�? (�?{frame_number} = {source_start_time:.1f}s)...")
            
            audio_extracted = self._extract_audio_from_video(
                self.audio_source,
                source_start_time,
                duration + 1,  # 多提�?1秒作为缓�?
                str(audio_path)
            )
            
            if not audio_extracted:
                print(f"   鈿狅笍 [鍚庡彴] 鏈?鑳戒粠婧愯?嗛?戞彁鍙栭煶棰?")
                return
            
            # 鍚堝苟闊宠?嗛??
            temp_video_path = Path(video_path).parent / f"{moment_id}_temp.mp4"
            if Path(video_path).exists():
                Path(video_path).rename(temp_video_path)
            
            print(f"   🔗 [后台] 正在合并音�?��??...")
            audio_merged = self._merge_audio_to_video(
                str(temp_video_path),
                str(audio_path),
                video_path
            )
            
            if not audio_merged:
                # 濡傛灉鍚堝苟澶辫触, 鎭㈠?嶅師濮嬭?嗛??
                print(f"   ⚠️ [后台] 合并失败，使用无音�?�版�?")
                try:
                    if temp_video_path.exists():
                        temp_video_path.rename(video_path)
                except:
                    pass
            else:
                print(f"   �? [后台] 音�?�已成功合并")
            
            print(f"   �? [后台线程完成]")
            
        except Exception as e:
            print(f"   ⚠️ [后台线程异常] {e}")
            import traceback
            traceback.print_exc()
    
    def _add_audio_to_clip(self, moment_id: str, video_path: str, 
                           start_timestamp: float, duration: float, frame_number: int = 0):
        """
        在后台线程中异�?�添加音频轨�? (不阻塞主线程)
        """
        print(f"   🔊 [主线程] _add_audio_to_clip �?调用，moment_id={moment_id}")
        thread = threading.Thread(
            target=self._add_audio_to_clip_async,
            args=(moment_id, video_path, start_timestamp, duration, frame_number),
            daemon=True
        )
        print(f"   🔊 [主线程] �?动后台线�?...")
        thread.start()
        print(f"   🔊 [主线程] 后台线程已启�?")

    def mark_user_anchor(self, frame, frame_number: int, 
                         person_count: int = 0, track_ids: List[int] = None,
                         user_note: str = "", transcript: str = "", context_transcript: str = "",
                         source: str = None) -> KeyMoment:
        """
        鐢ㄦ埛鎸変笅鎸夐挳鏍囪?板綋鍓嶆椂鍒? (0.5绉掓剰鍥鹃敋瀹?)
        保存�? KEY_MOMENT_BEFORE_SECONDS 秒的视�?�，并启动后台任务等�? KEY_MOMENT_AFTER_SECONDS �?
        
        Args:
            frame: ��ǰ֡ͼ�1�7? (numpy array)
            frame_number: ֡��
            person_count: 当前人数
            track_ids: 活跃的追踪ID
            user_note: 用户备注
            transcript: 鏈�杩戠殑璇?闊宠浆鏂囧瓧鍐呭?癸紙鐢ㄤ簬鍗虫椂灞曠ず锛?
            context_transcript: 更长的历史上下文（用于后续AI分析，可能�??�?�?�?
            source: 来源 (默�?? USER_ANCHOR, �?指定 AI_DETECTED)
            
        Returns:
            创建�? KeyMoment 对象
        """
        import cv2
        
        timestamp = time.time()
        duration = timestamp - self.start_time
        time_str = self._format_time(duration)
        
        # 生成�?丄1�7ID
        moment_id = f"anchor_{int(timestamp)}_{frame_number}"
        
        try:
            # 保存关键�?
            frame_filename = f"{moment_id}.jpg"
            frame_path = self.moments_dir / frame_filename
            print(f"   �1�79�1�79 [DEBUG] Saving keyframe to {frame_path}")
            
            # 使用高画质保�?
            cv2.imwrite(str(frame_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            
            # 验证文件�?否生�?
            if not frame_path.exists() or frame_path.stat().st_size == 0:
                print(f"   �1�7? [ERROR] Keyframe file creation failed: {frame_path}")
        except Exception as e:
            print(f"   �1�7? [ERROR] Failed to save keyframe image: {e}")
            import traceback
            traceback.print_exc()

        # 为�?�关�?时刻保存上下文（按键原因 + 历史�?写），供后续AI分析读取
        try:
            context_path = self.moments_dir / f"{moment_id}_context.txt"
            with open(context_path, "w", encoding="utf-8") as f:
                f.write(f"moment_id: {moment_id}\n")
                f.write(f"timestamp: {timestamp:.3f}\n")
                if user_note:
                    f.write(f"user_note: {user_note}\n")
                if context_transcript:
                    f.write("\n=== transcript_context ===\n")
                    f.write(context_transcript)
                    f.write("\n")
        except Exception:
            pass

        # 纭?瀹氭潵婧?
        moment_source = source if source else MomentSource.USER_ANCHOR.value

        # 创建关键时刻 (视�?�路径暂空，由后台线程生�?)
        try:
            moment = KeyMoment(
                id=moment_id,
                timestamp=timestamp,
                frame_number=frame_number,
                source=moment_source,
                frame_path=str(frame_path),
                video_path="",  # ��ʱΪ��
                video_duration=0.0,
                time_str=time_str,
                duration_seconds=duration,
                user_note=user_note,
                transcript=transcript,  # 保存�?音转文字
                person_count=person_count,
                track_ids=track_ids or []
            )
            
            self.moments.append(moment)
            self.stats["user_anchors"] += 1
            self.stats["total_moments"] += 1
            print(f"   �1�77�1�73 [DEBUG] Moment object created and appended. Total: {len(self.moments)}")
            
        except Exception as e:
            print(f"   �1�7? [ERROR] Failed to create KeyMoment object: {e}")
            import traceback
            traceback.print_exc()
            return None
        
        # 立即保存丄1�7次，�?保前�?能立即刷出卡片并触发特效
        self._save_moments()
        
        print(f"🔴 用户标�?�关�?时刻: {time_str} (�? {frame_number})")
        if user_note:
            print(f"   �9�5 ��ע: {user_note}")
        if transcript:
            print(f"   🎤 实时�?音片�?: {transcript[:50]}...")
        
        # 馃幀 鍚?鍔ㄥ悗鍙扮嚎绋?: 1.淇濆瓨鍒濆?嬭?嗛?? -> 2.绛夊緟鎵╁睍 -> 3.瑙﹀彂AI鍒嗘瀽
        def async_video_processing():
            # 1. 保存�? KEY_MOMENT_BEFORE_SECONDS 秒的视�?�片�?
            try:
                video_path, video_duration = self._save_video_clip(
                    moment_id,
                    clip_duration_before=float(KEY_MOMENT_BEFORE_SECONDS),
                    frame_number=frame_number,
                    center_timestamp=timestamp,
                )
                
                if video_path:
                    print(f"   💾 初始视频已生成 (前{KEY_MOMENT_BEFORE_SECONDS:.0f}秒): {video_duration:.1f}秒")
                    moment.video_path = video_path
                    moment.video_duration = video_duration
                    moment.video_path = video_path
                    moment.video_duration = video_duration
                    self._save_moments() # 更新视�?�路�?
            except Exception as e:
                print(f"   鉂? 鍒濆?嬭?嗛?戠敓鎴愬け璐?: {e}")

            # 2. 等待 after 秒后生成包含后�?�的完整视�??
            print(f"   �? {KEY_MOMENT_AFTER_SECONDS:.0f}秒后将扩展完整�?��?�并进�?�AI分析...")
            time.sleep(float(KEY_MOMENT_AFTER_SECONDS))  # 等待收集后续�?
            self._extend_video_with_after_frames(moment_id, timestamp, frame.copy())
        
        processing_thread = threading.Thread(target=async_video_processing, daemon=True)
        processing_thread.start()
        
        return moment

    def _extend_video_with_after_frames(self, moment_id: str, original_timestamp: float, frame=None):
        """
        延迟调用：合并标记时刻前后各10秒的视�??
        
        Args:
            moment_id: 关键时刻ID
            original_timestamp: 原�?�标记的时间�?
            frame: 关键帧图�? (用于后续AI分析)
        """
        import cv2
        
        print(f"   🎬 [完整视�?�扩展] 弄1�7始�?�理 moment_id={moment_id}, timestamp={original_timestamp:.2f}")
        
        try:
            with self.buffer_lock:
                before_s = float(KEY_MOMENT_BEFORE_SECONDS)
                after_s = float(KEY_MOMENT_AFTER_SECONDS)

                # 诊断日志
                print(f"   🔧 [DEBUG] 帧缓冲区总大�?: {len(self.frame_buffer)} �?")
                if len(self.frame_buffer) > 0:
                    buffer_start_ts = self.frame_buffer[0][2]
                    buffer_end_ts = self.frame_buffer[-1][2]
                    buffer_span = buffer_end_ts - buffer_start_ts
                    print(f"   🔧 [DEBUG] 缓冲区时间跨�?: {buffer_span:.1f}�?")
                    print(f"   �9�9 [DEBUG] �1�7?�괰�1�7?: [{original_timestamp - before_s:.1f}, {original_timestamp + after_s:.1f}] = {before_s + after_s:.0f}�1�7?")
                
                # 获取标�?�时刻前后窗口的�?
                clip_frames = []
                for frame_buf, frame_num, ts in self.frame_buffer:
                    if original_timestamp - before_s <= ts <= original_timestamp + after_s:
                        # 解码 JPEG
                        frame = cv2.imdecode(frame_buf, cv2.IMREAD_COLOR)
                        if frame is not None:
                            clip_frames.append((frame, frame_num, ts))
                
                print(f"   🔧 [DEBUG] 窗口内收集到帧数: {len(clip_frames)} �?")
                
                if len(clip_frames) < 30:  # 至少霄1�7�?1�?
                    print(f"   �7�2�1�5 ֡���㣬�޷���չ�ӄ1�7?? ({len(clip_frames)} �1�7?). Buffer Range: {buffer_start_ts:.1f}-{buffer_end_ts:.1f}, Target: {original_timestamp - before_s:.1f}-{original_timestamp + after_s:.1f}")
                    return
            
            # 鐢熸垚鏂拌?嗛?戣矾寰?
            video_filename = f"{moment_id}.mp4"
            video_path = self.moments_dir / video_filename
            
            # 璁＄畻甯х巼鍜岃?嗛?戞椂闀?
            if len(clip_frames) >= 2:
                time_span = clip_frames[-1][2] - clip_frames[0][2]
                actual_fps = len(clip_frames) / time_span if time_span > 0 else 30
                # 不限制最小FPS，保持真实时间跨�?
                actual_fps = min(max(actual_fps, 5), 60)  # 朄1�7�?5fps，保�?30秒�?��?�完�?
                print(f"   🔧 [DEBUG] 实际时间跨度: {time_span:.2f}�?")
                print(f"   �9�9 [DEBUG] ����FPS: {actual_fps:.1f}")
                # 使用实际时间跨度作为视�?�时长，而不�?计算�?
                video_duration = time_span
            else:
                actual_fps = 30
                video_duration = len(clip_frames) / actual_fps
            
            print(f"   �9�9 [DEBUG] �ӄ1�7?�1�7ʱ�1�7?: {video_duration:.2f}�1�7? ({len(clip_frames)}�1�7? @ {actual_fps:.1f}fps)")
            
            # 获取帧尺�?
            first_frame = clip_frames[0][0]
            h, w = first_frame.shape[:2]
            
            # 使用 ffmpeg 编码
            import subprocess
            try:
                ffmpeg_cmd = [
                    'ffmpeg', '-y',
                    '-f', 'rawvideo', '-pix_fmt', 'bgr24',
                    '-s', f'{w}x{h}', '-r', str(int(actual_fps)),
                    '-i', 'pipe:0',
                    '-c:v', 'libx264', '-preset', 'ultrafast', '-crf', '28',
                    '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
                    str(video_path)
                ]
                
                process = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, 
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                for frame, _, _ in clip_frames:
                    process.stdin.write(frame.tobytes())
                
                process.stdin.close()
                process.wait(timeout=30)
                
            except Exception as e:
                # 鍥為��鍒? OpenCV
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                writer = cv2.VideoWriter(str(video_path), fourcc, actual_fps, (w, h))
                for frame, _, _ in clip_frames:
                    writer.write(frame)
                writer.release()
            
            # 鏇存柊 moment 鐨勮?嗛?戜俊鎭?骞惰幏鍙杅rame_number
            moment_frame_number = None
            for m in self.moments:
                if m.id == moment_id:
                    m.video_path = str(video_path)
                    m.video_duration = video_duration
                    moment_frame_number = m.frame_number
                    break
            
            self._save_moments()
            print(f"   ✅ 完整视频已生成: {video_duration:.1f}秒 (前{before_s:.0f}秒 + 后{after_s:.0f}秒)")
            
            # 馃攰 涓哄畬鏁磋?嗛?戞坊鍔犻煶棰戯紝骞跺湪瀹屾垚鍚庤Е鍙戣??闊宠浆鏂囧瓧+AI鍒嗘瀽
            if moment_frame_number is not None:
                print(f"   馃帳 涓哄畬鏁磋?嗛?戞坊鍔犻煶棰?...")
                self._add_audio_to_video(
                    moment_id,
                    str(video_path),
                    moment_frame_number,
                    video_duration,
                    frame,
                    center_timestamp=float(original_timestamp),
                    window_before=float(before_s),
                    window_after=float(after_s),
                )
            
        except Exception as e:
            print(f"   �? 扩展视�?�失�?: {e}")
            import traceback
            traceback.print_exc()
    
    # ============================================================
    # �?? AI �?动识�? (Smart Mirror)
    # ============================================================
    
    def update_frame(self, frame, frame_number: int, 
                    person_count: int = 0, track_ids: List[int] = None):
        """
        每帧调用, 用于 AI 分析缓冲
        
        Args:
            frame: 当前�?
            frame_number: ֡��
            person_count: 人数
            track_ids: ׷��ID
        """
        self.frame_count = frame_number
        current_time = time.time()
        
        # 棄1�7查是否需要进�? AI 分析 (�?3.5分钟)
        if current_time - self.last_ai_analysis_time >= self.ai_interval_seconds:
            if person_count > 0:  # �?在有人时分析
                # ⚠️ 关键：先更新时间戳再触发分析，确保切片之间无遗漏
                # 即使处理耗时30秒，下一次也�?从本次的210秒后触发，�1�7�非处理完成后的210�?
                self.last_ai_analysis_time = current_time
                # 异�?�进�? AI 分析
                self._trigger_ai_analysis(frame.copy(), frame_number, person_count, track_ids or [])
    
    def _trigger_ai_analysis(self, frame, frame_number: int, 
                             person_count: int, track_ids: List[int]):
        """触发 AI 分析 (异�??)"""
        if not self.qwen_available:
            return
        
        # 在后台线程执行分�?
        thread = threading.Thread(
            target=self._analyze_frame_with_ai,
            args=(frame, frame_number, person_count, track_ids),
            daemon=True
        )
        thread.start()
    
    def _trigger_ai_analysis_for_moment(self, frame, moment_id: str, transcript: str = ""):
        """瑙﹀彂瀵圭敤鎴锋爣璁板叧閿?鏃跺埢鐨? AI 鍒嗘瀽 (寮傛?ワ紝鍖呭惈璇?闊?)"""
        if not self.qwen_available:
            return
        
        # 在后台线程执行分�?
        thread = threading.Thread(
            target=self._analyze_moment_with_ai,
            args=(frame, moment_id, transcript),
            daemon=True
        )
        thread.start()
    
    def _analyze_frame_with_ai(self, frame, frame_number: int,
                               person_count: int, track_ids: List[int]):
        """
        使用 Qwen-VL 分析�? (�?视�??)
        
        基于编码框架识别协作学习行为
        """
        import cv2
        
        try:
            # 优化：缩小图像以加快传输和分�? (Max width 1280)
            frame_for_ai = frame
            h, w = frame.shape[:2]
            if w > 1280:
                scale = 1280 / w
                new_h = int(h * scale)
                frame_for_ai = cv2.resize(frame, (1280, new_h))

            # 将帧编码�? base64
            _, buffer = cv2.imencode('.jpg', frame_for_ai, [cv2.IMWRITE_JPEG_QUALITY, 85])
            image_base64 = base64.b64encode(buffer).decode('utf-8')
            prompt = """你是协作学习研究专家。分析这张协作学习场景的图片。

请根据以下完整编码框架识别行为：

⚠️ 关键原则：
1. 只有当确实观察到【明显的协作互动】（如讨论、手指屏幕、共同操作、眼神交流）时，才标记为 is_key_moment: true。
2. 如果画面只是大家各自看电脑、玩手机、发呆，或者没有人，请直接返回 "is_key_moment": false。不要强行套用以下分类。

=================================================================
维度一：参与与沉浸 (Engagement) - 投入时间、情感状态与心流体验
=================================================================

【Eng-Flow 沉浸/心流】
- Engage: [R1]探索性困惑(好奇/困惑), [R1]真实性确认
- Investigate: [R1]问题命名(重构问题), [R1]信息供给
- Act: [R0]具象化行动(制作草图/模型), [R1]改进意图

【Eng-Emo 情感/氛围】
- Engage: [R0]情感连接(破冰), [R0]尊重确认(肯定观点), [R1]相互印证
- Investigate: [R0]资源接入, [R0]物理陪伴, [R1]邀请思考
- Act: [R0]实质协作, [R1]赞美评价, [R1]集体自豪

【Eng-Strug 挣扎/坚持】
- Engage: [R1]识别困难, [R1]处理难题
- Investigate: [R1]识别分歧, [R1]设定限制
- Act: [R1]潜力评估, [R2]验证假设

=================================================================
维度二：主动性与意图 (Initiative) - 设定目标、寻求反馈、承担风险
=================================================================

【Init-Goal 目标/计划】
- Engage: [R1]目标锚定, [R1]计划制定, [R1]澄清细节
- Investigate: [R1]角色分配, [R1]流程建议, [R2]认知代理
- Act: [R2]构思发散(数量优先), [R2]决策叠加, [R2]妥协陈述

【Init-Feed 反馈/验证】
- Engage: [R1]观点陈述, [R1]理解想法
- Investigate: [R2]理由质疑, [R2]澄清分歧, [R2]综合分析
- Act: [R2]迭代修改, [R2]事实测试, [R2]经验测试

【Init-Risk 风险/争论】
- Engage: [R2]对比想法, [R2]疯狂想法
- Investigate: [R2]探索不一致, [R2]论证推理, [R2]批判挑战
- Act: [R3]超越自我(新综合), [R2]论据权重, [R3]框架重构

=================================================================
维度三：社会支架 (Social Scaffolding) - 互助、激发灵感、物理连接
=================================================================

【Soc-Ind 独立/自说自话】
- [R0]独立陈述(Monologue), [R0]平行研习, [R0]平行制作(Co-acting)

【Soc-Help 互助/教学】
- Engage: [R0]关系确认, [R1]建议劝告
- Investigate: [R1]消除盲区, [R1]信息提供, [R1]文献支持
- Act: [R0]直接任务协作, [R1]积极参与, [R3]对称贡献

【Soc-Insp 激发/共享】
- Engage: [R1]印证例子, [R2]丰富语境
- Investigate: [R2]数据支持, [R2]权威扩展, [R2]解释细化
- Act: [R3]启发发现("A ha!"), [R3]综合观点, [R3]整合隐喻

【Soc-Conn 连接/协同】
- Engage: [R0]物理在场, [R1]共享责任
- Investigate: [R1]促进理解, [R0]同伴关系
- Act: [R3]贡献专长, [R3]共同建构, [R2]兴趣叠加

=================================================================
维度四：理解的发展 (Understanding) - 顿悟、解释策略、应用知识
=================================================================

【Und-Exp 解释/推演】
- Engage: [R1]定义问题, [R1]问题命名
- Investigate: [R1]参考经验, [R2]解释连接, [R2]引用支持
- Act: [R2]解释方案, [R2]协商术语, [R2]细化观点

【Und-Aha 顿悟/突破】★关键
- Engage: [R3]真实基石, [R3]洞察力生成
- Investigate: [R3]发现时刻"I find it!"💡, [R3]可改进思想
- Act: [R3]新的综合💡, [R3]应用新知, [R3]元认知改变💡

【Und-Strive 深思/内化】
- Engage: [R1]认知困惑, [R2]精神生活
- Investigate: [R2]个人思考, [R2]检查实践, [R2]识别问题
- Act: [R2]反向反思, [R2]认知图式测试, [R2]隐含性决策

=================================================================
反思层级: R0(基础) / R1(初级) / R2(深度) / R3(高阶突破)
阶段: Engage(定义) / Investigate(学习) / Act(制作)
=================================================================

请以JSON格式返回:
{
    "is_key_moment": true/false,
    "importance": 0.0-1.0,
    "reflection_level": "R0|R1|R2|R3",
    "phase": "Engage|Investigate|Act",
    "dimension": "Engagement|Initiative|Social|Understanding",
    "behavior_code": "�1�7�1�7 Eng-Flow",
    "specific_behavior": "如 [R2]论证推理",
    "description": "简短描述正在发生什么",
    "observable_behaviors": ["�ɹ۲���Ϊ1"],
    "emotions": ["情绪状态"],
    "tags": ["��ǩ1"]
}

只返回JSON，不要其他内容。"""

            result_text = self._run_vision_llm(
                image_base64=image_base64,
                prompt=prompt,
                model_override=self.vision_model_fast,
                temperature=0.3,
                max_tokens=500
            )

            # 解析 JSON
            # 移除�?能的 markdown 代码块标�?
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
            
            result = json.loads(result_text)
            
            # 强制�?照模�?
            force_snapshot = (os.environ.get("MULTIMODAL_FORCE_SNAPSHOT", "0") or "0").strip() == "1"
            
            # 濡傛灉鏄?鍏抽敭鏃跺埢锛岃?板綍锛堥槇鍊?0.3锛屾彁楂樼伒鏁忓害锛?
            # 或�1�7? forced
            is_key = result.get("is_key_moment", False)
            importance = result.get("importance", 0)
            
            if (is_key and importance > 0.3) or force_snapshot:
                if force_snapshot:
                    print("�1�77�1�72�1�71�1�75 Visual analysis negative, but forced snapshot enabled.")
                    if not result.get("description"):
                       result["description"] = "Periodic snapshot (Image only)"
                
                self._record_ai_moment(
                    frame=frame,
                    frame_number=frame_number,
                    person_count=person_count,
                    track_ids=track_ids,
                    ai_result=result
                )
            else:
                print(f"�1�7?? AI Analysis (Frame {frame_number}): Non-key moment (Importance: {result.get('importance', 0):.2f})")
                
        except Exception as e:
            print(f"�7�2�1�5 AI Analysis failed: {e}")
    
    def _record_ai_moment(self, frame, frame_number: int,
                          person_count: int, track_ids: List[int],
                          ai_result: Dict[str, Any]):
        """记录 AI 识别的关�?时刻"""
        import cv2
        
        timestamp = time.time()
        duration = timestamp - self.start_time
        time_str = self._format_time(duration)
        
        # 生成�?丄1�7ID
        moment_id = f"ai_{int(timestamp)}_{frame_number}"
        
        # 淇濆瓨鎴?鍥?
        image_filename = f"{moment_id}.jpg"
        image_path = self.moments_dir / image_filename
        cv2.imwrite(str(image_path), frame)
        
        # 提取 AI 分析结果
        description = ai_result.get("description", "AIʶ��Ĺ؄1�7?ʱ��")
        tags = ai_result.get("tags", [])
        importance = ai_result.get("importance", 0.5)
        # 鍏煎?逛笉鍚? prompt 鐨勫瓧娈?
        if not tags:
            tags = ai_result.get("tags", [])
        
        # 创建关键时刻
        moment = KeyMoment(
            id=moment_id,
            timestamp=timestamp,
            frame_number=frame_number,
            source=MomentSource.AI_DETECTED.value,
            frame_path=str(image_path),
            time_str=time_str,
            duration_seconds=duration,
            person_count=person_count,
            track_ids=track_ids.copy() if track_ids else [],
            ai_description=description,
            ai_tags=tags,
            ai_importance=importance,
            analysis=ai_result.get("meeting_note", "") or ai_result.get("analysis", "")
        )

        # 先落�? moment，确保后台线程更新时�?找到
        self.moments.append(moment)
        self.stats["ai_detected"] += 1
        self.stats["total_moments"] += 1
        self._save_moments()

        # 馃幀 涓庢墜鍔ㄦ爣璁颁繚鎸佷竴鑷?: 鍏堜繚瀛樺墠15绉掕?嗛?戯紝鐒跺悗寤惰繜鐢熸垚瀹屾暣30绉掕?嗛??
        # 绗?涓�闃舵??: 淇濆瓨鍓?15绉掕?嗛??
        print(f"   🎬 [AI视�?�] �?丄1�7阶�??: 弄1�7始保存前{KEY_MOMENT_BEFORE_SECONDS:.0f}秒�?��??...")
        video_path, video_duration = self._save_video_clip(
            moment_id=moment_id,
            clip_duration_before=float(KEY_MOMENT_BEFORE_SECONDS),  # 15�1�7?
            frame_number=frame_number,
            frame=frame,
            center_timestamp=timestamp  # 使用AI棄1�7测时刻作为中�?
        )
        if video_path:
            moment.video_path = video_path
            moment.video_duration = video_duration
            self._save_moments()
            print(f"   鉁? [AI瑙嗛?慮 绗?涓�闃舵?靛畬鎴?: {video_duration:.1f}绉掕?嗛?戝凡淇濆瓨")
        else:
            print(f"   ⚠️ AI关键时刻视�?�生成失�?: {moment_id}")
            return  # 濡傛灉绗?涓�闃舵?靛け璐ワ紝涓嶇户缁?
        
        # 绗?浜岄樁娈?: 鍚?鍔ㄥ悗鍙扮嚎绋嬶紝绛夊緟15绉掑悗鐢熸垚鍖呭惈鍚庢?电殑瀹屾暣瑙嗛??
        print(f"   🎬 [AI视�?�] �?二阶�?: �?动延迟线程，{KEY_MOMENT_AFTER_SECONDS:.0f}秒后生成完整视�??")
        # 绗?浜岄樁娈?: 鍚?鍔ㄥ悗鍙扮嚎绋嬶紝绛夊緟15绉掑悗鐢熸垚鍖呭惈鍚庢?电殑瀹屾暣瑙嗛??
        print(f"   🎬 [AI视�?�] �?二阶�?: �?动延迟线程，{KEY_MOMENT_AFTER_SECONDS:.0f}秒后生成完整视�??")
        
        # 使用�?包捕获当前所霄1�7变量
        def delayed_video_extension(mid, ts, frm):
            try:
                print(f"   �? [AI视�?�延迟] 线程弄1�7�? (moment_id={mid}), 等待 {KEY_MOMENT_AFTER_SECONDS:.0f} �?...")
                time.sleep(float(KEY_MOMENT_AFTER_SECONDS))
                print(f"   🎬 [AI视�?�延迟] 唤醒! 弄1�7始生成完整�?��??: {mid}")
                self._extend_video_with_after_frames(mid, ts, frm)
            except Exception as e:
                print(f"   �? [AI视�?�延迟] 线程异常: {e}")
        
        # 浼犻�掑弬鏁伴伩鍏嶉棴鍖呭彉閲忔崟鑾烽棶棰?
        extend_thread = threading.Thread(
            target=delayed_video_extension, 
            args=(moment_id, timestamp, frame.copy()),
            daemon=True
        )
        extend_thread.start()
        print(f"   �? [AI视�?�] 延迟线程已启�? (thread_id={extend_thread.ident}, moment_id={moment_id})")
        
        print(f"�?? AI 识别关键时刻: {time_str}")
        print(f"   �1�79�1�75 {description[:60]}...")
        print(f"   🏷️ 标签: {', '.join(tags[:3])}")
        print(f"   ⭐ 重要性: {importance:.2f}")
        print(f"   🎞️ 视频 (前{KEY_MOMENT_BEFORE_SECONDS:.0f}秒): {video_duration:.1f}秒")
        print(f"   ⏳ {KEY_MOMENT_AFTER_SECONDS:.0f}秒后将生成完整视频并进行AI分析...")
    
    def _process_video_with_multimodal_analysis(self, moment_id: str, video_path: str, frame=None):
        """浠庡畬鏁磋?嗛?戜腑鎻愬彇闊抽?戝苟杩涜?岃??闊宠浆鏂囧瓧锛岀劧鍚庤繘琛屽?氭ā鎬丄I鍒嗘瀽
        
        Args:
            moment_id: 关键时刻ID
            video_path: 鍚?闊抽?戠殑瀹屾暣瑙嗛?戣矾寰?
            frame: 关键帧图�?
        """
        from pathlib import Path
        import subprocess

        def _ai_step(step: int, total: int, msg: str):
            # 缁堢??绮剧畝浣嗏�滄瘡涓�姝ラ兘瑕佹湁鈥濃�斺�旂粺涓�鎴愬崟琛屾?ラ?よ緭鍑?
            print(f"   🧩 [AI处理] {step}/{total} {msg}")
        
        try:
            total_steps = 9
            # 鍏堝啓鍏モ�滃?勭悊涓?鈥濆崰浣嶏紝閬垮厤鍓嶇??闀挎椂闂存樉绀? No AI analysis content
            with self._moments_lock:
                for m in self.moments:
                    if m.id == moment_id:
                        if not (m.ai_description or "").strip() and not (m.analysis or "").strip():
                            m.ai_description = "AI Processing..."
                            self._save_moments()
                        break

            _ai_step(1, total_steps, "׼�1�7??/ռλ")

            # 读取上下文（�?能包�? after 秒补齐的窗口�?写）
            _ai_step(2, total_steps, "�1�7�1�7�0�0 context.txt")
            context_text = ""
            context_transcript = ""
            try:
                ctx_path = Path(video_path).parent / f"{moment_id}_context.txt"
                if ctx_path.exists():
                    context_text = ctx_path.read_text(encoding="utf-8")
                    marker = "=== transcript_context ==="
                    if marker in context_text:
                        # 取最后一次写入的 transcript_context，避免重复追加�?�致解析到旧内�??
                        context_transcript = context_text.rsplit(marker, 1)[1].strip()
                    print(f"   �?? [AI处理] context.txt 找到，上下文�?�?: {len(context_transcript)} �?")
                else:
                    print(f"   �?? [AI处理] {moment_id}_context.txt 不存�? (仅使用全屄1�7KB)")

                # GLOBAL KB: 读取全局 context.txt (知识�?)
                # �1�7?�1�7?: integrated_data/../context.txt -> 1215zzh/context.txt
                try:
                    global_kb_path = self.data_dir.parent / "context.txt"
                    if global_kb_path.exists():
                        kb_content = global_kb_path.read_text(encoding="utf-8").strip()
                        if kb_content:
                            print(f"   📚 [AI处理] 加载全局知识�? (context.txt): {len(kb_content)} �?")
                            # �? KB 拼接�? context_text 前面或后�?
                            context_text = f"【全屄1�7知识�?/背景信息】\n{kb_content}\n\n" + context_text
                    else:
                        print(f"   ⚠️ [AI处理] 全局知识�? context.txt 不存�?: {global_kb_path}")
                except Exception as e:
                    print(f"   ⚠️ [AI处理] 读取全局KB失败: {e}")
            except Exception as e:
                print(f"   �?? [AI处理] 读取 context.txt 失败: {e}")
                context_text = ""
                context_transcript = ""

            # 榛樿?ょ?佺敤鈥滀紭鍏堜娇鐢ㄤ笂涓嬫枃杞?鍐欌�濓紝鏀逛负寮哄埗瀵光�滃畬鏁村垏鐗囪?嗛?戔�濆仛 ASR銆?
            # 鍘熷洜锛氫笂涓嬫枃杞?鍐欏彧鍖呭惈鎸夐敭鍓嶇殑鍘嗗彶锛岃�岃?嗛?戝垏鐗囧寘鍚?鎸夐敭鍚庣殑鈥滄湭鏉モ�?15绉掋�傚彧鏈夐噸鍋? ASR 鎵嶈兘鎷垮埌杩欓儴鍒嗗唴瀹圭殑鏂囧瓧銆?
            prefer_ctx_asr = os.environ.get("KEY_MOMENT_PREFER_CONTEXT_TRANSCRIPT", "0").strip().lower() in {"1", "true", "yes"}
            _ai_step(3, total_steps, f"�ж��1�7?д���1�7?: prefer_ctx_asr={int(prefer_ctx_asr)} ctx_len={len((context_transcript or '').strip())}")
            if prefer_ctx_asr and context_transcript:
                _ai_step(4, total_steps, "跳过提取音�??/二�??ASR(直接用上下文�?�?)")
                # 更新 moment.transcript（�1�7�常更完整）
                with self._moments_lock:
                    for m in self.moments:
                        if m.id == moment_id:
                            incoming = (context_transcript or "").strip()
                            existing = (m.transcript or "").strip()
                            looks_like_window = ("\n" in incoming) or ("[00:" in incoming) or ("[0" in incoming)
                            if looks_like_window:
                                if incoming and incoming != existing:
                                    m.transcript = context_transcript
                                    if not (m.asr_provider or "").strip():
                                        m.asr_provider = "realtime"
                                    self._save_moments()
                            else:
                                if len(incoming) > len(existing):
                                    m.transcript = context_transcript
                                    if not (m.asr_provider or "").strip():
                                        m.asr_provider = "realtime"
                                    self._save_moments()
                            break

                if frame is not None:
                    if self._transcript_is_missing(context_transcript):
                        _ai_step(9, total_steps, "跳过AI分析(无有效�??�?)")
                        self._mark_moment_no_audio(moment_id, "上下文转写为�?/无有效�??�?")
                    else:
                        _ai_step(9, total_steps, "调用视�??/多模态AI分析")
                        self._analyze_moment_with_ai(frame, moment_id, context_transcript, context_text=context_text)
                else:
                    _ai_step(9, total_steps, "跳过AI分析(无frame)")

                # 琛ラ綈鈥滄瘡涓�姝ラ兘瑕佹湁鈥濈殑杈撳嚭锛氫腑闂存?ラ?ゆ爣璁颁负璺宠繃
                _ai_step(5, total_steps, "跳过(已用上下文转�?)")
                _ai_step(6, total_steps, "跳过(已用上下文转�?)")
                _ai_step(7, total_steps, "跳过(已用上下文转�?)")
                _ai_step(8, total_steps, "跳过(已用上下文转�?)")
                return

            # 限流：避免�?�个关键时刻并�?�把系统拖慢（尤�? FireRedASR/LLM 都会吃资源）
            _ai_step(4, total_steps, "等待重任务信号量")
            with self._heavy_job_sema:
                _ai_step(5, total_steps, "��ȡ��1�7??(ffmpeg)")
                import subprocess
                from pathlib import Path
            
                # 1. 提取音�?�用于�??音转文字
                audio_for_asr_path = Path(video_path).parent / f"{moment_id}_asr.wav"
            
                cmd_extract_audio = [
                    'ffmpeg', '-y', '-i', str(video_path),
                    '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1',
                    str(audio_for_asr_path)
                ]
            
                print(f"   🎵 提取音�?�用于�??音识�?...")
                result = subprocess.run(cmd_extract_audio, capture_output=True, timeout=30)
                _ai_step(6, total_steps, f"ffmpeg rc={result.returncode} wav_exists={int(audio_for_asr_path.exists())}")
            
                if result.returncode != 0 or not audio_for_asr_path.exists():
                    print(f"   ⚠️ 音�?�提取失败，跳过�?音转文字")
                    self._mark_moment_no_audio(moment_id, "Video segment has no audio track/audio extraction failed")
                    return
            
                # 2. 调用ASR进�?��??音转文字
                _ai_step(7, total_steps, "ASR�1�7?�1�7?")
                transcript = self._transcribe_audio(audio_for_asr_path)
            
                # 娓呯悊涓存椂闊抽?戞枃浠?
                try:
                    audio_for_asr_path.unlink()
                except:
                    pass
            
            # 3. 更新moment的transcript字�??
            _ai_step(8, total_steps, f"�1�7�1�7��moment transcript(asr_len={len((transcript or '').strip())})")
            for moment in self.moments:
                if moment.id == moment_id:
                    moment.transcript = transcript
                    moment.asr_provider = (self._last_asr_meta.get("provider") or "")
                    moment.asr_model = (self._last_asr_meta.get("model") or "")
                    moment.asr_model_dir = (self._last_asr_meta.get("model_dir") or "")
                    print(f"   �? �?音转文字完成: {len(transcript)} �?")
                    # if transcript:
                    #     print(f"   �9�5 �ڄ1�7??: {transcript[:80]}...")
                    break
            
            self._save_moments()

            if self._transcript_is_missing(transcript):
                _ai_step(9, total_steps, "跳过AI分析(ASR为空/无有效�??�?)")
                self._mark_moment_no_audio(moment_id, "ASR is empty/no valid speech")
                return
            
            # 4. 杩涜?屽?氭ā鎬丄I鍒嗘瀽 (瑙嗛??+璇?闊?)
            _ai_step(9, total_steps, "调用视�??/多模态AI分析")
            if frame is not None:
                self._analyze_moment_with_ai(frame, moment_id, transcript, context_text=context_text)
            else:
                _ai_step(9, total_steps, "跳过AI分析(无frame)")
            
        except Exception as e:
            print(f"   ⚠️ 多模态�?�理失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _transcribe_audio(self, audio_path: Path) -> str:
        """
        浣跨敤DashScope杩涜?岄煶棰戣浆鏂囧瓧 (鍙傝�冨疄鏃禔SR鐨勬垚鍔熷疄鐜?)
        
        Args:
            audio_path: 音�?�文件路�? (WAV格式, 16kHz, 单声�?)
            
        Returns:
            杞?鍐欐枃鏈?
        """
        try:
            # ============================================================
            # ASR 后�??选择：支持本�? FireRedASR（�?�线）或 DashScope (云�??)
            # 用户偏好：Qwen (DashScope)
            # ============================================================
            # 榛樿?ゆ敼涓? dashscope 浠ュ搷搴旂敤鎴疯?锋眰
            asr_provider = os.environ.get("ASR_PROVIDER", "dashscope").strip().lower()

            if asr_provider == "fireredasr":
                # (Keep FireRedASR logic but it won't be default)
                model_dir = os.environ.get("FIREREDASR_MODEL_DIR", "pretrained_models/FireRedASR-AED-L")
                asr_type = os.environ.get("FIREREDASR_ASR_TYPE", "aed").strip().lower()
                use_gpu = os.environ.get("FIREREDASR_USE_GPU", "0").strip() in {"1", "true", "yes"}
                beam_size = int(os.environ.get("FIREREDASR_BEAM_SIZE", "3"))
                nbest = int(os.environ.get("FIREREDASR_NBEST", "1"))

                # 鍏堣?板綍鍏冧俊鎭?锛堝嵆渚垮悗缁?澶辫触/鍥為��锛屼篃鑳界湅鍑烘湰鏉ユ兂鐢ㄤ粈涔堬級
                self._last_asr_meta = {
                    "provider": "fireredasr",
                    "model": f"{asr_type}:{Path(model_dir).name}",
                    "model_dir": str(model_dir),
                }

                if not Path(model_dir).exists():
                    print(f"   ⚠️ FireRedASR 模型�?录不存在: {model_dir}")
                    # 允�?�回逄1�7�? DashScope
                else:
                    try:
                        # 关键：�?�用模型，避免每�? from_pretrained 导致长时间卡�?/高延�?
                        with self._fireredasr_lock:
                            if self._fireredasr_model is None:
                                try:
                                    from fireredasr.models.fireredasr import FireRedAsr
                                except Exception:
                                    project_dir = Path(__file__).parent
                                    candidates = [project_dir / "FireRedASR", project_dir / "vendor" / "FireRedASR"]
                                    for c in candidates:
                                        if c.exists() and str(c) not in sys.path:
                                            sys.path.insert(0, str(c))
                                    from fireredasr.models.fireredasr import FireRedAsr
                                self._fireredasr_model = FireRedAsr.from_pretrained(asr_type, model_dir)

                            model = self._fireredasr_model
                        decode_conf = {"use_gpu": int(use_gpu), "beam_size": beam_size, "nbest": nbest}
                        results = model.transcribe(["utt1"], [str(audio_path)], decode_conf)
                        if results:
                            text = (results[0].get("text") or "").strip()
                            if text:
                                return text
                    except Exception as e:
                        print(f"   ⚠️ FireRedASR �?写失�?(将回逄1�7DashScope): {e}")
                # FireRedASR �?产出结果时，继续�? DashScope 分支

            # DashScope / Qwen ��֧
            self._last_asr_meta = {
                "provider": "dashscope",
                "model": "qwen-audio-turbo",
                "model_dir": "",
            }

            # 妫�鏌?DashScope鍙?鐢ㄦ�?
            if not self.api_key:
                print("   ⚠️ DashScope API Key�?配置")
                return ""
            
            # 方法1: 使用 Recognition API (同�?�调�?) - 参�1�7? realtime_asr.py
            try:
                import dashscope
                from dashscope.audio.asr import Recognition
                
                dashscope.api_key = self.api_key
                
                print(f"   🎤 正在进�?��??音转文字 (文件大小: {audio_path.stat().st_size} bytes, DashScope)...")
                
                # ASR模型优先级列�?（只使用已确认可用的模型�?
                models_to_try = [
                    'paraformer-realtime-v2',      # 实时ASR模型（主力）
                    'paraformer-realtime-8k-v2',   # 8k采样率版�?（�?�用�?
                ]
                
                result = None
                last_error = None
                successful_model = None
                
                for model_name in models_to_try:
                    try:
                        print(f"   🔄 尝试模型: {model_name}")
                        
                        # 创建识别对象 (�? realtime_asr.py 保持丄1�7�?)
                        recognition = Recognition(
                            model=model_name,
                            format='wav',       # �ļ���ʽ
                            sample_rate=16000,  # 采样�?
                            callback=None       # 同�?�调用不霄1�7要回�?
                        )
                        
                        # 鍚屾?ヨ皟鐢?,鐩存帴浼犲叆鏂囦欢璺?寰?
                        result = recognition.call(str(audio_path))
                        
                        # 棄1�7查结�?
                        if result and hasattr(result, 'output') and result.output:
                            successful_model = model_name
                            print(f"   �? 模型 {model_name} 识别成功")
                            break
                        elif result and hasattr(result, 'status_code'):
                            if result.status_code == 200:
                                # 状�1�7�成功但结果为空，尝试下丄1�7�?模型
                                print(f"   ⚠️ 模型 {model_name} 返回成功但结果为空，尝试下一�?模型")
                                last_error = f"模型 {model_name} 无识�?结果"
                                continue  # 继续尝试下一�?模型
                            else:
                                error_msg = getattr(result, 'message', f'Status {result.status_code}')
                                last_error = error_msg
                                print(f"   �7�2�1�5 ģ�� {model_name} ʧ��: {error_msg}")
                                continue
                        else:
                            last_error = f"ģ�� {model_name} ���ؿս�1�7?"
                            print(f"   �7�2�1�5 {last_error}")
                            continue
                            
                    except Exception as e:
                        last_error = str(e)
                        print(f"   �7�2�1�5 ģ�� {model_name} �쳣: {e}")
                        continue

                if successful_model:
                    self._last_asr_meta = {
                        "provider": "dashscope",
                        "model": str(successful_model),
                        "model_dir": "",
                    }
                
                # 提取�?写文�?
                transcript_parts = []
                if result and hasattr(result, 'output') and result.output:
                    output = result.output
                    
                    # 🔍 调试输出结构
                    print(f"   �1�79�1�73 [DEBUG] Output type: {type(output)}")
                    if isinstance(output, dict):
                        print(f"   �1�79�1�73 [DEBUG] Output keys: {list(output.keys())}")
                        print(f"   �1�79�1�73 [DEBUG] Output content: {output}")
                    elif hasattr(output, '__dict__'):
                        print(f"   �1�79�1�73 [DEBUG] Output attrs: {vars(output)}")
                    else:
                        print(f"   �1�79�1�73 [DEBUG] Output: {output}")
                    
                    # 处理不同的输出格�?
                    if isinstance(output, dict):
                        # ��ʽ1: sentence (�б���ʽ - paraformer-realtime-v2)
                        if 'sentence' in output:
                            sentence = output['sentence']
                            # sentence �?列表,包含多个句子对象
                            if isinstance(sentence, list):
                                for sent_obj in sentence:
                                    if isinstance(sent_obj, dict) and 'text' in sent_obj:
                                        text = sent_obj['text'].strip()
                                        if text:
                                            transcript_parts.append(text)
                            # 兜底:单个句子对象
                            elif isinstance(sentence, dict) and 'text' in sentence:
                                text = sentence['text'].strip()
                                if text:
                                    transcript_parts.append(text)
                            elif isinstance(sentence, str):
                                text = sentence.strip()
                                if text:
                                    transcript_parts.append(text)
                        
                        # 格式2: sentences (多句)
                        elif 'sentences' in output:
                            for sentence in output['sentences']:
                                if isinstance(sentence, dict) and 'text' in sentence:
                                    text = sentence['text'].strip()
                                    if text:
                                        transcript_parts.append(text)
                        
                        # 格式3: text (直接文本)
                        elif 'text' in output:
                            text = output['text'].strip()
                            if text:
                                transcript_parts.append(text)
                    
                    # 濡傛灉鏄?瀵硅薄,灏濊瘯瀵硅薄灞炴�ц?块棶
                    elif hasattr(output, 'sentence'):
                        sentence = getattr(output, 'sentence')
                        if hasattr(sentence, 'text'):
                            text = getattr(sentence, 'text', '').strip()
                            if text:
                                transcript_parts.append(text)
                
                transcript = ' '.join(transcript_parts).strip()
                
                if transcript:
                    print(f"   �? �?音转文字成功: {len(transcript)} �?")
                    # print(f"   �9�5 ʶ���ڄ1�7??: {transcript[:100]}{'...' if len(transcript) > 100 else ''}")
                    return transcript
                else:
                    print(f"   ⚠️ Recognition API 返回空结�?")
                    if last_error:
                        print(f"   �9�7 ���: {last_error}")
                    
            except ImportError as e:
                print(f"   ⚠️ dashscope.audio.asr �?安�??: {e}")
            except Exception as e:
                print(f"   ⚠️ �?音转文字异常: {e}")
                import traceback
                traceback.print_exc()
            
            
            # 扄1�7有方法都失败�?
            print(f"   ⚠️ �?音转文字扄1�7有方法都失败")
            print(f"   💡 建�??: 棄1�7�? DashScope API 密钥权限或模型可用�1�7?")
            
            # 馃幆 鍥為��鏂规?堬細浣跨敤瀹炴椂ASR鐨勫巻鍙茶浆鍐欙紙濡傛灉瀛樺湪锛?
            if context_transcript and len(context_transcript.strip()) > 0:
                print(f"   �? 使用上下文转写作为回逄1�7方�?? ({len(context_transcript)}�?)")
                return context_transcript
            
            print(f"   🔄 系统将使用纯视�?? AI 分析")
            return ""
        
        except Exception as e:
            print(f"   ⚠️ �?音转文字异常: {e}")
            import traceback
            traceback.print_exc()
            return ""
    
    def _analyze_moment_with_ai(self, frame, moment_id: str, transcript: str = "", context_text: str = ""):
        """
        为用户标记的关键时刻生成 AI 分析 (多模�?)
        
        Args:
            frame: ֡ͼ�1�7?
            moment_id: 关键时刻ID
            transcript: �?音转文字内�??
        """
        import cv2
        
        try:
            # 优化：缩小图像以加快 VLM 分析 (Max width 1280)
            frame_for_ai = frame
            h, w = frame.shape[:2]
            if w > 1280:
                scale = 1280 / w
                new_h = int(h * scale)
                frame_for_ai = cv2.resize(frame, (1280, new_h))

            # 将帧编码�? base64
            _, buffer = cv2.imencode('.jpg', frame_for_ai, [cv2.IMWRITE_JPEG_QUALITY, 85])
            image_base64 = base64.b64encode(buffer).decode('utf-8')

            # �? moment 里取按键原因
            user_note = ""
            for m in self.moments:
                if m.id == moment_id:
                    user_note = (m.user_note or "")
                    break

            # 鍏抽敭锛氳?佹眰鈥滃熀浜庤瘉鎹?锛屼笉纭?瀹氬氨璇翠笉纭?瀹氣�濓紝骞剁◢寰?鍙ｈ??骞介粯
            transcript_clean = (transcript or "").strip()

            # 关键：只�? context.txt 里最后一次写入的 transcript_context（也就是“窗口转写�1�7�）
            context_excerpt = (context_text or "").strip()
            marker = "=== transcript_context ==="
            if marker in context_excerpt:
                context_excerpt = context_excerpt.rsplit(marker, 1)[1].strip()
            # 鎴?鏂?鏃朵繚鐣欏熬閮?锛堟洿闈犺繎鎸夐敭鏃跺埢/绐楀彛锛夛紝閬垮厤鎴?鍒版棫鍐呭??
            if len(context_excerpt) > 3500:
                context_excerpt = "[...context truncated...]\n" + context_excerpt[-3500:]

            prompt = f"""你是一面"智能镜子"，忠实记录创客马拉松/Hackathon现场发生的事情。

场景说明：这是创客马拉松/Hackathon现场（做原型、写代码、调试、讨论方案）。

核心原则 - 镜子观察法：
1) **忠实反映**：像镜子一样客观描述画面中看到的内容和ASR听到的对话，不加主观评价。
2) **具体可见**：描述具体的动作、对话、表情、物品，而非抽象概念。
3) **卡片摘要**：
   - 生成25-30字的总结，用于卡片首页展示。
   - 必须包含1-2个表情符号 🎯
   - 稍微客观，不要描述太具体。

【按键原因/备注】{user_note or "(无)"}

【历史上下文(可能截断)】
{context_excerpt or "(��)"}

【本片段ASR（可能有噪声）】
{transcript_clean or "(无语音)"}

输出格式严格如下：
标签：<10~14字，描述这一刻发生的具体事件，如"3人围着电脑看代码"，可带0-1个相关表情符号>
卡片摘要：<25-30字，提炼总结。稍微客观，不要过于琐碎具体；必须包含1-2个Emoji>
详细描述：<2~3句，客观描述画面内容：
  - 人数和位置
  - 正在进行的动作
  - 对话内容（引用ASR）
  - 可见的设备/物品
  使用短句；总字数≤120；避免"似乎""可能""深度"等模糊词汇>
上下文定位：<1句，说明在历史上下文中找到的相关内容；若无则写"未在上下文中找到相关内容">
证据摘录：<1~3条，原样引用历史上下文或ASR中的文字，保留时间戳；若无则写"无">
"""


            ai_analysis = self._run_vision_llm(
                image_base64=image_base64,
                prompt=prompt,
                model_override=self.vision_model,
                temperature=0.7,
                max_tokens=900
            )

            # 鍙?閫夛細鐢ㄦ洿寮虹殑鏂囨湰妯″瀷锛堥粯璁? qwen3-max锛夊仛浜屾?℃暣鐞嗭紝鎻愬崌鈥滆创绾告爣绛?/璇︾粏瑙ｈ??/璇佹嵁鎽樺綍鈥濈殑涓�鑷存�?
            use_text_postprocess = os.environ.get("KEY_MOMENT_TEXT_POSTPROCESS", "1").strip().lower() in {"1", "true", "yes"}
            final_text = ai_analysis
            if use_text_postprocess:
                refine_prompt = f"""你是一面智能镜子，客观整理视觉模型输出。

你将收到三份输入：
1) 视觉模型对画面的解读（可能不完整）
2) 历史上下文（带时间戳）
3) 本片段 ASR 文本

核心要求：
1) **详细描述**：客观描述可见内容，不要主观评价。只使用【历史上下文】与【ASR】作为证据。
2) **卡片摘要**：生成25-30字（汉字）的简短总结，用于卡片展示。
   - 必须包含1-2个表情符号 🎯
   - 稍微客观，不要描述太具体（与详细描述区分），概括发生了什么。
   - 基于下面的详细描述和上下文提炼。

【按键原因/备注】{user_note or "(无)"}

【视觉解读(来自模型)】
{(ai_analysis or "").strip() or "(�1�7�1�7)"}

【历史上下文】
{context_excerpt or "(��)"}

【本片段ASR】
{transcript_clean or "(无语音)"}

输出格式严格如下：
标签：<10~14字，描述这一刻发生的具体事件，如"3人围着电脑看代码"，可带0-1个相关表情符号>
卡片摘要：<25-30字，提炼总结。稍微客观，不要过于琐碎具体；必须包含1-2个Emoji>
详细描述：<2~3句，客观描述画面内容：
  - 人数和位置
  - 正在进行的动作
  - 对话内容（引用ASR）
  - 可见的设备/物品
  使用短句；总字数≤120；避免"似乎""可能"以及抽象词汇>
上下文定位：<1句，说明在历史上下文中找到的相关内容；若无则写"未在上下文中找到相关内容">
证据摘录：<1~3条，原样引用历史上下文或ASR中的文字，保留时间戳；若无则写"无">
"""
                try:
                    final_text = self._run_text_llm(
                        prompt=refine_prompt,
                        system="",
                        model_override=self.text_model,
                        temperature=0.4,
                        max_tokens=900,
                    )
                except Exception as e:
                    print(f"鈿狅笍 浜屾?℃枃鏈?鏁寸悊澶辫触锛屽洖閫�鍒拌?嗚?夎緭鍑?: {e}")
                    final_text = ai_analysis
            
            # 更新关键时刻�? AI 分析结果
            for moment in self.moments:
                if moment.id == moment_id:
                    tagline, body = self._extract_tagline(final_text)
                    detail_desc = self._extract_detail_description(body)
                    card_summary = self._extract_card_summary(body)  # ��ȡ��Ƭժ�1�7??
                    framework_tags = self._extract_framework_tags(body)
                    
                    # 优先使用card_summary�?20-25字）显示在卡片上
                    #  回�1�7�1�7到detail_desc或tagline
                    new_description = (card_summary or "").strip() or (detail_desc or "").strip() or (tagline or "").strip()

                    moment.ai_tagline = (tagline or "").strip()
            
                    moment.ai_framework_tags = framework_tags
                    moment.analysis = body

                    # 闃叉?⑩�滈檷绾р�濓細涓嶈?佺敤寰堢煭鐨勬柊鏂囨湰瑕嗙洊宸叉湁鐨勯珮淇℃伅瀵嗗害鎻忚堪
                    existing_desc = (moment.ai_description or "").strip()
                    existing_is_placeholder = existing_desc in {"", "AI����1�7?�1�7?", "AI Processing...", "AI����ʧ��", "AI Analysis Failed"}
                    has_card_summary = bool((card_summary or "").strip())
                    if has_card_summary or existing_is_placeholder:
                        # 有card_summary或是占位符：直接更新
                        moment.ai_description = new_description
                    else:
                        # 过短的新文本通常�?“标签截�?/抽取失败”，不�?�盖
                        if len(new_description) < 12:
                            pass
                        # 新文�?显著更短且没有明显�?�量时，不�?�盖
                        elif len(new_description) + 10 < len(existing_desc):
                            pass
                        else:
                            moment.ai_description = new_description

                    moment.llm_provider = self.llm_provider
                    moment.llm_model = (
                        f"vision={self.vision_model};text={self.text_model}"
                        if use_text_postprocess else self.vision_model
                    )
                    print(f"�1�7? AI Analysis completed: {moment_id}")
                    if (moment.ai_tagline or "").strip():
                        print(f"   �9�5�1�7? Tag: {moment.ai_tagline}")
                    if framework_tags:
                        print(f"   �1�79�1�72 Framework tags: {framework_tags}")
                    break
            
            # 保存更新
            self._save_moments()
            
        except Exception as e:
            print(f"�7�2�1�5 AI Analysis failed: {e}")
            import traceback
            traceback.print_exc()

            # 回写丄1�7�?�?见的失败信息，避免前�?显示空白
            for moment in self.moments:
                if moment.id == moment_id:
                    if not (moment.ai_description or "").strip():
                        moment.ai_description = "AI Analysis Failed"
                    if not (moment.analysis or "").strip():
                        moment.analysis = "[AI Analysis Failed] Summary not generated (Model/Network/Timeout)."
                    moment.llm_provider = self.llm_provider
                    moment.llm_model = moment.llm_model or (self.vision_model or "")
                    break
            try:
                self._save_moments()
            except Exception:
                pass
    
    # ============================================================
    # 🎤📷 多模态分�? (音�?? + 图像联合)
    # ============================================================

    def _transcript_is_missing(self, transcript_text: str) -> bool:
        t = (transcript_text or "").strip()
        if not t:
            return True
        low = t.lower()
        if "no speech content" in low or "needs microphone" in low or "audio track" in low:
            return True
        meaningful = "".join(ch for ch in t if ch.isalnum())
        return len(meaningful) < 2

    def _mark_moment_no_audio(self, moment_id: str, reason: str) -> None:
        """When there is no valid audio/voice evidence, explicitly write "unreliable summary" to prevent LLM fabrication."""
        with self._moments_lock:
            for m in self.moments:
                if m.id != moment_id:
                    continue
                m.ai_tagline = "�1�79�1�77 No Audio"
                m.ai_description = f"No audio/voice content, unable to generate reliable summary ({reason})"
                m.analysis = f"[No Audio] {reason}"
                try:
                    m.ai_importance = min(float(getattr(m, "ai_importance", 0.0) or 0.0), 0.15)
                except Exception:
                    m.ai_importance = 0.0
                self._save_moments()
                break
    
    def analyze_with_multimodal(
        self,
        frame,
        frame_number: int,
        transcript_text: str,
        person_count: int = 0,
        track_ids: Optional[List[int]] = None,
        timestamp: Optional[float] = None,
        video_frames: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[Dict[str, Any]]:
        """澶氭ā鎬佽仈鍚堝垎鏋愶紙闊抽?戠獥鍙ｈ浆鍐? + 鍗曞抚鍥惧儚锛夈�?

        Args:
            frame: 当前帧图�?
            frame_number: ֡��
            transcript_text: 涓庤?ュ抚瀵归綈鐨勭煭绐楀彛杞?鍐欐枃鏈?锛堥�氬父涓郝?10绉掔獥鍙ｏ級
            person_count: 当前人数
            track_ids: 统一后的 person_id 列表
            timestamp: 璇ュ抚瀵瑰簲鐨? epoch 鏃堕棿鎴筹紙鐢ㄤ簬涓庤浆鍐?/瑙嗛?戠墖娈靛?归綈锛?
            video_frames: 鍙?閫夌殑瑙嗛?戝抚绐楀彛锛堟潵鑷? 5 鍒嗛挓鍒囩墖缂撳啿锛夛紝鐢ㄤ簬鐢熸垚涓庤?ユ椂鍒诲尮閰嶇殑瑙嗛?戠墖娈?

        Returns:
            LLM 分析结果 dict（仅当命�?关键时刻并成功�?�录时返回），否�? None
        """
        if not self.qwen_available:
            print("⚠️ LLM 不可�?，跳过�?�模态分�?")
            return None

        # 榛樿?わ細鏃犳湁鏁堣??闊宠浆鍐欐椂涓嶅仛鈥滃叧閿?鏃跺埢鍒ゅ畾/钀藉簱鈥濓紝閬垮厤绾?瑙嗚?夊湪璇佹嵁涓嶈冻鏃朵贡璇淬�?
        # 鏀瑰姩锛氫负浜嗘弧瓒斥�滄瘡涓ゅ垎閽熷己鍒剁敓鎴愬崱鐗団�濈殑闇�姹傦紝灏嗛粯璁ゅ�兼敼涓? 0 (False)锛屽厑璁哥函瑙嗚?夊垎鏋愩�?
        require_transcript = (os.environ.get("MULTIMODAL_REQUIRE_TRANSCRIPT", "0") or "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
            "on",
        }
        if self._transcript_is_missing(transcript_text):
            if require_transcript:
                return None
            return self._analyze_frame_only(frame, frame_number, person_count, track_ids or [])

        import cv2

        try:
            # 将帧编码�? base64
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            image_base64 = base64.b64encode(buffer).decode('utf-8')

            track_ids = track_ids or []
            prompt = f"""你是协作学习研究专家，使用专业的行为编码框架分析协作场景。

场景说明：这是“创客马拉松 / Hackathon”现场（做原型、写代码、调试、讨论方案），但我们希望卡片文案像体育赛事直播一样有节奏、有梗。

你将收到：一帧视频画面 + 与该帧时间对齐的短窗口语音转写（通常±10秒）。

【判定原则（非常重要）】
1) 不要为了找而找：如果证据不足/不明确/只是普通流程对话，请返回 is_key_moment=false。
2) 关键时刻应当体现清晰的“认知/协作跃迁”，优先 R2/R3。
    但在“讲授/观点输出/结构化讲解”场景里，如果出现：
    - 清晰的概念定义/框架提出（Und-Exp）
    - 结构化总结/列点（例如“有三个点/第一第二第三”）
    - 关键提问推动思考（Init-Feed/Und-Exp）
    也可以判为关键（importance 给到 0.50—0.75，视证据强度）。
3) importance 标定要保守：
    - 0.00—0.39：普通互动/重复信息/流程
    - 0.40—0.59：有价值但不构成“关键”（通常仍应 is_key_moment=false）
    - 0.60—0.79：关键（证据清晰，可复述）
    - 0.80—1.00：强关键（明显突破/转折/共识/方法改变）
4) 输出要短：description/meeting_note 控制在 1-2 句，信息密度高，可复述。
5) 需要提供 card_summary：用于卡片的简短摘要，**严格20-30字**，"体育赛事播报风 + 创客马拉松语境"，更口语更好玩；可带 2-3 个轻量表情符号（如 🎯💡💣🔥🍌），但不要低俗。

【视觉信息】画面中的场景
【语音内容】与该帧对齐的窗口对话转写:
"{transcript_text}"

请根据以下完整编码框架进行识别：

=================================================================
维度一：参与与沉浸 (Engagement) - 投入时间、情感状态与心流体验
=================================================================

【Eng-Flow 沉浸/心流】
- Engage: [R1]探索性困惑(好奇/困惑), [R1]真实性确认
- Investigate: [R1]问题命名(重构问题), [R1]信息供给
- Act: [R0]具象化行动(制作草图/模型), [R1]改进意图

【Eng-Emo 情感/氛围】
- Engage: [R0]情感连接(破冰), [R0]尊重确认(肯定观点), [R1]相互印证
- Investigate: [R0]资源接入, [R0]物理陪伴, [R1]邀请思考
- Act: [R0]实质协作, [R1]赞美评价, [R1]集体自豪

【Eng-Strug 挣扎/坚持】
- Engage: [R1]识别困难, [R1]处理难题
- Investigate: [R1]识别分歧, [R1]设定限制
- Act: [R1]潜力评估, [R2]验证假设

=================================================================
维度二：主动性与意图 (Initiative) - 设定目标、寻求反馈、承担风险
=================================================================

【Init-Goal 目标/计划】
- Engage: [R1]目标锚定, [R1]计划制定, [R1]澄清细节
- Investigate: [R1]角色分配, [R1]流程建议, [R2]认知代理
- Act: [R2]构思发散(数量优先), [R2]决策叠加, [R2]妥协陈述

【Init-Feed 反馈/验证】
- Engage: [R1]观点陈述, [R1]理解想法
- Investigate: [R2]理由质疑, [R2]澄清分歧, [R2]综合分析
- Act: [R2]迭代修改, [R2]事实测试, [R2]经验测试

【Init-Risk 风险/争论】
- Engage: [R2]对比想法, [R2]疯狂想法
- Investigate: [R2]探索不一致, [R2]论证推理, [R2]批判挑战
- Act: [R3]超越自我(新综合), [R2]论据权重, [R3]框架重构

=================================================================
维度三：社会支架 (Social Scaffolding) - 互助、激发灵感、物理连接
=================================================================

【Soc-Ind 独立/自说自话】
- [R0]独立陈述(Monologue), [R0]平行研习, [R0]平行制作(Co-acting)

【Soc-Help 互助/教学】
- Engage: [R0]关系确认, [R1]建议劝告
- Investigate: [R1]消除盲区, [R1]信息提供, [R1]文献支持
- Act: [R0]直接任务协作, [R1]积极参与, [R3]对称贡献

【Soc-Insp 激发/共享】
- Engage: [R1]印证例子, [R2]丰富语境
- Investigate: [R2]数据支持, [R2]权威扩展, [R2]解释细化
- Act: [R3]启发发现("A ha!"), [R3]综合观点, [R3]整合隐喻

【Soc-Conn 连接/协同】
- Engage: [R0]物理在场, [R1]共享责任
- Investigate: [R1]促进理解, [R0]同伴关系
- Act: [R3]贡献专长, [R3]共同建构, [R2]兴趣叠加

=================================================================
维度四：理解的发展 (Understanding) - 顿悟、解释策略、应用知识
=================================================================

【Und-Exp 解释/推演】
- Engage: [R1]定义问题, [R1]问题命名
- Investigate: [R1]参考经验, [R2]解释连接, [R2]引用支持
- Act: [R2]解释方案, [R2]协商术语, [R2]细化观点

【Und-Aha 顿悟/突破】★关键
- Engage: [R3]真实基石, [R3]洞察力生成
- Investigate: [R3]发现时刻"I find it!"💡, [R3]可改进思想
- Act: [R3]新的综合💡, [R3]应用新知, [R3]元认知改变💡

【Und-Strive 深思/内化】
- Engage: [R1]认知困惑, [R2]精神生活
- Investigate: [R2]个人思考, [R2]检查实践, [R2]识别问题
- Act: [R2]反向反思, [R2]认知图式测试, [R2]隐含性决策

=================================================================
理论来源图例
=================================================================
[LDF]: Tinkering学习维度  [Hack4CBL]: 时间阶段
[IAM]: 交互分析模型       [DT]: d.school设计思维
[EVT]: 有价值教育对话     [KB]: 知识建构原则
[Co-ref]: 共同反思实践    [SSBC]: 社会支持行为
R0-R3: Fleck和Fitzpatrick(2010)反思层级

=================================================================

请分析并以JSON格式返回:
{{
    "is_key_moment": true/false,
    "importance": 0.0-1.0,
    "reflection_level": "R0|R1|R2|R3",
    "phase": "Engage|Investigate|Act",
    "primary_dimension": "Engagement|Initiative|Social|Understanding",
    "behavior_code": "L1行为代码如 Eng-Flow/Eng-Emo/Init-Goal/Soc-Help/Und-Aha等",
    "specific_behavior": "具体子行为如 [R2]论证推理/[R3]发现时刻/[R1]问题命名等",
    "theoretical_source": "理论来源如 [IAM]PhII/A/[EVT]启发式/[KB]超越自我等",
    "description": "一句话描述正在发生什么（偏客观、可复述）",
    "card_summary": "用于关键时刻卡片的一句话（更口语/更幽默，可带表情符号）",
    "key_quote": "如果有关键对话，摘录最重要的一句",
    "observable_evidence": "可观察的行为证据",
    "meeting_note": "用于会议纪要的简洁记录"
}}

只返回JSON，不要其他内容。"""
            result_text = self._run_vision_llm(
                image_base64=image_base64,
                prompt=prompt,
                model_override=self.vision_model,
                temperature=0.4,
                max_tokens=800
            )
            
            # 解析 JSON
            if result_text.startswith("```"):
                lines = result_text.split("```")
                result_text = lines[1] if len(lines) > 1 else lines[0]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
            
            result = json.loads(result_text.strip())

            # 追踪：打印模型原始JSON（截�?/全量�? LLM_TRACE_* 控制�?
            self._llm_trace_decision("multimodal parsed_json", result if isinstance(result, dict) else {"raw": result})

            # 多模态分析阈值（与AI棄1�7测阈值保持一致）
            threshold = float(os.environ.get("MULTIMODAL_KEY_THRESHOLD", "0.35"))
            # 降低冷却时间，避免漏记重要时�?
            cooldown_s = float(os.environ.get("MULTIMODAL_COOLDOWN_SECONDS", "8"))
            debug_flag = (os.environ.get("MULTIMODAL_DEBUG", "0") or "0").strip().lower()
            debug_enabled = debug_flag in ("1", "true", "yes", "y", "on")
            debug_mode = (os.environ.get("MULTIMODAL_DEBUG_MODE", "concise") or "concise").strip().lower()

            now_ts = float(timestamp) if isinstance(timestamp, (int, float)) else time.time()
            last_ts = float(getattr(self, "_last_multimodal_moment_ts", 0.0) or 0.0)
            too_close = (now_ts - last_ts) < cooldown_s

            importance = float(result.get("importance", 0) or 0)
            is_key = bool(result.get("is_key_moment", False))

            # 寮哄埗蹇?鐓фā寮忥細濡傛灉鐜?澧冨彉閲忚?剧疆浜嗗己鍒跺揩鐓э紝鍒欏拷鐣?AI鍒ゅ畾鐨? False 鍜岄噸瑕佹�ч槇鍊?
            force_snapshot = (os.environ.get("MULTIMODAL_FORCE_SNAPSHOT", "0") or "0").strip() == "1"
            
            allow_bypass_cooldown = importance >= 0.85
            ok_to_record = (is_key and importance >= threshold and (not too_close or allow_bypass_cooldown)) or force_snapshot

            # 如果�?强制�?照，�?�? is_key 以便后续逻辑正确处理
            if force_snapshot and not is_key:
                is_key = True
                result["is_key_moment"] = True
                if importance < 0.1:
                    result["importance"] = 0.5 # 给个默�?�重要�1�7?

            # 总是打印清晰的判定结果（命中或未命中），方便用户直接在终�?看到
            summary_desc = (result.get("description") or result.get("meeting_note") or "")[:40].replace("\n", " ")
            rl = (result.get("reflection_level") or "").strip()
            phase = (result.get("phase") or "").strip()
            dim = (result.get("primary_dimension") or result.get("dimension") or "").strip()
            
            if ok_to_record:
                # 命中会由后续逻辑打印 "�? 发现关键时刻"
                pass 
            else:
                # 分析拒绝原因
                reasons = []
                if not is_key:
                    reasons.append("AI�ж��ǹ؄1�7?")
                if importance < threshold:
                    reasons.append(f"重�?��1�7�不�?({importance:.2f}<{threshold})")
                if too_close and not allow_bypass_cooldown:
                    reasons.append(f"��ȴ�1�7?({int(now_ts - last_ts)}s<{int(cooldown_s)}s)")
                
                reason_str = ", ".join(reasons)
                print(f"🧾 �?命中: {reason_str} | 重�?��1�7?:{importance:.2f} | 标�??:{dim}/{phase}/{rl} | 摘�??:{summary_desc}...")

            # Debug 杈撳嚭锛氶粯璁ゅ彧鎵撳嵃鈥滃垽瀹氬叧閿?瀛楁?碘�濓紝閬垮厤鎶婂叏鏂?/闀胯浆鍐欏埛灞?
            if debug_enabled:
                rl = (result.get("reflection_level") or "").strip()
                phase = (result.get("phase") or "").strip()
                code = (result.get("behavior_code") or "").strip()
                print(
                    f"�1�7?? MM frame={frame_number} key={is_key} imp={importance:.2f} thr={threshold:.2f} "
                    f"cooldown={too_close}({cooldown_s:.0f}s) ok={ok_to_record} rl={rl} phase={phase} code={code}"
                )

                if debug_mode in {"verbose", "full"}:
                    spec = (result.get("specific_behavior") or "").strip()
                    if spec:
                        print(f"   �1�79�1�74 {spec}")
                    preview = (transcript_text or "").replace("\n", " ").strip()
                    if len(preview) > 120:
                        preview = preview[:120] + "�1�7?"
                    if preview:
                        print(f"   �9�7�1�7? {preview}")

            # 追踪：打印判定依�?
            self._llm_trace_decision(
                "multimodal decision",
                {
                    "is_key_moment": is_key,
                    "importance": importance,
                    "threshold": threshold,
                    "cooldown_s": cooldown_s,
                    "too_close": too_close,
                    "allow_bypass_cooldown": allow_bypass_cooldown,
                    "ok_to_record": ok_to_record,
                },
            )

            if ok_to_record:
                self._record_multimodal_moment(
                    frame=frame,
                    frame_number=frame_number,
                    person_count=person_count,
                    track_ids=track_ids or [],
                    transcript=transcript_text,
                    ai_result=result,
                    timestamp=now_ts,
                    video_frames=video_frames,
                )
                self._last_multimodal_moment_ts = now_ts
                return result

            if debug_enabled:
                if not is_key:
                    reason = "is_key_moment=false"
                elif importance < threshold:
                    reason = f"importance<{threshold:.2f}"
                elif too_close and not allow_bypass_cooldown:
                    reason = f"cooldown<{cooldown_s:.0f}s"
                else:
                    reason = "filtered"
                print(f"   �1�70�1�73 skip: {reason}")

            return None
                
        except json.JSONDecodeError as e:
            print(f"�1�77�1�72�1�71�1�75 Multimodal Analysis JSON parse error: {e}")
            return None
        except Exception as e:
            print(f"�7�2�1�5 Multimodal Analysis failed: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _analyze_frame_only(self, frame, frame_number: int,
                            person_count: int, track_ids: List[int]) -> Optional[Dict]:
        """绾?鍥惧儚鍒嗘瀽锛堟棤璇?闊虫椂鐨勫洖閫�锛?"""
        # 改动：默认允许纯图像生成关键时刻
        allow = (os.environ.get("ALLOW_IMAGE_ONLY_KEY_MOMENTS", "1") or "1").strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
            "on",
        }
        if not allow:
            return None
        # 调用原有的图像分析（�?能会落库 AI_DETECTED�?
        # 注意：这里改为同步调用或者需等待结果才能返回给integrated_system
        # 鐢变簬 _analyze_frame_with_ai 鍘熸湰璁捐?′负void锛屾垜浠?闇�瑕佺◢寰?鏀归�犲畠鎴栬�呯洿鎺ヨ繖閲岃繑鍥? mock result
        # 浣嗕负浜嗗?嶇敤閫昏緫锛屾垜浠?鍏堣?╁畠璺戯紙寮傛??/鍚屾?ュ彇鍐充簬瀹炵幇锛夛紝瀹冧細鑷?宸? _record_ai_moment
        self._analyze_frame_with_ai(frame, frame_number, person_count, track_ids or [])
        
        # 返回丄1�7�?占位符，告诉integrated_system我们尝试�?
        return {"status": "image_analysis_triggered"}
    
    def _record_multimodal_moment(
        self,
        frame,
        frame_number: int,
        person_count: int,
        track_ids: List[int],
        transcript: str,
        ai_result: Dict[str, Any],
        timestamp: Optional[float] = None,
        video_frames: Optional[List[Dict[str, Any]]] = None,
    ) -> KeyMoment:
        """璁板綍澶氭ā鎬佸垎鏋愮殑鍏抽敭鏃跺埢锛屽苟灏介噺鐢熸垚涓庝箣鍖归厤鐨勮?嗛?戠墖娈点�?"""
        import cv2

        timestamp = float(timestamp) if isinstance(timestamp, (int, float)) else time.time()
        duration = timestamp - self.start_time
        time_str = self._format_time(duration)

        moment_id = f"multimodal_{int(timestamp)}_{frame_number}"

        # 保存关键�?
        frame_filename = f"{moment_id}.jpg"
        frame_path = self.moments_dir / frame_filename
        cv2.imwrite(str(frame_path), frame)

        # 构建描述（优先使用简�?的card_summary显示在卡片上�?
        card_summary = (ai_result.get("card_summary") or "").strip()
        full_description = (ai_result.get("description", "") or "").strip()
        description = card_summary or full_description  # 优先箄1�7�?摘�??
        key_quote = (ai_result.get("key_quote") or "").strip()
        if key_quote and key_quote not in description:
            description += f' �1�79�1�76 "{key_quote}"'
        
        # 🏷�? �?动生成tags（从existing text content提取关键词）
        tags = ai_result.get("tags", [])
        if not tags or len(tags) == 0:
            # 从tagline/description�?动提取关�?词作为tags
            tagline = (ai_result.get("tagline") or "").strip()
            text_for_tags = tagline or description or transcript or ""
            # 改进的分词：按标点�?�号分割，提取短�?
            import re
            # 移除emoji (修复乱码range)
            try:
                # 匹配常见Emoji范围
                clean_text = re.sub(r'[\U00010000-\U0010ffff]', '', text_for_tags)
            except:
                clean_text = text_for_tags
            
            # 按标点和空格分割
            clean_text = re.sub(r'[，。！？、：“”‘’（）【】\s]+', '|', clean_text)
            words = [w.strip() for w in clean_text.split('|') if w.strip()]
            
            # 过滤：只保留2-8字的�?�?，排除常见词
            stopwords = {
                '的', '了', '和', '与', '在', '是', '有', '就', '都', '很', '也', '而', '及', '或', '被', '把',
                '我们', '你们', '他们', '她们', '它们', '这里', '那里', '这个', '那个', '一个', '一些',
            }
            filtered = []
            for w in words:
                if 2 <= len(w) <= 8 and w not in stopwords:
                    filtered.append(w)
            
            tags = filtered[:3]  # �1�7?ȡǰ3�1�7?
            if not tags:
                tags = []

        moment = KeyMoment(
            id=moment_id,
            timestamp=timestamp,
            frame_number=frame_number,
            source=MomentSource.AI_DETECTED.value,
            frame_path=str(frame_path),
            time_str=time_str,
            duration_seconds=duration,
            transcript=transcript,
            ai_description=description,
            ai_importance=ai_result.get("importance", 0.7),
            ai_tags=tags,  # 使用�?动生成的tags
            analysis=ai_result.get("meeting_note", "") or description,
            person_count=person_count,
            track_ids=track_ids,
            user_note=ai_result.get("observable_evidence", ""),
        )
        
        self.moments.append(moment)
        self.stats["ai_detected"] += 1
        self.stats["total_moments"] += 1

        # 鍏堜繚瀛橈紝鍐嶇敓鎴愯?嗛?戯紙纭?淇濆悗鍙板?勭悊鍙?鍥炲啓 transcript/analysis锛?
        self._save_moments()

        before_s = float(os.environ.get("MULTIMODAL_BEFORE_SECONDS", "15"))
        after_s = float(os.environ.get("MULTIMODAL_AFTER_SECONDS", "15"))

        # 馃幀 缁熶竴浣跨敤frame_buffer鐢熸垚瀹屾暣30绉掕?嗛?戯紙淇濊瘉涓�鑷存�э級
        # 移除min_required_frames阈�1�7�判�?，确保所有AI棄1�7测的关键时刻都是固定时长
        video_path, video_duration = self._save_video_clip(
            moment_id=moment_id,
            clip_duration_before=float(before_s),
            clip_duration_after=float(after_s),  # ǰ��15�1�7?=30�1�7?
            frame_number=frame_number,
            frame=frame,
            center_timestamp=float(timestamp),
        )
        if video_path:
            moment.video_path = video_path
            moment.video_duration = video_duration
            self._save_moments()
            print(f"   ✅ 完整视频已生成: {video_duration:.1f}秒 (前{before_s:.0f}秒 + 后{after_s:.0f}秒)")
        else:
            print(f"   ⚠️  视�?�生成失�?")
        
        moment_type = ai_result.get("moment_type", "unknown")
        print(f"���📷 多模态关�?时刻: {time_str} [{moment_type}]")
        print(f"   �1�79�1�75 {description}")
        if ai_result.get("meeting_note"):
            print(f"   �9�7 �1�7?�1�7?: {ai_result['meeting_note']}")
        print(f"   �9�5�1�7? ��1�7??: {', '.join(ai_result.get('tags', []))}")
        
        return moment
    
    def generate_meeting_notes(self, transcript_segments: List[Dict] = None) -> Dict[str, Any]:
        """
        鐢熸垚鏅鸿兘浼氳??绾?瑕?
        
        Args:
            transcript_segments: 完整的转写片段列�? [{"text": "...", "timestamp": ...}, ...]
            
        Returns:
            浼氳??绾?瑕佸瓧鍏?
        """
        if not self.qwen_available:
            return self._generate_simple_meeting_notes(transcript_segments)
        
        try:
            # 鍑嗗?囨椂鍒绘憳瑕?
            moments_summary = []
            for m in sorted(self.moments, key=lambda x: x.timestamp):
                summary = {
                    "time": m.time_str,
                    "type": "�û���1�7??" if m.source == "user_anchor" else "AIʶ��",
                    "description": m.ai_description or m.user_note or "�1�7?����",
                    "tags": m.ai_tags,
                    "note": m.user_note if m.source != "user_anchor" else ""
                }
                moments_summary.append(summary)
            
            # 鍑嗗?囪浆鍐欐枃鏈?
            full_transcript = ""
            if transcript_segments:
                full_transcript = " ".join([s.get("text", "") for s in transcript_segments])
            
            zh_note_instr = "All output fields (summary, key_points, action_items, decisions) must be in Simplified Chinese."
            prompt = f"""你是纪录片导演和教育研究者。请基于以下协作学习活动中的关键时刻，创作一份团队叙事报告。

关键时刻记录:
{json.dumps(moments_summary, ensure_ascii=False, indent=2)}

请生成:
1. 叙事总结 (3-5句话的整体故事线)
2. 关键章节 (将时刻组织成有意义的阶段)
3. 团队洞察 (从这些时刻中观察到的协作模式和亮点)
4. 反思问题 (2-3个引发学生反思的问题)

以JSON格式返回:
{{
    "narrative_summary": "整体叙事...",
    "chapters": [
        {{
            "title": "章节标题",
            "time_range": "00:00-05:00",
            "description": "这个阶段发生了什么",
            "moment_ids": ["相关moment的id"]
        }}
    ],
    "team_insights": ["洞察1", "洞察2"],
    "reflection_questions": ["问题1", "问题2"]
}}
"""
            result_text = self._run_text_llm(
                prompt=prompt,
                model_override=self.text_model,
                temperature=0.4,
                max_tokens=2000
            )
            
            # 解析 JSON
            if result_text.startswith("```"):
                lines = result_text.split("```")
                result_text = lines[1] if len(lines) > 1 else lines[0]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
            
            meeting_notes = json.loads(result_text.strip())
            meeting_notes["generated_at"] = datetime.now().isoformat()
            meeting_notes["total_moments"] = len(self.moments)
            meeting_notes["transcript_length"] = len(full_transcript) if full_transcript else 0
            
            # 淇濆瓨浼氳??绾?瑕?
            notes_file = self.moments_dir / "meeting_notes.json"
            with open(notes_file, 'w', encoding='utf-8') as f:
                json.dump(meeting_notes, f, ensure_ascii=False, indent=2)
            
            print(f"📋 会�??�?要生成完�?")
            return meeting_notes
            
        except Exception as e:
            print(f"⚠️ 会�??�?要生成失�?: {e}")
            return self._generate_simple_meeting_notes(transcript_segments)
    
    def _generate_simple_meeting_notes(self, transcript_segments: List[Dict] = None) -> Dict[str, Any]:
        """鐢熸垚绠�鍗曚細璁?绾?瑕侊紙鏃? AI锛?"""
        full_transcript = ""
        if transcript_segments:
            full_transcript = " ".join([s.get("text", "") for s in transcript_segments])
        
        # 从关�?时刻提取要点
        key_points = []
        for m in self.moments:
            if m.ai_description:
                key_points.append(m.ai_description)
            elif m.user_note:
                key_points.append(f"[用户标�?�] {m.user_note}")
        
        return {
            "summary": f"�?次会�?共�?�录 {len(self.moments)} �?关键时刻，转写文�?�? {len(full_transcript)} 字�1�7?",
            "discussion_topics": [],
            "decisions": [],
            "action_items": [],
            "key_quotes": key_points[:5],  # 朄1�7�?5�?
            "participants_count": max([m.person_count for m in self.moments]) if self.moments else 0,
            "generated_at": datetime.now().isoformat(),
            "total_moments": len(self.moments),
            "transcript_length": len(full_transcript)
        }


    def _record_ai_moment(self, frame, frame_number: int,
                          person_count: int, track_ids: List[int],
                          ai_result: Dict[str, Any]):
        """记录 AI 识别的关键时刻"""
        import cv2
        
        timestamp = time.time()
        duration = timestamp - self.start_time
        time_str = self._format_time(duration)
        
        # 生成唯一ID
        moment_id = f"ai_{int(timestamp)}_{frame_number}"
        
        # 保存截图
        image_filename = f"{moment_id}.jpg"
        image_path = self.moments_dir / image_filename
        cv2.imwrite(str(image_path), frame)
        
        # 提取 AI 分析结果
        description = ai_result.get("description", "AIʶ��Ĺؼ�ʱ��")
        tags = ai_result.get("tags", [])
        importance = ai_result.get("importance", 0.5)
        # 兼容不同 prompt 的字段
        if not tags:
            tags = ai_result.get("tags", [])
        
        # 创建关键时刻
        moment = KeyMoment(
            id=moment_id,
            timestamp=timestamp,
            frame_number=frame_number,
            source=MomentSource.AI_DETECTED.value,
            frame_path=str(image_path),
            time_str=time_str,
            duration_seconds=duration,
            person_count=person_count,
            track_ids=track_ids.copy() if track_ids else [],
            ai_description=description,
            ai_tags=tags,
            ai_importance=importance,
            analysis=ai_result.get("meeting_note", "") or ai_result.get("analysis", "")
        )

        # 先落盘 moment，确保后台线程更新时可找到
        self.moments.append(moment)
        self.stats["ai_detected"] += 1
        self.stats["total_moments"] += 1
        self._save_moments()

        # 🎬 与手动标记保持一致: 先保存前15秒视频，然后延迟生成完整30秒视频
        # 第一阶段: 保存前15秒视频
        print(f"   🎬 [AI视频] 第一阶段: 开始保存前{KEY_MOMENT_BEFORE_SECONDS:.0f}秒视频...")
        video_path, video_duration = self._save_video_clip(
            moment_id=moment_id,
            clip_duration_before=float(KEY_MOMENT_BEFORE_SECONDS),  # 15�1�7�1�7
            frame_number=frame_number,
            frame=frame,
            center_timestamp=timestamp  # 使用AI检测时刻作为中心
        )
        if video_path:
            moment.video_path = video_path
            moment.video_duration = video_duration
            self._save_moments()
            print(f"   ✅ [AI视频] 第一阶段完成: {video_duration:.1f}秒视频已保存")
        else:
            print(f"   ⚠️ AI关键时刻视频生成失败: {moment_id}")
            return  # 如果第一阶段失败，不继续
        
        # 第二阶段: 启动后台线程，等待15秒后生成包含后段的完整视频
        print(f"   🎬 [AI视频] 第二阶段: 启动延迟线程，{KEY_MOMENT_AFTER_SECONDS:.0f}秒后生成完整视频")
        # 第二阶段: 启动后台线程，等待15秒后生成包含后段的完整视频
        print(f"   🎬 [AI视频] 第二阶段: 启动延迟线程，{KEY_MOMENT_AFTER_SECONDS:.0f}秒后生成完整视频")
        
        # 使用闭包捕获当前所需变量
        def delayed_video_extension(mid, ts, frm):
            try:
                print(f"   ⏳ [AI视频延迟] 线程开始 (moment_id={mid}), 等待 {KEY_MOMENT_AFTER_SECONDS:.0f} 秒...")
                time.sleep(float(KEY_MOMENT_AFTER_SECONDS))
                print(f"   🎬 [AI视频延迟] 唤醒! 开始生成完整视频: {mid}")
                self._extend_video_with_after_frames(mid, ts, frm)
            except Exception as e:
                print(f"   ❌ [AI视频延迟] 线程异常: {e}")
        
        # 传递参数避免闭包变量捕获问题
        extend_thread = threading.Thread(
            target=delayed_video_extension, 
            args=(moment_id, timestamp, frame.copy()),
            daemon=True
        )
        extend_thread.start()
        print(f"   ✅ [AI视频] 延迟线程已启动 (thread_id={extend_thread.ident}, moment_id={moment_id})")
        
        print(f"👁️ AI 识别关键时刻: {time_str}")
        print(f"   �1�79�1�75 {description[:60]}...")
        print(f"   🏷️ 标签: {', '.join(tags[:3])}")
        print(f"   ⭐ 重要性: {importance:.2f}")
        print(f"   🎞️ 视频 (前{KEY_MOMENT_BEFORE_SECONDS:.0f}秒): {video_duration:.1f}秒")
        print(f"   ⏳ {KEY_MOMENT_AFTER_SECONDS:.0f}秒后将生成完整视频并进行AI分析...")
    
    # ============================================================
    # 📖 叙事生成 (The Narrative)
    # ============================================================
    
    def generate_narrative(self) -> Dict[str, Any]:
        """
        生成团队叙事 (Oeuvre)
        
        鍍忕邯褰曠墖瀵兼紨涓�鏍凤紝灏嗙?庣墖鍖栫殑鐥曡抗鍓?杈戞垚杩炶疮鐨勫洟闃熷彊浜?
        """
        if not self.moments:
            return {"narrative": "���޹ؼ�ʱ�̼�¼", "chapters": []}
        
        if not self.qwen_available:
            return self._generate_simple_narrative()
        
        try:
            # 鍑嗗?囨椂鍒绘憳瑕?
            moments_summary = []
            for m in sorted(self.moments, key=lambda x: x.timestamp):
                summary = {
                    "time": m.time_str,
                    "source": "�û���1�7??" if m.source == "user_anchor" else "AIʶ��",
                    "description": m.user_note or m.ai_description or "�1�7?����",
                    "person_count": m.person_count,
                    "importance": m.ai_importance if m.source == "ai_detected" else 0.8,
                    "tags": m.ai_tags
                }
                moments_summary.append(summary)
            
            prompt = f"""浣犳槸涓�浣嶇邯褰曠墖瀵兼紨鍜屾暀鑲茬爺绌惰�呫�傝?峰熀浜庝互涓嬪崗浣滃?︿範娲诲姩涓?鐨勫叧閿?鏃跺埢锛屽垱浣滀竴浠藉洟闃熷彊浜嬫姤鍛娿�?

关键时刻记录:
{json.dumps(moments_summary, ensure_ascii=False, indent=2)}

请生�?:
1. 叙事总结 (3-5句话的整体故事线)
2. 关键章节 (将时刻组织成有意义的阶�??)
3. 团队洞察 (从这些时刻中观察到的协作模式和亮�?)
4. 鍙嶆�濋棶棰? (2-3涓?寮曞?煎?︾敓鍙嶆�濈殑闂?棰?)

�?JSON格式返回:
{{
    "narrative_summary": "整体叙事...",
    "chapters": [
        {{
            "title": "�½ڱ�1�7??",
            "time_range": "00:00-05:00",
            "description": "这个阶�?�发生了仄1�7�?",
            "moment_ids": ["相关moment的id"]
        }}
    ],
    "team_insights": ["洞察1", "洞察2"],
    "reflection_questions": ["�?�?1", "�?�?2"]
}}"""

            result_text = self._run_text_llm(
                prompt=prompt,
                model_override=self.text_model,
                temperature=0.4,
                max_tokens=1500
            )
            
            # 解析 JSON
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
            
            narrative = json.loads(result_text)
            narrative["generated_at"] = datetime.now().isoformat()
            narrative["total_moments"] = len(self.moments)
            
            # 保存叙事
            narrative_file = self.moments_dir / "narrative.json"
            with open(narrative_file, 'w', encoding='utf-8') as f:
                json.dump(narrative, f, ensure_ascii=False, indent=2)
            
            print(f"📖 叙事生成完成")
            return narrative
            
        except Exception as e:
            print(f"⚠️ 叙事生成失败: {e}")
            return self._generate_simple_narrative()
    
    def _generate_simple_narrative(self) -> Dict[str, Any]:
        """生成箄1�7单叙�? (�? AI)"""
        sorted_moments = sorted(self.moments, key=lambda x: x.timestamp)
        
        chapters = []
        current_chapter_moments = []
        chapter_start_time = 0
        
        # 按时间间隔分章节 (5分钟丄1�7�?)
        for m in sorted_moments:
            if m.duration_seconds - chapter_start_time > 300 and current_chapter_moments:
                chapters.append({
                    "title": f"�1�7�0�0�1�7 {len(chapters) + 1}",
                    "time_range": f"{self._format_time(chapter_start_time)}-{self._format_time(current_chapter_moments[-1].duration_seconds)}",
                    "description": f"记录�? {len(current_chapter_moments)} �?关键时刻",
                    "moment_ids": [cm.id for cm in current_chapter_moments]
                })
                current_chapter_moments = []
                chapter_start_time = m.duration_seconds
            
            current_chapter_moments.append(m)
        
        # 添加朄1�7后一�?章节
        if current_chapter_moments:
            chapters.append({
                "title": f"�1�7�0�0�1�7 {len(chapters) + 1}",
                "time_range": f"{self._format_time(chapter_start_time)}-{self._format_time(current_chapter_moments[-1].duration_seconds)}",
                "description": f"记录�? {len(current_chapter_moments)} �?关键时刻",
                "moment_ids": [cm.id for cm in current_chapter_moments]
            })
        
        user_count = sum(1 for m in self.moments if m.source == "user_anchor")
        ai_count = sum(1 for m in self.moments if m.source == "ai_detected")
        
        return {
            "narrative_summary": f"本次活动共记录了 {len(self.moments)} 个关键时刻，其中用户主动标记 {user_count} 个，AI 自动识别 {ai_count} 个。",
            "chapters": chapters,
            "team_insights": [
                f"用户主动标记了 {user_count} 个认为重要的时刻",
                f"AI 系统识别了 {ai_count} 个潜在的协作亮点"
            ],
            "reflection_questions": [
                "回顾这些关键时刻，哪�?朄1�7让你印象深刻？为仄1�7么？",
                "在标记的时刻中，团队的协作模式有什么特点？"
            ],
            "generated_at": datetime.now().isoformat(),
            "total_moments": len(self.moments)
        }
    
    # ============================================================
    # 🔧 工具方法
    # ============================================================
    
    def _format_time(self, seconds: float) -> str:
        """格式化时间为 HH:MM:SS"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    def get_moments(self, source: str = None) -> List[Dict]:
        """
        获取关键时刻列表
        
        Args:
            source: �?选过�? - 'user_anchor' �? 'ai_detected'
        """
        moments = self.moments
        if source:
            moments = [m for m in moments if m.source == source]
        
        return [m.to_dict() for m in sorted(moments, key=lambda x: x.timestamp)]
    
    def get_stats(self) -> Dict:
        """鑾峰彇缁熻?′俊鎭?"""
        return {
            **self.stats,
            "session_duration": self._format_time(time.time() - self.start_time),
            "ai_enabled": self.qwen_available,
            "ai_interval": self.ai_interval_seconds
        }
    
    def get_moment_image_path(self, moment_id: str) -> Optional[str]:
        """获取关键时刻图片�?�?"""
        for m in self.moments:
            if m.id == moment_id:
                return m.frame_path
        return None
    
    def get_moment_video_path(self, moment_id: str) -> Optional[str]:
        """鑾峰彇鍏抽敭鏃跺埢瑙嗛?戠墖娈佃矾寰?"""
        for m in self.moments:
            if m.id == moment_id:
                return m.video_path if m.video_path else None
        return None

    def generate_linkography(self, moments: List[Dict]) -> Dict:
        """生成 Linkography 图：nodes + edges（使�? LLM 从卡片内容推�?跨时刻关联）�?

        说明�?
        - 仅允许引用输�? moments 的信�?，不足则返回�? edges�?
        - 输出结构用于前�??�?视化：{"status":"ok", "nodes":[], "edges":[]}�?
        """

        # 兜底
        if not isinstance(moments, list) or not moments:
            return {"status": "ok", "nodes": [], "edges": []}

        # 缂撳瓨锛氶伩鍏嶉?戠箒杞?璇㈣Е鍙戦噸澶? LLM 璋冪敤
        try:
            sig = "|".join([str(m.get("id")) for m in moments])
        except Exception:
            sig = str(len(moments))

        cache = getattr(self, "_linkography_cache", None)
        if isinstance(cache, dict):
            if cache.get("sig") == sig and (time.time() - float(cache.get("ts") or 0.0)) < 30:
                return cache.get("result") or {"status": "ok", "nodes": [], "edges": []}

        # LLM 不可用时，仍返回 nodes，edges 为空
        if not getattr(self, "qwen_available", False):
            nodes = []
            for m in moments:
                nodes.append({
                    "id": str(m.get("id")),
                    "t": float(m.get("timestamp") or 0.0),
                    "label": (m.get("ai_tagline") or m.get("user_note") or "").strip()[:24]
                })
            result = {"status": "llm_unavailable", "nodes": nodes, "edges": []}
            self._linkography_cache = {"sig": sig, "ts": time.time(), "result": result}
            return result

        # 组织 prompt：尽量短、但信息足�??
        def _short(s: str, n: int) -> str:
            s = (s or "").strip().replace("\n", " ")
            return s if len(s) <= n else (s[:n] + "�1�7?")

        items = []
        for m in moments:
            mid = str(m.get("id"))
            ts = m.get("timestamp")
            try:
                tsf = float(ts) if isinstance(ts, (int, float, str)) else 0.0
            except Exception:
                tsf = 0.0
            dt = ""
            try:
                if tsf > 0:
                    dt = datetime.fromtimestamp(tsf).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                dt = ""

            source = (m.get("source") or "").strip()
            tagline = _short(m.get("ai_tagline") or "", 80)
            desc = _short(m.get("ai_description") or m.get("ai_analysis") or "", 200)
            note = _short(m.get("user_note") or "", 100)
            transcript = _short(m.get("transcript") or "", 150)
            tags = m.get("ai_tags") or []
            if not isinstance(tags, list):
                tags = []
            tags_txt = ",".join([str(t) for t in tags[:4]])

            items.append({
                "id": mid,
                "timestamp": tsf,
                "datetime": dt,
                "source": source,
                "tagline": tagline,
                "desc": desc,
                "note": note,
                "transcript": transcript,
                "tags": tags_txt,
            })

        system = (
            "你是一个严谨的协作分析助手。\n"
            "任务：基于给定的关键时刻卡片内容，找出不同时刻之间的可解释联系（Linkography）。\n"
            "必须遵守：1) 只能引用输入字段，不得编造；2) 如果证据不足，就不连边；3) 输出必须是严格 JSON（不要代码块、不要额外文字）。\n"
            "�����ͽ��飺same_topic, follow_up, cause_effect, supports, contradicts, decision_related��"
        )

        prompt = (
            "给你一组 moments（按时间排序）。请输出一个 JSON 对象：\n"
            "{\n"
            "  \"nodes\": [{\"id\":\"...\",\"t\":1700000000.0,\"label\":\"...\"}],\n"
            "  \"edges\": [{\"source\":\"id1\",\"target\":\"id2\",\"type\":\"same_topic\",\"reason\":\"<=20�1�7�1�7\"}]\n"
            "}\n"
            "要求：\n"
            "- nodes 必须覆盖所有输入 id；label 用中文短语概括（<=16字）。\n"
            "- edges 最多 60 条，连接明确相关或可能相关的关系；reason 必须短且可从输入中推断。\n"
            "- 不要使用不存在的 id。\n\n"
            + json.dumps(items, ensure_ascii=False, indent=2)
        )

        raw = self._run_text_llm(prompt=prompt, system=system, temperature=0.1, max_tokens=4000)
        txt = (raw or "").strip()
        if txt.startswith("```"):
            parts = txt.split("```")
            txt = parts[1].strip() if len(parts) > 1 else txt
            if txt.startswith("json"):
                txt = txt[4:].strip()

        result: Dict[str, Any] = {"status": "ok", "nodes": [], "edges": []}
        try:
            data = json.loads(txt)
        except Exception:
            # 灏濊瘯浠庢枃鏈?涓?鎶藉彇绗?涓�涓? JSON 瀵硅薄
            m = re.search(r"\{[\s\S]*\}", txt)
            if m:
                try:
                    data = json.loads(m.group(0))
                except Exception:
                    data = None
            else:
                data = None

        if isinstance(data, dict):
            nodes = data.get("nodes") or []
            edges = data.get("edges") or []
            if isinstance(nodes, list):
                result["nodes"] = nodes
            if isinstance(edges, list):
                result["edges"] = edges
        else:
            # 朄1�7坏兜底：仅节�?
            print(f"�1�7? JSON PARSE FAILED. Raw Output:\n{txt}")
            result["status"] = "parse_failed"
            result["nodes"] = [{"id": it["id"], "t": it["timestamp"], "label": _short(it.get("tagline") or it.get("note") or "", 12)} for it in items]
            result["edges"] = []

        # 规范化 nodes：确保每个输入 id 都在
        seen = set()
        norm_nodes = []
        for n in result.get("nodes") or []:
            if not isinstance(n, dict):
                continue
            nid = str(n.get("id") or "")
            if not nid or nid in seen:
                continue
            seen.add(nid)
            try:
                t = float(n.get("t") or 0.0)
            except Exception:
                t = 0.0
            label = _short(str(n.get("label") or ""), 16)
            norm_nodes.append({"id": nid, "t": t, "label": label})

        by_id = {it["id"]: it for it in items}
        for it in items:
            if it["id"] not in seen:
                norm_nodes.append({
                    "id": it["id"],
                    "t": float(it.get("timestamp") or 0.0),
                    "label": _short(it.get("tagline") or it.get("note") or "", 12),
                })

        # 规范化 edges：过滤无效 id
        valid_ids = set(by_id.keys())
        norm_edges = []
        for e in result.get("edges") or []:
            if not isinstance(e, dict):
                continue
            s = str(e.get("source") or "")
            t = str(e.get("target") or "")
            if not s or not t or s == t:
                continue
            if s not in valid_ids or t not in valid_ids:
                continue
            et = _short(str(e.get("type") or ""), 24)
            rs = _short(str(e.get("reason") or ""), 20)
            norm_edges.append({"source": s, "target": t, "type": et, "reason": rs})
            if len(norm_edges) >= 40:
                break

        # 按时间排序 nodes，前端更好用
        norm_nodes.sort(key=lambda x: float(x.get("t") or 0.0))
        result["nodes"] = norm_nodes
        result["edges"] = norm_edges

        self._linkography_cache = {"sig": sig, "ts": time.time(), "result": result}
        return result


# ============================================================
# 🧪 测试
# ============================================================

if __name__ == "__main__":
    import numpy as np
    
    print("=" * 60)
    print("🎯 双轨关键时刻识别系统 - 测试")
    print("=" * 60)
    
    # 创建管理器
    manager = KeyMomentsManager()
    
    # 模拟用户标记
    fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    
    print("\n🎥 测试用户标记...")
    moment1 = manager.mark_user_anchor(
        frame=fake_frame,
        frame_number=100,
        person_count=3,
        track_ids=[1, 2, 3],
        user_note="团队讨论激烈"
    )
    
    time.sleep(1)
    
    moment2 = manager.mark_user_anchor(
        frame=fake_frame,
        frame_number=250,
        person_count=2,
        track_ids=[1, 2],
        user_note="发现关键问题"
    )
    
    # 获取统计
    print("\n📊 统计信息:")
    stats = manager.get_stats()
    for k, v in stats.items():
        print(f"   {k}: {v}")
    
    # 鑾峰彇鎵�鏈夋椂鍒?
    print("\n📋 扄1�7有关�?时刻:")
    moments = manager.get_moments()
    for m in moments:
        print(f"   [{m['source']}] {m['time_str']} - {m.get('user_note') or m.get('ai_description', 'N/A')}")
    
    # 生成叙事
    print("\n📖 生成叙事...")
    narrative = manager.generate_narrative()
    print(f"   ժ�1�7??: {narrative.get('narrative_summary', '')}")
    
    print("\n�? 测试完成!")
