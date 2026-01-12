#!/usr/bin/env python3
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
from urllib.parse import quote
import threading
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from enum import Enum

# ============================================================
# ⏱️ 关键时刻时间窗（默认前后各15秒，可用环境变量覆盖）
# ============================================================

KEY_MOMENT_BEFORE_SECONDS = float(os.environ.get("KEY_MOMENT_BEFORE_SECONDS", "15"))
KEY_MOMENT_AFTER_SECONDS = float(os.environ.get("KEY_MOMENT_AFTER_SECONDS", "15"))

# ============================================================
# 📦 数据结构
# ============================================================

class MomentSource(Enum):
    """关键时刻来源"""
    USER_ANCHOR = "user_anchor"      # 用户按钮标记
    AI_DETECTED = "ai_detected"      # AI 自动识别
    AI_HIGHLIGHT = "ai_highlight"    # AI 识别的高光时刻


@dataclass
class KeyMoment:
    """关键时刻数据结构"""
    id: str                          # 唯一ID: timestamp_source
    timestamp: float                 # Unix 时间戳
    frame_number: int                # 帧号
    source: str                      # 来源: user_anchor / ai_detected
    frame_path: str                  # 关键帧图片路径
    
    # 视频片段
    video_path: str = ""             # 视频片段路径 (前后各5秒)
    video_duration: float = 0        # 视频时长(秒)
    
    # 元数据
    time_str: str = ""               # 可读时间 HH:MM:SS
    duration_seconds: float = 0      # 从开始到这一刻的秒数
    
    # 用户输入 (仅 user_anchor)
    user_note: str = ""              # 用户备注 (可选)
    
    # 语音数据
    transcript: str = ""             # 语音转文字内容

    # 语音/模型元信息（用于回答“现在ASR是什么模型”）
    asr_provider: str = ""           # fireredasr | dashscope | ...
    asr_model: str = ""              # 例如 aed:FireRedASR-AED-L 或 paraformer-realtime-v2
    asr_model_dir: str = ""          # FireRedASR 模型目录（如适用）
    
    # AI 分析结果 (仅 ai_detected)
    ai_description: str = ""         # AI 对这一刻的描述
    ai_tagline: str = ""             # AI 短标签（用于贴纸/短标识；可选）
    ai_importance: float = 0.0       # AI 评估的重要性 0-1
    ai_tags: List[str] = field(default_factory=list)  # AI 提取的标签
    ai_framework_tags: str = ""      # 协作学习框架标签（如[R2]论证、Eng-Flow等）
    analysis: str = ""               # AI 综合分析/总结

    # LLM 元信息
    llm_provider: str = ""           # qwen | claude
    llm_model: str = ""              # 实际调用的模型（此处多为 vision_model）
    
    # 场景信息
    person_count: int = 0            # 当前画面人数
    track_ids: List[int] = field(default_factory=list)  # 活跃的追踪ID
    
    # 叙事元素 (由 LLM 生成)
    narrative_role: str = ""         # 在叙事中的角色: opening/rising/climax/falling/resolution
    narrative_text: str = ""         # 叙事文本
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        d = asdict(self)
        # 前端用 `||` 做兜底时，空字符串/None 才会正确回退；纯空白字符串会导致“看起来没内容”。
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
# 🎬 关键时刻管理器
# ============================================================

class KeyMomentsManager:
    """双轨关键时刻管理器"""
    
    def __init__(self, data_dir: Path = None, api_key: str = None,
                 video_source: str = None, audio_source: str = None, microphone_recorder=None,
                 video_fps: float = None):
        """
        初始化管理器
        
        Args:
            data_dir: 数据存储目录
            api_key: DashScope API Key (用于 Qwen-VL)
            video_source: 原始视频文件路径或摄像头ID (用于提取音频)
            audio_source: 音频源路径 (可选, 如果与视频不同)
            microphone_recorder: 麦克风录制器实例 (摄像头模式使用)
        """
        self.data_dir = data_dir or Path(__file__).parent / "integrated_data"
        self.moments_dir = self.data_dir / "key_moments"
        self.moments_dir.mkdir(parents=True, exist_ok=True)
        
        # 麦克风录制器
        self.microphone_recorder = microphone_recorder
        
        # API 配置 (LLM provider: qwen | claude)
        self.dashscope_api_key = api_key or os.environ.get("DASHSCOPE_API_KEY", "")
        self.claude_api_key = os.environ.get("ANTHROPIC_API_KEY", "") or os.environ.get("CLAUDE_API_KEY", "")
        self.llm_provider = os.environ.get("LLM_PROVIDER", "qwen").lower()
        self.text_model = os.environ.get("LLM_MODEL") or ("claude-3-5-haiku-20241022" if self.llm_provider.startswith("claude") else "qwen-max")
        self.vision_model_fast = os.environ.get("VISION_MODEL_FAST") or ("claude-3-5-haiku-20241022" if self.llm_provider.startswith("claude") else "qwen-vl-plus")
        self.vision_model = os.environ.get("VISION_MODEL") or ("claude-3-5-haiku-20241022" if self.llm_provider.startswith("claude") else "qwen-vl-max-latest")

        # FireRedASR 模型缓存（关键时刻转写会频繁触发；避免每次 from_pretrained 导致卡顿/高延迟）
        self._fireredasr_lock = threading.Lock()
        self._fireredasr_model = None

        # moments 的并发更新（用户标记线程 / after 扩展线程 / AI线程都可能写入）
        self._moments_lock = threading.Lock()

        # 重任务限流：关键时刻“提取音频→ASR→多模态AI”会占用较多 CPU/GIL。
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
        
        # 🎬 视频/音频源配置 (用于提取音频轨道)
        self.video_source = video_source  # 原始视频文件路径
        self.audio_source = audio_source or video_source  # 音频源 (默认与视频相同)
        self.video_fps = float(video_fps) if video_fps else None
        
        # 状态
        self.moments: List[KeyMoment] = []
        self.start_time: float = time.time()
        self.frame_count: int = 0
        
        # 🎬 视频帧缓冲区 (用于录制关键时刻前后的视频片段)
        self.frame_buffer: list = []      # 存储 (frame, frame_num, timestamp) 元组
        # 缓冲区最大保留秒数（需覆盖关键时刻窗口 + AI分析延迟 + 余量）
        # 从60秒增加到120秒，以适应AI分析延迟（约60秒）
        self.buffer_max_seconds = int(max(120, KEY_MOMENT_BEFORE_SECONDS + KEY_MOMENT_AFTER_SECONDS + 90))
        # 按最高可能FPS(60)计算，确保FPS波动时仍能覆盖120秒
        self.buffer_fps = 60.0
        self.buffer_max_frames = int(self.buffer_max_seconds * self.buffer_fps)
        print(f"   🔧 [BUFFER] Config: max_seconds={self.buffer_max_seconds}, fps={self.buffer_fps}, max_frames={self.buffer_max_frames}, format=JPEG")
        self.buffer_lock = threading.Lock()
        
        # 🔊 音频缓冲区 (用于录制对应的音频片段)
        self.audio_buffer: list = []      # 存储 (audio_chunk, timestamp) 元组
        self.audio_buffer_lock = threading.Lock()
        
        # AI 分析配置
        self.ai_interval_seconds = 210  # 3.5分钟一次切片
        self.last_ai_analysis_time: float = 0
        self.ai_analysis_buffer: List[tuple] = []  # (frame, frame_num, timestamp)
        
        # 统计 (必须在加载历史数据前初始化)
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
            audio_status = f"✅ 文件音频"
        
        print("🎯 关键时刻管理器已启动")
        print(f"   📁 存储: {self.moments_dir.name}")
        print(f"   🎤 音频: {audio_status}")
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

                # 轻量迁移：历史数据里有些 moment 的 ai_description 是“短标签”(<=14字)，
                # 但 analysis 中包含“详细描述：…”，会导致卡片信息密度下降。这里自动提升一次。
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
                        # 移除emoji
                        clean_text = re.sub(r'[😀-🙏💀-🛿🎀-🏿🐀-🦿🌀-🗿⚀-⛿✀-➿]', '', text_for_tags)
                        # 按标点和空格分割
                        clean_text = re.sub(r'[，。！？、：；""''（）【】\s]+', '|', clean_text)
                        words = [w.strip() for w in clean_text.split('|') if w.strip()]
                        
                        # 过滤：只保留2-8字的短语
                        stopwords = {'的', '了', '和', '与', '在', '是', '有', '这', '那', '就', '不', '也', '都', '还', '从', '到'}
                        filtered = [w for w in words if 2 <= len(w) <= 8 and w not in stopwords]
                        
                        tags = filtered[:3]
                        if not tags:
                            tags = []
                        m.ai_tags = tags
                        tags_updated = True
                
                if tags_updated:
                    print(f"   🏷️ 为历史数据补充了tags")
                    self._save_moments()
                
                print(f"   已加载 {len(self.moments)} 个历史关键时刻")
            except Exception as e:
                print(f"   ⚠️ 加载历史数据失败: {e}")
    
    def _save_moments(self):
        """保存关键时刻到文件"""
        moments_file = self.moments_dir / "moments.json"
        try:
            data = {
                'moments': [m.to_dict() for m in self.moments],
                'stats': self.stats,
                'last_updated': datetime.now().isoformat()
            }
            with open(moments_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ 保存关键时刻失败: {e}")

    def _build_llm_client(self):
        """根据提供者创建 LLM 客户端"""
        if not self.llm_api_key:
            raise RuntimeError("LLM API Key 未配置")
        # 避免网络抖动/限流导致请求无限期卡住
        llm_timeout = float(os.environ.get("LLM_TIMEOUT_SECONDS", "45"))
        if self.llm_provider.startswith("claude"):
            try:
                from anthropic import Anthropic
            except ImportError as e:
                raise ImportError("请先安装 anthropic 库: pip install anthropic") from e
            # anthropic 的 timeout 配置在不同版本差异较大；此处先保持兼容，仅控制 OpenAI 路径
            return Anthropic(api_key=self.llm_api_key)
        try:
            from openai import OpenAI
        except ImportError as e:
            raise ImportError("请先安装 openai 库: pip install openai>=1.0.0") from e
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
    # 🧾 LLM Trace（打印 Prompt/返回/判定依据）
    # ============================================================

    def _llm_trace_mode(self) -> str:
        """Trace 输出等级：off / meta / compact / full

        - off: 不打印
        - meta: 只打印 meta（不打印 prompt/response）
        - compact: 打印 meta + response/decision，但隐藏 prompt（避免刷屏/泄露提示词）
        - full: 打印 meta + prompt + response
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
        print(f"🧾 LLM TRACE | {title}")
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
        """在用户标记后（尤其 AFTER 秒之后）补齐/修正展示文本。

        - user_note: 用于卡片短描述（前端优先展示）
        - transcript: 用于详情页“Transcription”
        - context_transcript: 会写入 *_context.txt，供后续 AI 分析引用
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
                # transcript：优先“窗口转写”（带时间戳的多行），即使它比旧文本短也应覆盖。
                if transcript:
                    incoming = transcript.strip()
                    existing = (m.transcript or "").strip()
                    looks_like_window = (
                        "\n" in incoming
                        or "[00:" in incoming
                        or "[0" in incoming  # 兼容 [0:xx] / [00:xx]
                    )
                    if looks_like_window:
                        if incoming and incoming != existing:
                            m.transcript = transcript
                            updated = True
                    else:
                        # 非窗口文本：仍按“更长则覆盖”的规则
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

        # 同步写回 context 文件（供 AI 分析证据引用）
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
        """从模型输出中抽取短标签（用于卡片/贴纸）和正文。支持中英文格式。"""
        if not text:
            return "", ""
        lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
        tagline = ""
        body_lines = []
        for ln in lines:
            # 支持中文和英文标签格式
            if ln.startswith("标签：") or ln.startswith("标签:") or ln.lower().startswith("label:"):
                if "：" in ln:
                    tagline = ln.split("：", 1)[1].strip()
                else:
                    tagline = ln.split(":", 1)[1].strip()
                continue
            body_lines.append(ln)

        # 兜底：如果没有显式标签，取第一句前 14 个字
        if not tagline:
            first = lines[0] if lines else ""
            tagline = first

        tagline = tagline.replace("\"", "").strip()
        if len(tagline) > 50:  # 英文标签可能更长，增大限制
            tagline = tagline[:50]
        body = "\n".join(body_lines).strip()
        if not body:
            body = text.strip()
        return tagline, body

    @staticmethod
    def _extract_detail_description(body: str) -> str:
        """从正文中抽取"详细描述"段落（用于卡片展示，更信息密集）。支持中英文格式。"""
        if not body:
            return ""
        lines = [ln.strip() for ln in body.splitlines()]
        # 支持中文和英文格式
        start = None
        for i, ln in enumerate(lines):
            if (ln.startswith("详细描述：") or ln.startswith("详细描述:") or 
                ln.lower().startswith("detailed description:")):
                start = i
                break
        if start is None:
            return ""

        def _strip_prefix(s: str) -> str:
            if "：" in s:
                return s.split("：", 1)[1].strip()
            if ":" in s:
                return s.split(":", 1)[1].strip()
            return s.strip()

        out: List[str] = []
        first = _strip_prefix(lines[start])
        if first:
            out.append(first)
        for ln in lines[start + 1 :]:
            if not ln:
                continue
            # 支持中文和英文停止标记
            if any(
                ln.startswith(p) or ln.lower().startswith(p.lower())
                for p in (
                    "上下文定位：",
                    "上下文定位:",
                    "Context Positioning:",
                    "证据摘录：",
                    "证据摘录:",
                    "Evidence Excerpt:",
                    "标签：",
                    "标签:",
                    "Label:",
                    "卡片摘要：",
                    "卡片摘要:",
                    "Card Summary:",
                    "分析框架标签",
                    "Analysis Framework Label:",
                )
            ):
                break
            out.append(ln)
        return " ".join(out).strip()
    
    @staticmethod
    def _extract_card_summary(body: str) -> str:
        """从正文中抽取\"卡片摘要\"（20-30 words的简短版本）。支持中英文格式。"""
        if not body:
            return ""
        lines = [ln.strip() for ln in body.splitlines()]
        for ln in lines:
            # 支持中文和英文格式
            if ln.startswith("卡片摘要：") or ln.startswith("卡片摘要:") or ln.lower().startswith("card summary:"):
                if "：" in ln:
                    txt = ln.split("：", 1)[-1].strip()
                else:
                    txt = ln.split(":", 1)[-1].strip()
                return txt
        return ""
    
    @staticmethod
    def _extract_framework_tags(body: str) -> str:
        """从正文中抽取'分析框架标签'段落。支持中英文格式。"""
        if not body:
            return ""
        lines = [ln.strip() for ln in body.splitlines()]
        for i, ln in enumerate(lines):
            # 支持中文和英文格式
            if (ln.startswith("分析框架标签：") or ln.startswith("分析框架标签:") or 
                ln.startswith("框架标签：") or ln.lower().startswith("analysis framework label:")):
                # 提取内容（去掉前缀）
                if "：" in ln:
                    content = ln.split("：", 1)[-1].strip()
                else:
                    content = ln.split(":", 1)[-1].strip()
                return content
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
                print("⏱️ 提示: API超时,请检查网络或增加timeout值")
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
        """从一段转写（通常为最近 5 分钟）里挑出最可能的关键时刻候选。

        Args:
            transcript_items: [{"timestamp": epoch(float), "time": "HH:MM:SS", "text": str, ...}, ...]
            max_candidates: 返回候选数量上限
            base_timestamp: 用于把 epoch 映射到相对时间（None 则自动用 transcript_items 最早 timestamp）

        Returns:
            [{"timestamp": float, "time_str": str, "reason": str}, ...]
        """
        if not transcript_items or max_candidates <= 0:
            return []
        if not self.qwen_available:
            return []

        # 若 time 为空或仍是“绝对时间(HH:MM:SS)”导致歧义，可用 base_timestamp 生成相对时间
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

        # 只取有时间+文本的行，避免无意义噪声
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
            # 控制单行长度
            if len(txt) > 120:
                txt = txt[:120] + "…"
            line = f"[{tstr}] {txt}"
            lines.append(line)
            line_by_time.setdefault(tstr, line)

        if not lines:
            return []

        # 控制 prompt 长度：最多 220 行
        if len(lines) > 220:
            lines = lines[-220:]

        system = (
            "You are a locator of key moments for classroom/presentation content."
            "Task: Select the time points most worthy of 'Key Moment Cards' from the given timestamped transcript."
            "Key moments usually include: definitions/conclusions, important data/comparisons, reasoning twists, summary sublimations, core viewpoints, strong emotions/laughter."
            "Do not force a search; if there are indeed no obvious key points, return an empty array."
            "Must provide evidence: evidence must be a short snippet quoted verbatim from the original transcript (no fabrication allowed)."
            "Output must be strict JSON (no code blocks, no extra text)."
        )
        prompt = (
            f"Please select up to {max_candidates} candidate key moments from the following transcript.\n"
            "Output format: [{\"time_str\":\"HH:MM:SS\",\"reason\":\"...\",\"evidence\":\"...\"}, ...]\n"
            "time_str must exactly match the timestamps in the transcript.\n\n"
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

            # time_str -> timestamp 映射（若 time 为空，使用 base_ts 生成的相对时间）
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

                # 证据必须能在对应时间戳那一行中找到，避免“编了一个关键句子”
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
        """用调用方提供的一段帧序列生成视频片段。

        主要用于“5分钟切片分析”场景：frame_buffer 只保留几十秒，旧时间点会过期。
        provided_frames 的元素格式为 {"frame": np.ndarray, "frame_number": int, "ts": float}。
        
        Args:
            center_timestamp: 如果提供，则只使用该时间戳前后的帧（默认±10秒）
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
        
        # 🎯 如果提供了center_timestamp，只保留该时间前后的帧
        if center_timestamp is not None:
            import os
            window_before = float(os.environ.get("MULTIMODAL_BEFORE_SECONDS", "15"))
            window_after = float(os.environ.get("MULTIMODAL_AFTER_SECONDS", "15"))
            
            start_ts = center_timestamp - window_before
            end_ts = center_timestamp + window_after
            
            filtered_frames = [f for f in clip_frames if start_ts <= f[2] <= end_ts]
            print(f"   🔍 [视频帧筛选] 原始帧数: {len(clip_frames)}, 筛选后: {len(filtered_frames)}, 窗口: 前{window_before}s + 后{window_after}s = {window_before + window_after}s")
            if filtered_frames:
                clip_frames = filtered_frames
            else:
                # 如果过滤后为空，可能是时间窗太窄或帧太少，尝试找最近的帧
                closest_frame = min(clip_frames, key=lambda f: abs(f[2] - center_timestamp))
                clip_frames = [closest_frame]
            
            if len(clip_frames) < 2: # 确保至少有两帧才能形成视频
                return None, 0

        # 准备写入视频
        video_filename = f"{moment_id}.mp4"
        video_path = self.moments_dir / video_filename

        try:
            import subprocess
            first_frame = clip_frames[0][0]
            h, w = first_frame.shape[:2]

            time_span = float(clip_frames[-1][2]) - float(clip_frames[0][2])
            est_fps = (len(clip_frames) / time_span) if time_span > 1e-6 else 10.0
            # 提高最小fps到5，最大到60，与手动标记保持一致，确保画质流畅
            est_fps = min(max(est_fps, 5.0), 60.0)

            video_duration = len(clip_frames) / est_fps

            ffmpeg_cmd = [
                'ffmpeg', '-y',
                '-f', 'rawvideo', '-pix_fmt', 'bgr24',
                '-s', f'{w}x{h}', '-r', f'{est_fps:.3f}',
                '-i', 'pipe:0',
                '-c:v', 'libx264',
                '-preset', 'slow',  # slow提供更好的压缩质量（比medium慢但质量更高）
                '-crf', '15',  # 降低到15获得更高画质（0-51，越小越好，18是默认高质量）
                '-b:v', '5M',  # 明确设置码率为5Mbps，确保高质量
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
                print(f"   🎬 视频片段已保存(切片帧): {video_filename} ({len(clip_frames)}帧, {video_duration:.1f}秒, fps≈{est_fps:.1f})")
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
        print("🔄 关键时刻管理器会话已重置")

    def delete_frame_from_timeline(self, person_id: int, frame_num: int):
        """删除 timeline 中的特定帧
        
        目前实现为空操作，因为 timeline 数据来自 face_db.detection_history
        真正的删除在 FaceDatabase.delete_person() 中处理
        """
        # Timeline 数据来自 face_db，所以删除由后端在 face_db 中处理
        print(f"✅ 已从 timeline 删除 Frame {frame_num}")
    
    def delete_moment(self, moment_id: str):
        """删除一个关键时刻
        
        Args:
            moment_id: 关键时刻 ID
        """
        # 从列表中删除
        self.moments = [m for m in self.moments if m.id != moment_id]
        
        # 删除对应的文件
        moment_dir = self.moments_dir / moment_id
        if moment_dir.exists():
            import shutil
            shutil.rmtree(moment_dir)
            print(f"✅ 已删除关键时刻 {moment_id}")
        
        # 重新保存
        self._save_moments()
        print(f"✅ 已更新关键时刻数据")
    
    # ============================================================
    # 🔴 用户标记 (The Anchor)
    # ============================================================
    
    def add_frame_to_buffer(self, frame, frame_number: int):
        """
        将帧添加到缓冲区 (每帧调用)
        
        Args:
            frame: 当前帧 (numpy array)
            frame_number: 帧号
        """
        import cv2
        # 使用 JPEG 压缩存储以节省内存 (1280x720 raw=2.7MB, jpeg~=200KB)
        success, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if not success:
            return
            
        with self.buffer_lock:
            # 存储格式: (jpeg_buffer, frame_num, timestamp)
            self.frame_buffer.append((buffer, frame_number, time.time()))
            # 保持缓冲区大小在限制内
            while len(self.frame_buffer) > self.buffer_max_frames:
                if len(self.frame_buffer) % 500 == 0:
                     print(f"   🔧 [BUFFER] Popping frame! Size={len(self.frame_buffer)}, Max={self.buffer_max_frames}")
                self.frame_buffer.pop(0)
    
    def add_audio_frame_to_buffer(self, audio_chunk: bytes, timestamp: float = None):
        """
        将音频帧添加到缓冲区 (实时调用)
        
        Args:
            audio_chunk: 音频数据块 (bytes)
            timestamp: 时间戳 (如果为None，使用当前时间)
        """
        if timestamp is None:
            timestamp = time.time()
        
        with self.audio_buffer_lock:
            self.audio_buffer.append((audio_chunk, timestamp))
            # 保持音频缓冲区大小在限制内（25秒音频 @16kHz 16-bit）
            # 估计每秒 16000 * 2 = 32KB
            while len(self.audio_buffer) > self.buffer_max_frames * 32768:  
                self.audio_buffer.pop(0)
    
    def _add_audio_to_video(self, moment_id: str, video_path: str, frame_number: int, video_duration: float,
                            frame=None, center_timestamp: float = None, window_before: float = None, window_after: float = None):
        """
        添加音频到视频（麦克风或视频源）
        
        Args:
            moment_id: 关键时刻ID
            video_path: 视频路径
            frame_number: 帧号
            video_duration: 视频时长
            frame: 关键帧图像 (用于AI分析)
        """
        import math

        # 优先使用麦克风录制的音频
        if self.microphone_recorder:
            print(f"   🎤 从麦克风保存音频...")
            # 为避免截断，取 ceil + 1 秒
            fallback_seconds = int(math.ceil(float(video_duration))) + 1

            audio_path = None
            if center_timestamp is not None and window_before is not None and window_after is not None:
                # 关键时刻完整视频：按同一时间窗对齐音频
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
                # 其他场景：回退为“最近N秒”
                audio_path = self.microphone_recorder.save_audio_clip(duration_seconds=fallback_seconds)
            if audio_path:
                self._merge_audio_to_video_async(moment_id, video_path, audio_path, frame, video_duration=video_duration)
            else:
                print(f"   ⚠️ 麦克风音频保存失败，跳过语音转文字")
        # 否则从视频源提取音频
        elif self.audio_source and Path(self.audio_source).exists():
            print(f"   🔊 从视频源提取音频...")
            self._extract_and_merge_audio_async(moment_id, video_path, frame_number, video_duration, frame)
        else:
            print(f"   ⚠️ 无可用音频源 (麦克风: {bool(self.microphone_recorder)}, 视频源: {self.audio_source})")
            print(f"   ℹ️ 视频将只包含画面，语音转文字功能不可用")
    
    def _merge_audio_to_video_async(self, moment_id: str, video_path: str, audio_path: str, frame=None, video_duration: float = None):
        """异步合并音频和视频，完成后进行语音转文字和AI分析"""
        def merge_task():
            try:
                import subprocess
                import math
                temp_video = Path(video_path).parent / f"{moment_id}_temp.mp4"
                Path(video_path).rename(temp_video)
                
                print(f"   🔧 [DEBUG] 合并命令:")
                print(f"      视频: {temp_video}")
                print(f"      音频: {audio_path}")
                print(f"      输出: {video_path}")
                
                # 关键点：不要用 -shortest，否则会把输出裁到更短的那一路，导致“只识别一半/视频变短”。
                # 这里固定输出为视频时长，并用 apad 在需要时给音频补静音。
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
                
                print(f"   🔧 [DEBUG] FFmpeg命令: {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                
                if result.returncode == 0:
                    print(f"   ✅ [后台] 音频合并成功")
                    temp_video.unlink()
                    Path(audio_path).unlink()  # 清理临时音频文件
                    
                    # 🎤📹 触发语音转文字 + AI多模态分析
                    print(f"   🎤 开始语音转文字和AI分析...")
                    self._process_video_with_multimodal_analysis(moment_id, video_path, frame)
                else:
                    print(f"   ❌ [后台] FFmpeg返回错误码: {result.returncode}")
                    print(f"   ❌ stderr: {result.stderr}")
                    print(f"   ⚠️ [后台] 恢复原视频")
                    temp_video.rename(video_path)
            except Exception as e:
                print(f"   ⚠️ [后台] 音频合并异常: {e}")
                import traceback
                traceback.print_exc()
        
        thread = threading.Thread(target=merge_task, daemon=True)
        thread.start()
    
    def _extract_and_merge_audio_async(self, moment_id: str, video_path: str, frame_number: int, video_duration: float, frame=None):
        """
        后台异步提取视频文件中的音频并合并到已保存的视频，完成后进行语音转文字和AI分析
        
        Args:
            moment_id: 关键时刻ID
            video_path: 已保存的视频路径
            frame_number: 帧号（用于计算时间位置）
            video_duration: 视频时长
            frame: 关键帧图像 (用于AI分析)
        """
        def merge_task():
            try:
                import subprocess
                
                # 计算在源视频中的位置（尽量使用真实 fps）
                assumed_fps = self.video_fps if (self.video_fps and self.video_fps > 1e-6) else 30.0
                source_start_time = frame_number / float(assumed_fps)
                
                print(f"   🔊 [后台] 从源视频提取音频 (帧{frame_number} = {source_start_time:.1f}s)...")
                
                # 临时音频文件
                audio_path = Path(video_path).parent / f"{moment_id}_audio.m4a"
                output_path = Path(video_path).parent / f"{moment_id}_with_audio.mp4"
                
                # 步骤1: 从源视频提取音频
                cmd_extract = [
                    'ffmpeg', '-y', '-loglevel', 'error',
                    '-ss', str(source_start_time),
                    '-t', str(video_duration + 1),  # 多提取1秒作为缓冲
                    '-i', str(self.audio_source),
                    '-vn',
                    '-map', '0:a:0?',
                    '-c:a', 'aac', '-b:a', '128k',
                    str(audio_path)
                ]
                
                result = subprocess.run(cmd_extract, timeout=30)

                def _maybe_backfill_transcript_from_source():
                    """当合并音频失败时，仍尝试从源视频直接提取 WAV 并做 ASR，避免 transcript 为空。"""
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
                                # 只在缺失时回填，避免覆盖更完整结果
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
                    print(f"   ⚠️ [后台] 音频提取失败")
                    _maybe_backfill_transcript_from_source()
                    return
                
                print(f"   ✅ [后台] 音频提取成功")
                
                # 步骤2: 合并音视频
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
                    # 用合并后的视频替换原视频
                    Path(video_path).unlink()
                    output_path.rename(video_path)
                    audio_path.unlink()
                    print(f"   ✅ [后台] 音频合并成功")
                    
                    # 🎤📹 触发语音转文字 + AI多模态分析
                    print(f"   🎤 开始语音转文字和AI分析...")
                    self._process_video_with_multimodal_analysis(moment_id, video_path, frame)
                else:
                    print(f"   ⚠️ [后台] 音频合并失败，保留原视频")
                    _maybe_backfill_transcript_from_source()
                    
            except subprocess.TimeoutExpired:
                print(f"   ⚠️ [后台] 音频处理超时")
            except Exception as e:
                print(f"   ⚠️ [后台] 音频处理异常: {e}")
        
        # 启动后台线程
        thread = threading.Thread(target=merge_task, daemon=True)
        thread.start()
    
    def _extract_audio_from_video(self, video_source: str, start_time: float, 
                                   duration: float, output_audio_path: str) -> bool:
        """
        从视频文件提取指定时间段的音频
        
        Args:
            video_source: 源视频文件路径
            start_time: 开始时间 (秒, 相对于文件开始)
            duration: 提取时长 (秒)
            output_audio_path: 输出音频文件路径
            
        Returns:
            True 如果成功, False 如果失败
        """
        try:
            import subprocess
            
            # 使用 ffmpeg 提取音频
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
                    print(f"   🔊 音频已提取: {Path(output_audio_path).name} ({file_size} bytes)")
                    return True
            
            return False
            
        except Exception as e:
            print(f"   ⚠️ 音频提取失败: {e}")
            return False
    
    def _merge_audio_to_video(self, video_path: str, audio_path: str, 
                              output_path: str) -> bool:
        """
        将音频轨道合并到视频文件
        
        Args:
            video_path: 视频文件路径 (含视频但无音频)
            audio_path: 音频文件路径
            output_path: 输出文件路径
            
        Returns:
            True 如果成功, False 如果失败
        """
        try:
            import subprocess
            
            # 使用 ffmpeg 合并音视频
            ffmpeg_cmd = [
                'ffmpeg', '-y',
                '-i', str(video_path),
                '-i', str(audio_path),
                '-c:v', 'copy',  # 直接复制视频流
                '-c:a', 'aac',   # 重新编码音频为AAC
                '-shortest',  # 以较短的流长度为准
                '-n',  # 不覆盖
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
                print(f"   🎬 音视频已合并: {Path(output_path).name} ({merged_size} bytes)")
                
                # 删除临时文件
                try:
                    Path(video_path).unlink()
                    Path(audio_path).unlink()
                except:
                    pass
                
                return True
            
            return False
            
        except Exception as e:
            print(f"   ⚠️ 音视频合并失败: {e}")
            return False
    
    def _save_video_clip(self, moment_id: str, clip_duration_before: float = 10.0,
                         clip_duration_after: float = 0.0, frame_number: int = 0, frame=None,
                         center_timestamp: Optional[float] = None) -> tuple:
        """
        从帧缓冲区保存视频片段
        
        Args:
            moment_id: 关键时刻ID
            clip_duration_before: 标记时刻前保留的秒数 (默认10秒)
            clip_duration_after: 标记时刻后等待的秒数 (需要异步实现)
            
        Returns:
            (video_path, duration) 或 (None, 0) 如果失败
        """
        import cv2
        
        with self.buffer_lock:
            if len(self.frame_buffer) < 10:  # 至少需要10帧
                print(f"   ⚠️ 帧缓冲区不足，无法生成视频 ({len(self.frame_buffer)} 帧)")
                return None, 0
            
            # 🔍 调试：打印buffer状态
            if self.frame_buffer:
                buffer_start_ts = self.frame_buffer[0][2]
                buffer_end_ts = self.frame_buffer[-1][2]
                buffer_span = buffer_end_ts - buffer_start_ts
                print(f"   🔍 [DEBUG] Buffer状态: {len(self.frame_buffer)} 帧, 时间跨度: {buffer_span:.1f}秒")
                print(f"   🔍 [DEBUG] Buffer范围: [{buffer_start_ts:.2f}, {buffer_end_ts:.2f}]")
            
            # 获取以 center_timestamp 为中心的帧（默认用当前时刻）
            center_ts = float(center_timestamp) if isinstance(center_timestamp, (int, float)) else time.time()
            start_ts = center_ts - float(clip_duration_before)
            end_ts = center_ts + float(clip_duration_after)
            
            print(f"   🔍 [DEBUG] 目标窗口: [{start_ts:.2f}, {end_ts:.2f}], 中心: {center_ts:.2f}")
            print(f"   🔍 [DEBUG] 窗口宽度: {clip_duration_before:.1f}s (前) + {clip_duration_after:.1f}s (后) = {clip_duration_before + clip_duration_after:.1f}s")
            
            clip_frames = []
            for frame_buf, frame_num, ts in self.frame_buffer:
                if start_ts <= ts <= end_ts:
                    # 解码 JPEG
                    frame = cv2.imdecode(frame_buf, cv2.IMREAD_COLOR)
                    if frame is not None:
                        clip_frames.append((frame, frame_num, ts))
            
            print(f"   🔍 [DEBUG] 筛选结果: 收集到 {len(clip_frames)} 帧")
        
        if len(clip_frames) == 0:
            # timestamp不在buffer范围（历史时刻已过期），使用当前时间重试
            print(f"   ⚠️ 历史timestamp不在buffer范围，使用当前时间重新筛选")
            center_ts = time.time()
            start_ts = center_ts - float(clip_duration_before)
            end_ts = center_ts + float(clip_duration_after)
            
            print(f"   🔍 [RETRY] 新窗口: [{start_ts:.2f}, {end_ts:.2f}], 中心: {center_ts:.2f}")
            
            # 先收集当前可用的帧
            for frame_buf, frame_num, ts in self.frame_buffer:
                if start_ts <= ts <= end_ts:
                    # 解码 JPEG
                    frame = cv2.imdecode(frame_buf, cv2.IMREAD_COLOR)
                    if frame is not None:
                        clip_frames.append((frame, frame_num, ts))
            
            print(f"   🔍 [RETRY] 初步筛选结果: 收集到 {len(clip_frames)} 帧")
            
            # 如果需要后续帧，等待buffer收集
            if clip_duration_after > 0 and len(clip_frames) < 1800:
                wait_seconds = float(clip_duration_after)
                print(f"   ⏳ 等待 {wait_seconds:.0f}秒 收集后续帧...")
                time.sleep(wait_seconds)
                
                # 重新筛选，包含新收集的帧
                clip_frames = []
                with self.buffer_lock:
                    for frame_buf, frame_num, ts in self.frame_buffer:
                        if start_ts <= ts <= end_ts:
                            frame = cv2.imdecode(frame_buf, cv2.IMREAD_COLOR)
                            if frame is not None:
                                clip_frames.append((frame, frame_num, ts))
                
                print(f"   🔍 [RETRY] 等待后筛选结果: 收集到 {len(clip_frames)} 帧")
        
        if len(clip_frames) < 10:
            # 如果仍然不够（buffer本身太小），使用最近一段缓冲区兜底
            print(f"   ⚠️ 筛选帧数仍然不足 ({len(clip_frames)} < 10)，使用最近300帧兜底")
            # 同样需要解码
            clip_frames = []
            for frame_buf, frame_num, ts in list(self.frame_buffer)[-300:]:
                frame = cv2.imdecode(frame_buf, cv2.IMREAD_COLOR)
                if frame is not None:
                    clip_frames.append((frame, frame_num, ts))
        
        if not clip_frames:
            return None, 0
        
        # 准备写入视频
        video_filename = f"{moment_id}.mp4"
        video_path = self.moments_dir / video_filename
        
        try:
            import subprocess
            
            # 获取帧尺寸
            first_frame = clip_frames[0][0]
            h, w = first_frame.shape[:2]
            
            # 计算实际帧率
            time_span = clip_frames[-1][2] - clip_frames[0][2]
            actual_fps = len(clip_frames) / time_span if time_span > 0 else 30
            actual_fps = min(max(actual_fps, 15), 60)  # 限制在15-60fps
            
            video_duration = len(clip_frames) / actual_fps
            
            # 方法1: 尝试使用 ffmpeg 管道直接输出 H.264 MP4
            try:
                # 使用 ffmpeg 从原始帧数据创建视频
                ffmpeg_cmd = [
                    'ffmpeg', '-y',
                    '-f', 'rawvideo', '-pix_fmt', 'bgr24',
                    '-s', f'{w}x{h}', '-r', str(int(actual_fps)),
                    '-i', 'pipe:0',
                    '-c:v', 'libx264',
                    '-preset', 'slow',  # slow提供更好的压缩质量
                    '-crf', '15',  # 高画质（与LLM识别保持一致）
                    '-b:v', '5M',  # 5Mbps码率确保高质量
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
                    print(f"   🎬 视频片段已保存 (H.264): {video_filename} ({len(clip_frames)}帧, {video_duration:.1f}秒)")
                    
                    # 🔊 添加音频
                    self._add_audio_to_video(moment_id, str(video_path), frame_number, video_duration, frame)
                    
                    return str(video_path), video_duration
                    
            except Exception as e:
                print(f"   ⚠️ ffmpeg 方法失败: {e}")
            
            # 方法2: 回退到 OpenCV 保存 (可能无法在浏览器播放)
            fourcc = cv2.VideoWriter_fourcc(*'avc1')  # 尝试 H.264
            writer = cv2.VideoWriter(str(video_path), fourcc, actual_fps, (w, h))
            
            if not writer.isOpened():
                # 如果 avc1 不可用，使用 mp4v
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                writer = cv2.VideoWriter(str(video_path), fourcc, actual_fps, (w, h))
            
            for frame, _, _ in clip_frames:
                writer.write(frame)
            
            writer.release()
            
            print(f"   🎬 视频片段已保存 (OpenCV): {video_filename} ({len(clip_frames)}帧, {video_duration:.1f}秒)")
            
            # 🔊 添加音频
            self._add_audio_to_video(moment_id, str(video_path), frame_number, video_duration, frame)
            
            return str(video_path), video_duration
            
        except Exception as e:
            print(f"   ❌ 保存视频失败: {e}")
            import traceback
            traceback.print_exc()
            return None, 0
    
    def _add_audio_to_clip_async(self, moment_id: str, video_path: str, 
                                  start_timestamp: float, duration: float, frame_number: int = 0):
        """
        在后台线程中从源视频中提取音频并添加到关键时刻视频
        此函数在后台运行，不阻塞主视频处理线程
        
        Args:
            moment_id: 关键时刻ID
            video_path: 视频文件路径 (不含音频)
            start_timestamp: 视频片段在系统中的开始时间戳 (用于日志)
            duration: 视频片段时长 (秒)
            frame_number: 关键时刻的帧号 (用于计算视频中的位置)
        """
        try:
            print(f"   🎬 [后台线程开始] moment_id={moment_id}, audio_source={self.audio_source}")
            
            if not self.audio_source:
                print(f"   ⚠️ [后台线程] audio_source 为 None")
                return
                
            if not Path(self.audio_source).exists():
                print(f"   ⚠️ [后台线程] 音频源不存在: {self.audio_source}")
                return
            
            # 计算在源视频中的起始时间 (基于帧号和尽量真实的FPS)
            assumed_fps = self.video_fps if (self.video_fps and self.video_fps > 1e-6) else 30.0
            source_start_time = frame_number / float(assumed_fps)
            
            # 提取音频
            audio_path = Path(video_path).parent / f"{moment_id}_audio.m4a"
            
            print(f"   🎬 [后台] 正在从源视频提取音频 (帧{frame_number} = {source_start_time:.1f}s)...")
            
            audio_extracted = self._extract_audio_from_video(
                self.audio_source,
                source_start_time,
                duration + 1,  # 多提取1秒作为缓冲
                str(audio_path)
            )
            
            if not audio_extracted:
                print(f"   ⚠️ [后台] 未能从源视频提取音频")
                return
            
            # 合并音视频
            temp_video_path = Path(video_path).parent / f"{moment_id}_temp.mp4"
            if Path(video_path).exists():
                Path(video_path).rename(temp_video_path)
            
            print(f"   🔗 [后台] 正在合并音视频...")
            audio_merged = self._merge_audio_to_video(
                str(temp_video_path),
                str(audio_path),
                video_path
            )
            
            if not audio_merged:
                # 如果合并失败, 恢复原始视频
                print(f"   ⚠️ [后台] 合并失败，使用无音频版本")
                try:
                    if temp_video_path.exists():
                        temp_video_path.rename(video_path)
                except:
                    pass
            else:
                print(f"   ✅ [后台] 音频已成功合并")
            
            print(f"   ✅ [后台线程完成]")
            
        except Exception as e:
            print(f"   ⚠️ [后台线程异常] {e}")
            import traceback
            traceback.print_exc()
    
    def _add_audio_to_clip(self, moment_id: str, video_path: str, 
                           start_timestamp: float, duration: float, frame_number: int = 0):
        """
        在后台线程中异步添加音频轨道 (不阻塞主线程)
        """
        print(f"   🔊 [主线程] _add_audio_to_clip 被调用，moment_id={moment_id}")
        thread = threading.Thread(
            target=self._add_audio_to_clip_async,
            args=(moment_id, video_path, start_timestamp, duration, frame_number),
            daemon=True
        )
        print(f"   🔊 [主线程] 启动后台线程...")
        thread.start()
        print(f"   🔊 [主线程] 后台线程已启动")

    def mark_user_anchor(self, frame, frame_number: int, 
                         person_count: int = 0, track_ids: List[int] = None,
                         user_note: str = "", transcript: str = "", context_transcript: str = "") -> KeyMoment:
        """
        用户按下按钮标记当前时刻 (0.5秒意图锚定)
        保存前 KEY_MOMENT_BEFORE_SECONDS 秒的视频，并启动后台任务等待 KEY_MOMENT_AFTER_SECONDS 秒
        
        Args:
            frame: 当前帧图像 (numpy array)
            frame_number: 帧号
            person_count: 当前人数
            track_ids: 活跃的追踪ID
            user_note: 用户备注
            transcript: 最近的语音转文字内容（用于即时展示）
            context_transcript: 更长的历史上下文（用于后续AI分析，可能被截断）
            
        Returns:
            创建的 KeyMoment 对象
        """
        import cv2
        
        timestamp = time.time()
        duration = timestamp - self.start_time
        time_str = self._format_time(duration)
        
        # 生成唯一ID
        moment_id = f"anchor_{int(timestamp)}_{frame_number}"
        
        # 保存关键帧
        frame_filename = f"{moment_id}.jpg"
        frame_path = self.moments_dir / frame_filename
        cv2.imwrite(str(frame_path), frame)
        
        # 为该关键时刻保存上下文（按键原因 + 历史转写），供后续AI分析读取
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

        # 创建关键时刻 (视频路径暂空，由后台线程生成)
        moment = KeyMoment(
            id=moment_id,
            timestamp=timestamp,
            frame_number=frame_number,
            source=MomentSource.USER_ANCHOR.value,
            frame_path=str(frame_path),
            video_path="",  # 暂时为空
            video_duration=0.0,
            time_str=time_str,
            duration_seconds=duration,
            user_note=user_note,
            transcript=transcript,  # 保存语音转文字
            person_count=person_count,
            track_ids=track_ids or []
        )
        
        self.moments.append(moment)
        self.stats["user_anchors"] += 1
        self.stats["total_moments"] += 1
        
        # 立即保存一次，确保前端能立即刷出卡片并触发特效
        self._save_moments()
        
        print(f"🔴 用户标记关键时刻: {time_str} (帧 {frame_number})")
        if user_note:
            print(f"   📝 备注: {user_note}")
        if transcript:
            print(f"   🎤 实时语音片段: {transcript[:50]}...")
        
        # 🎬 启动后台线程: 1.保存初始视频 -> 2.等待扩展 -> 3.触发AI分析
        def async_video_processing():
            # 1. 保存前 KEY_MOMENT_BEFORE_SECONDS 秒的视频片段
            try:
                video_path, video_duration = self._save_video_clip(
                    moment_id,
                    clip_duration_before=float(KEY_MOMENT_BEFORE_SECONDS),
                    frame_number=frame_number,
                    center_timestamp=timestamp,
                )
                
                if video_path:
                    print(f"   🎬 初始视频已生成 (前{KEY_MOMENT_BEFORE_SECONDS:.0f}秒): {video_duration:.1f}秒")
                    moment.video_path = video_path
                    moment.video_duration = video_duration
                    self._save_moments() # 更新视频路径
            except Exception as e:
                print(f"   ❌ 初始视频生成失败: {e}")

            # 2. 等待 after 秒后生成包含后段的完整视频
            print(f"   ⏳ {KEY_MOMENT_AFTER_SECONDS:.0f}秒后将扩展完整视频并进行AI分析...")
            time.sleep(float(KEY_MOMENT_AFTER_SECONDS))  # 等待收集后续帧
            self._extend_video_with_after_frames(moment_id, timestamp, frame.copy())
        
        processing_thread = threading.Thread(target=async_video_processing, daemon=True)
        processing_thread.start()
        
        return moment

    def _extend_video_with_after_frames(self, moment_id: str, original_timestamp: float, frame=None):
        """
        延迟调用：合并标记时刻前后各10秒的视频
        
        Args:
            moment_id: 关键时刻ID
            original_timestamp: 原始标记的时间戳
            frame: 关键帧图像 (用于后续AI分析)
        """
        import cv2
        
        print(f"   🎬 [完整视频扩展] 开始处理 moment_id={moment_id}, timestamp={original_timestamp:.2f}")
        
        try:
            with self.buffer_lock:
                before_s = float(KEY_MOMENT_BEFORE_SECONDS)
                after_s = float(KEY_MOMENT_AFTER_SECONDS)

                # 诊断日志
                print(f"   🔧 [DEBUG] 帧缓冲区总大小: {len(self.frame_buffer)} 帧")
                if len(self.frame_buffer) > 0:
                    buffer_start_ts = self.frame_buffer[0][2]
                    buffer_end_ts = self.frame_buffer[-1][2]
                    buffer_span = buffer_end_ts - buffer_start_ts
                    print(f"   🔧 [DEBUG] 缓冲区时间跨度: {buffer_span:.1f}秒")
                    print(f"   🔧 [DEBUG] 目标窗口: [{original_timestamp - before_s:.1f}, {original_timestamp + after_s:.1f}] = {before_s + after_s:.0f}秒")
                
                # 获取标记时刻前后窗口的帧
                clip_frames = []
                for frame_buf, frame_num, ts in self.frame_buffer:
                    if original_timestamp - before_s <= ts <= original_timestamp + after_s:
                        # 解码 JPEG
                        frame = cv2.imdecode(frame_buf, cv2.IMREAD_COLOR)
                        if frame is not None:
                            clip_frames.append((frame, frame_num, ts))
                
                print(f"   🔧 [DEBUG] 窗口内收集到帧数: {len(clip_frames)} 帧")
                
                if len(clip_frames) < 30:  # 至少需要1秒
                    print(f"   ⚠️ 帧不足，无法扩展视频 ({len(clip_frames)} 帧). Buffer Range: {buffer_start_ts:.1f}-{buffer_end_ts:.1f}, Target: {original_timestamp - before_s:.1f}-{original_timestamp + after_s:.1f}")
                    return
            
            # 生成新视频路径
            video_filename = f"{moment_id}.mp4"
            video_path = self.moments_dir / video_filename
            
            # 计算帧率和视频时长
            if len(clip_frames) >= 2:
                time_span = clip_frames[-1][2] - clip_frames[0][2]
                actual_fps = len(clip_frames) / time_span if time_span > 0 else 30
                # 不限制最小FPS，保持真实时间跨度
                actual_fps = min(max(actual_fps, 5), 60)  # 最小5fps，保持30秒视频完整
                print(f"   🔧 [DEBUG] 实际时间跨度: {time_span:.2f}秒")
                print(f"   🔧 [DEBUG] 计算FPS: {actual_fps:.1f}")
                # 使用实际时间跨度作为视频时长，而不是计算值
                video_duration = time_span
            else:
                actual_fps = 30
                video_duration = len(clip_frames) / actual_fps
            
            print(f"   🔧 [DEBUG] 视频时长: {video_duration:.2f}秒 ({len(clip_frames)}帧 @ {actual_fps:.1f}fps)")
            
            # 获取帧尺寸
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
                # 回退到 OpenCV
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                writer = cv2.VideoWriter(str(video_path), fourcc, actual_fps, (w, h))
                for frame, _, _ in clip_frames:
                    writer.write(frame)
                writer.release()
            
            # 更新 moment 的视频信息并获取frame_number
            moment_frame_number = None
            for m in self.moments:
                if m.id == moment_id:
                    m.video_path = str(video_path)
                    m.video_duration = video_duration
                    moment_frame_number = m.frame_number
                    break
            
            self._save_moments()
            print(f"   ✅ 完整视频已生成: {video_duration:.1f}秒 (前{before_s:.0f}秒 + 后{after_s:.0f}秒)")
            
            # 🔊 为完整视频添加音频，并在完成后触发语音转文字+AI分析
            if moment_frame_number is not None:
                print(f"   🎤 为完整视频添加音频...")
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
            print(f"   ❌ 扩展视频失败: {e}")
            import traceback
            traceback.print_exc()
    
    # ============================================================
    # 🤖 AI 自动识别 (Smart Mirror)
    # ============================================================
    
    def update_frame(self, frame, frame_number: int, 
                    person_count: int = 0, track_ids: List[int] = None):
        """
        每帧调用, 用于 AI 分析缓冲
        
        Args:
            frame: 当前帧
            frame_number: 帧号
            person_count: 人数
            track_ids: 追踪ID
        """
        self.frame_count = frame_number
        current_time = time.time()
        
        # 检查是否需要进行 AI 分析 (每3.5分钟)
        if current_time - self.last_ai_analysis_time >= self.ai_interval_seconds:
            if person_count > 0:  # 只在有人时分析
                # ⚠️ 关键：先更新时间戳再触发分析，确保切片之间无遗漏
                # 即使处理耗时30秒，下一次也是从本次的210秒后触发，而非处理完成后的210秒
                self.last_ai_analysis_time = current_time
                # 异步进行 AI 分析
                self._trigger_ai_analysis(frame.copy(), frame_number, person_count, track_ids or [])
    
    def _trigger_ai_analysis(self, frame, frame_number: int, 
                             person_count: int, track_ids: List[int]):
        """触发 AI 分析 (异步)"""
        if not self.qwen_available:
            return
        
        # 在后台线程执行分析
        thread = threading.Thread(
            target=self._analyze_frame_with_ai,
            args=(frame, frame_number, person_count, track_ids),
            daemon=True
        )
        thread.start()
    
    def _trigger_ai_analysis_for_moment(self, frame, moment_id: str, transcript: str = ""):
        """触发对用户标记关键时刻的 AI 分析 (异步，包含语音)"""
        if not self.qwen_available:
            return
        
        # 在后台线程执行分析
        thread = threading.Thread(
            target=self._analyze_moment_with_ai,
            args=(frame, moment_id, transcript),
            daemon=True
        )
        thread.start()
    
    def _analyze_frame_with_ai(self, frame, frame_number: int,
                               person_count: int, track_ids: List[int]):
        """
        使用 Qwen-VL 分析帧 (纯视觉)
        
        基于编码框架识别协作学习行为
        """
        import cv2
        
        try:
            # 将帧编码为 base64
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            image_base64 = base64.b64encode(buffer).decode('utf-8')

            prompt = """你是一位协作学习研究专家。分析这张协作学习场景的图片。

请根据以下完整编码框架识别行为：

⚠️ 关键原则：
1. 只有当确实观察到【明显的协作互动】（如讨论、手指屏幕、共同操作、眼神交流）时，才标记为 is_key_moment: true。
2. 如果画面只是大家各自看电脑、玩手机、发呆，或者没有人，请直接返回 "is_key_moment": false。不要强行套用以下分类！

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
- Act: [R0]实质协助, [R1]赞美评价, [R1]集体自豪

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
- Act: [R0]直接任务协助, [R1]积极参与, [R3]对称贡献

【Soc-Insp 激发/共享】
- Engage: [R1]印证例子, [R2]丰富环境
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

【Und-Aha 顿悟/突破】⭐关键
- Engage: [R3]真实基石, [R3]洞察力生成
- Investigate: [R3]发现时刻"I find it!"⭐, [R3]可改进思想
- Act: [R3]新的综合⭐, [R3]应用新知, [R3]元认知改变⭐

【Und-Strive 深思/内化】
- Engage: [R1]认知困惑, [R2]精神生活
- Investigate: [R2]个人思考, [R2]检查实践, [R2]识别问题
- Act: [R2]反向反馈, [R2]认知图式测试, [R2]隐含性决策

=================================================================
反思层级: R0(基础) / R1(初步) / R2(深度) / R3(高阶突破)
阶段: Engage(定义) / Investigate(学习) / Act(制作)
=================================================================

请以JSON格式返回:
{
    "is_key_moment": true/false,
    "importance": 0.0-1.0,
    "reflection_level": "R0|R1|R2|R3",
    "phase": "Engage|Investigate|Act",
    "dimension": "Engagement|Initiative|Social|Understanding",
    "behavior_code": "如 Eng-Flow",
    "specific_behavior": "如 [R2]论证推理",
    "description": "简短描述正在发生什么",
    "observable_behaviors": ["可观察行为1"],
    "emotions": ["情绪状态"],
    "tags": ["标签1"]
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
            # 移除可能的 markdown 代码块标记
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
            
            result = json.loads(result_text)
            
            # 如果是关键时刻，记录（阈值0.3，提高灵敏度）
            if result.get("is_key_moment", False) and result.get("importance", 0) > 0.3:
                self._record_ai_moment(
                    frame=frame,
                    frame_number=frame_number,
                    person_count=person_count,
                    track_ids=track_ids,
                    ai_result=result
                )
            else:
                print(f"🤖 AI 分析 (帧 {frame_number}): 非关键时刻 (重要性: {result.get('importance', 0):.2f})")
                
        except Exception as e:
            print(f"⚠️ AI 分析失败: {e}")
    
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
        description = ai_result.get("description", "AI识别的关键时刻")
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
            clip_duration_before=float(KEY_MOMENT_BEFORE_SECONDS),  # 15秒
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
                print(f"   ⏰ [AI视频延迟] 线程开始 (moment_id={mid}), 等待 {KEY_MOMENT_AFTER_SECONDS:.0f} 秒...")
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
        
        print(f"🤖 AI 识别关键时刻: {time_str}")
        print(f"   📝 {description[:60]}...")
        print(f"   🏷️ 标签: {', '.join(tags[:3])}")
        print(f"   ⭐ 重要性: {importance:.2f}")
        print(f"   🎬 视频 (前{KEY_MOMENT_BEFORE_SECONDS:.0f}秒): {video_duration:.1f}秒")
        print(f"   ⏳ {KEY_MOMENT_AFTER_SECONDS:.0f}秒后将生成完整视频并进行AI分析...")
    
    def _process_video_with_multimodal_analysis(self, moment_id: str, video_path: str, frame=None):
        """从完整视频中提取音频并进行语音转文字，然后进行多模态AI分析
        
        Args:
            moment_id: 关键时刻ID
            video_path: 含音频的完整视频路径
            frame: 关键帧图像
        """
        from pathlib import Path
        import subprocess

        def _ai_step(step: int, total: int, msg: str):
            # 终端精简但“每一步都要有”——统一成单行步骤输出
            print(f"   🧩 [AI处理] {step}/{total} {msg}")
        
        try:
            total_steps = 9
            # 先写入“处理中”占位，避免前端长时间显示 No AI analysis content
            with self._moments_lock:
                for m in self.moments:
                    if m.id == moment_id:
                        if not (m.ai_description or "").strip() and not (m.analysis or "").strip():
                            m.ai_description = "AI处理中…"
                            self._save_moments()
                        break

            _ai_step(1, total_steps, "准备/占位")

            # 读取上下文（可能包含 after 秒补齐的窗口转写）
            _ai_step(2, total_steps, "读取 context.txt")
            context_text = ""
            context_transcript = ""
            try:
                ctx_path = Path(video_path).parent / f"{moment_id}_context.txt"
                if ctx_path.exists():
                    context_text = ctx_path.read_text(encoding="utf-8")
                    marker = "=== transcript_context ==="
                    if marker in context_text:
                        # 取最后一次写入的 transcript_context，避免重复追加导致解析到旧内容
                        context_transcript = context_text.rsplit(marker, 1)[1].strip()
                    print(f"   🤖 [AI处理] context.txt 找到，上下文转写: {len(context_transcript)} 字")
                else:
                    print(f"   🤖 [AI处理] {moment_id}_context.txt 不存在 (仅使用全局KB)")

                # GLOBAL KB: 读取全局 context.txt (知识库)
                # 路径: integrated_data/../context.txt -> 1215zzh/context.txt
                try:
                    global_kb_path = self.data_dir.parent / "context.txt"
                    if global_kb_path.exists():
                        kb_content = global_kb_path.read_text(encoding="utf-8").strip()
                        if kb_content:
                            print(f"   📚 [AI处理] 加载全局知识库 (context.txt): {len(kb_content)} 字")
                            # 将 KB 拼接到 context_text 前面或后面
                            context_text = f"【全局知识库/背景信息】\n{kb_content}\n\n" + context_text
                    else:
                        print(f"   ⚠️ [AI处理] 全局知识库 context.txt 不存在: {global_kb_path}")
                except Exception as e:
                    print(f"   ⚠️ [AI处理] 读取全局KB失败: {e}")
            except Exception as e:
                print(f"   🤖 [AI处理] 读取 context.txt 失败: {e}")
                context_text = ""
                context_transcript = ""

            # 默认禁用“优先使用上下文转写”，改为强制对“完整切片视频”做 ASR。
            # 原因：上下文转写只包含按键前的历史，而视频切片包含按键后的“未来”15秒。只有重做 ASR 才能拿到这部分内容的文字。
            prefer_ctx_asr = os.environ.get("KEY_MOMENT_PREFER_CONTEXT_TRANSCRIPT", "0").strip().lower() in {"1", "true", "yes"}
            _ai_step(3, total_steps, f"判定转写来源: prefer_ctx_asr={int(prefer_ctx_asr)} ctx_len={len((context_transcript or '').strip())}")
            if prefer_ctx_asr and context_transcript:
                _ai_step(4, total_steps, "跳过提取音频/二次ASR(直接用上下文转写)")
                # 更新 moment.transcript（通常更完整）
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
                        _ai_step(9, total_steps, "跳过AI分析(无有效语音)")
                        self._mark_moment_no_audio(moment_id, "上下文转写为空/无有效语音")
                    else:
                        _ai_step(9, total_steps, "调用视觉/多模态AI分析")
                        self._analyze_moment_with_ai(frame, moment_id, context_transcript, context_text=context_text)
                else:
                    _ai_step(9, total_steps, "跳过AI分析(无frame)")

                # 补齐“每一步都要有”的输出：中间步骤标记为跳过
                _ai_step(5, total_steps, "跳过(已用上下文转写)")
                _ai_step(6, total_steps, "跳过(已用上下文转写)")
                _ai_step(7, total_steps, "跳过(已用上下文转写)")
                _ai_step(8, total_steps, "跳过(已用上下文转写)")
                return

            # 限流：避免多个关键时刻并行把系统拖慢（尤其 FireRedASR/LLM 都会吃资源）
            _ai_step(4, total_steps, "等待重任务信号量")
            with self._heavy_job_sema:
                _ai_step(5, total_steps, "提取音频(ffmpeg)")
                import subprocess
                from pathlib import Path
            
                # 1. 提取音频用于语音转文字
                audio_for_asr_path = Path(video_path).parent / f"{moment_id}_asr.wav"
            
                cmd_extract_audio = [
                    'ffmpeg', '-y', '-i', str(video_path),
                    '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1',
                    str(audio_for_asr_path)
                ]
            
                print(f"   🎵 提取音频用于语音识别...")
                result = subprocess.run(cmd_extract_audio, capture_output=True, timeout=30)
                _ai_step(6, total_steps, f"ffmpeg rc={result.returncode} wav_exists={int(audio_for_asr_path.exists())}")
            
                if result.returncode != 0 or not audio_for_asr_path.exists():
                    print(f"   ⚠️ 音频提取失败，跳过语音转文字")
                    self._mark_moment_no_audio(moment_id, "Video segment has no audio track/audio extraction failed")
                    return
            
                # 2. 调用ASR进行语音转文字
                _ai_step(7, total_steps, "ASR转写")
                transcript = self._transcribe_audio(audio_for_asr_path)
            
                # 清理临时音频文件
                try:
                    audio_for_asr_path.unlink()
                except:
                    pass
            
            # 3. 更新moment的transcript字段
            _ai_step(8, total_steps, f"回写moment transcript(asr_len={len((transcript or '').strip())})")
            for moment in self.moments:
                if moment.id == moment_id:
                    moment.transcript = transcript
                    moment.asr_provider = (self._last_asr_meta.get("provider") or "")
                    moment.asr_model = (self._last_asr_meta.get("model") or "")
                    moment.asr_model_dir = (self._last_asr_meta.get("model_dir") or "")
                    print(f"   ✅ 语音转文字完成: {len(transcript)} 字")
                    # if transcript:
                    #     print(f"   📝 内容: {transcript[:80]}...")
                    break
            
            self._save_moments()

            if self._transcript_is_missing(transcript):
                _ai_step(9, total_steps, "跳过AI分析(ASR为空/无有效语音)")
                self._mark_moment_no_audio(moment_id, "ASR is empty/no valid speech")
                return
            
            # 4. 进行多模态AI分析 (视频+语音)
            _ai_step(9, total_steps, "调用视觉/多模态AI分析")
            if frame is not None:
                self._analyze_moment_with_ai(frame, moment_id, transcript, context_text=context_text)
            else:
                _ai_step(9, total_steps, "跳过AI分析(无frame)")
            
        except Exception as e:
            print(f"   ⚠️ 多模态处理失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _transcribe_audio(self, audio_path: Path) -> str:
        """
        使用DashScope进行音频转文字 (参考实时ASR的成功实现)
        
        Args:
            audio_path: 音频文件路径 (WAV格式, 16kHz, 单声道)
            
        Returns:
            转写文本
        """
        try:
            # ============================================================
            # ASR 后端选择：支持本地 FireRedASR（离线）或 DashScope (云端)
            # 用户偏好：Qwen (DashScope)
            # ============================================================
            # 默认改为 dashscope 以响应用户请求
            asr_provider = os.environ.get("ASR_PROVIDER", "dashscope").strip().lower()

            if asr_provider == "fireredasr":
                # (Keep FireRedASR logic but it won't be default)
                model_dir = os.environ.get("FIREREDASR_MODEL_DIR", "pretrained_models/FireRedASR-AED-L")
                asr_type = os.environ.get("FIREREDASR_ASR_TYPE", "aed").strip().lower()
                use_gpu = os.environ.get("FIREREDASR_USE_GPU", "0").strip() in {"1", "true", "yes"}
                beam_size = int(os.environ.get("FIREREDASR_BEAM_SIZE", "3"))
                nbest = int(os.environ.get("FIREREDASR_NBEST", "1"))

                # 先记录元信息（即便后续失败/回退，也能看出本来想用什么）
                self._last_asr_meta = {
                    "provider": "fireredasr",
                    "model": f"{asr_type}:{Path(model_dir).name}",
                    "model_dir": str(model_dir),
                }

                if not Path(model_dir).exists():
                    print(f"   ⚠️ FireRedASR 模型目录不存在: {model_dir}")
                    # 允许回退到 DashScope
                else:
                    try:
                        # 关键：复用模型，避免每次 from_pretrained 导致长时间卡顿/高延迟
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
                        print(f"   ⚠️ FireRedASR 转写失败(将回退DashScope): {e}")
                # FireRedASR 未产出结果时，继续走 DashScope 分支

            # DashScope / Qwen 分支
            self._last_asr_meta = {
                "provider": "dashscope",
                "model": "qwen-audio-turbo",
                "model_dir": "",
            }

            # 检查DashScope可用性
            if not self.api_key:
                print("   ⚠️ DashScope API Key未配置")
                return ""
            
            # 方法1: 使用 Recognition API (同步调用) - 参考 realtime_asr.py
            try:
                import dashscope
                from dashscope.audio.asr import Recognition
                
                dashscope.api_key = self.api_key
                
                print(f"   🎤 正在进行语音转文字 (文件大小: {audio_path.stat().st_size} bytes, DashScope)...")
                
                # ASR模型优先级列表（只使用已确认可用的模型）
                models_to_try = [
                    'paraformer-realtime-v2',      # 实时ASR模型（主力）
                    'paraformer-realtime-8k-v2',   # 8k采样率版本（备用）
                ]
                
                result = None
                last_error = None
                successful_model = None
                
                for model_name in models_to_try:
                    try:
                        print(f"   🔄 尝试模型: {model_name}")
                        
                        # 创建识别对象 (与 realtime_asr.py 保持一致)
                        recognition = Recognition(
                            model=model_name,
                            format='wav',       # 文件格式
                            sample_rate=16000,  # 采样率
                            callback=None       # 同步调用不需要回调
                        )
                        
                        # 同步调用,直接传入文件路径
                        result = recognition.call(str(audio_path))
                        
                        # 检查结果
                        if result and hasattr(result, 'output') and result.output:
                            successful_model = model_name
                            print(f"   ✅ 模型 {model_name} 识别成功")
                            break
                        elif result and hasattr(result, 'status_code'):
                            if result.status_code == 200:
                                # 状态成功但结果为空，尝试下一个模型
                                print(f"   ⚠️ 模型 {model_name} 返回成功但结果为空，尝试下一个模型")
                                last_error = f"模型 {model_name} 无识别结果"
                                continue  # 继续尝试下一个模型
                            else:
                                error_msg = getattr(result, 'message', f'Status {result.status_code}')
                                last_error = error_msg
                                print(f"   ⚠️ 模型 {model_name} 失败: {error_msg}")
                                continue
                        else:
                            last_error = f"模型 {model_name} 返回空结果"
                            print(f"   ⚠️ {last_error}")
                            continue
                            
                    except Exception as e:
                        last_error = str(e)
                        print(f"   ⚠️ 模型 {model_name} 异常: {e}")
                        continue

                if successful_model:
                    self._last_asr_meta = {
                        "provider": "dashscope",
                        "model": str(successful_model),
                        "model_dir": "",
                    }
                
                # 提取转写文本
                transcript_parts = []
                if result and hasattr(result, 'output') and result.output:
                    output = result.output
                    
                    # 🔍 调试输出结构
                    print(f"   🔍 [DEBUG] Output type: {type(output)}")
                    if isinstance(output, dict):
                        print(f"   🔍 [DEBUG] Output keys: {list(output.keys())}")
                        print(f"   🔍 [DEBUG] Output content: {output}")
                    elif hasattr(output, '__dict__'):
                        print(f"   🔍 [DEBUG] Output attrs: {vars(output)}")
                    else:
                        print(f"   🔍 [DEBUG] Output: {output}")
                    
                    # 处理不同的输出格式
                    if isinstance(output, dict):
                        # 格式1: sentence (列表形式 - paraformer-realtime-v2)
                        if 'sentence' in output:
                            sentence = output['sentence']
                            # sentence 是列表,包含多个句子对象
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
                    
                    # 如果是对象,尝试对象属性访问
                    elif hasattr(output, 'sentence'):
                        sentence = getattr(output, 'sentence')
                        if hasattr(sentence, 'text'):
                            text = getattr(sentence, 'text', '').strip()
                            if text:
                                transcript_parts.append(text)
                
                transcript = ' '.join(transcript_parts).strip()
                
                if transcript:
                    print(f"   ✅ 语音转文字成功: {len(transcript)} 字")
                    # print(f"   📝 识别内容: {transcript[:100]}{'...' if len(transcript) > 100 else ''}")
                    return transcript
                else:
                    print(f"   ⚠️ Recognition API 返回空结果")
                    if last_error:
                        print(f"   📋 诊断: {last_error}")
                    
            except ImportError as e:
                print(f"   ⚠️ dashscope.audio.asr 未安装: {e}")
            except Exception as e:
                print(f"   ⚠️ 语音转文字异常: {e}")
                import traceback
                traceback.print_exc()
            
            
            # 所有方法都失败了
            print(f"   ⚠️ 语音转文字所有方法都失败")
            print(f"   💡 建议: 检查 DashScope API 密钥权限或模型可用性")
            
            # 🎯 回退方案：使用实时ASR的历史转写（如果存在）
            if context_transcript and len(context_transcript.strip()) > 0:
                print(f"   ✅ 使用上下文转写作为回退方案 ({len(context_transcript)}字)")
                return context_transcript
            
            print(f"   🔄 系统将使用纯视觉 AI 分析")
            return ""
        
        except Exception as e:
            print(f"   ⚠️ 语音转文字异常: {e}")
            import traceback
            traceback.print_exc()
            return ""
    
    def _analyze_moment_with_ai(self, frame, moment_id: str, transcript: str = "", context_text: str = ""):
        """
        为用户标记的关键时刻生成 AI 分析 (多模态)
        
        Args:
            frame: 帧图像
            moment_id: 关键时刻ID
            transcript: 语音转文字内容
        """
        import cv2
        
        try:
            # 将帧编码为 base64
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            image_base64 = base64.b64encode(buffer).decode('utf-8')

            # 从 moment 里取按键原因
            user_note = ""
            for m in self.moments:
                if m.id == moment_id:
                    user_note = (m.user_note or "")
                    break

            # 关键：要求“基于证据，不确定就说不确定”，并稍微口语幽默
            transcript_clean = (transcript or "").strip()

            # 关键：只取 context.txt 里最后一次写入的 transcript_context（也就是“窗口转写”）
            context_excerpt = (context_text or "").strip()
            marker = "=== transcript_context ==="
            if marker in context_excerpt:
                context_excerpt = context_excerpt.rsplit(marker, 1)[1].strip()
            # 截断时保留尾部（更靠近按键时刻/窗口），避免截到旧内容
            if len(context_excerpt) > 3500:
                context_excerpt = "[...context truncated...]\n" + context_excerpt[-3500:]

            prompt = f"""You are an "intelligent mirror" that faithfully records what happens at a Maker Marathon/Hackathon event.

Scene description: This is a Maker Marathon / Hackathon venue (making prototypes, writing code, debugging, discussing solutions).

Core principles - Mirror Observation Method:
1) **Faithful reflection**: Objectively describe what you see in the frame and what you hear from ASR, without subjective evaluation.
2) **Concrete and visible**: Describe specific actions, dialogues, expressions, objects, not abstract concepts (e.g., "deep discussion" → "two people pointing at screen and talking").
3) **Report what you see**: Write how many people you see, quote the dialogue you hear, describe the actions you observe.
4) **Full context positioning**: ⚠️ You MUST understand the current moment's position in the overall activity flow based on the complete transcript in [Historical Context], explaining what happened before, what is happening now, and the significance of this moment.
5) **Admit uncertainty**: If the image is blurry, ASR is empty, or you cannot determine, write "The frame does not show clear activity" or "No voice content".
6) ⚠️ If [This Segment ASR] is "(no voice)" AND the frame shows no obvious activity, write "No obvious activity in frame", do NOT fabricate content.

[Button Reason/Note] {user_note or "(none)"}

[Historical Context (may be truncated)]
{context_excerpt or "(none)"}

[This Segment ASR (may have noise)]
{transcript_clean or "(no voice)"}

⚠️ **Priority Principle**:
- Voice content > Frame content (voice is the core activity record)
- If ASR has content, you MUST describe with voice as the main line, frame as supplement
- Only describe frame purely if ASR is empty

Output format strictly as follows:
Label: <10-14 words, must include: number of people + specific action/event (prioritize based on voice content) + key object; may include 0-1 related emoji>
Detailed Description: <2-3 sentences, **prioritize describing voice content**: ①If there is ASR, first quote the dialogue verbatim (Chinese or English) ②Then supplement with frame: number of people, layout, actions ③Visible objects; use short sentences; total ≤120 words; prohibited words: "lively", "deep", "sparks" and other abstract terms>
Analysis Framework Label: <If the dialogue/behavior matches the collaborative learning coding framework, annotate the corresponding label, such as "[R2] Argumentation", "Eng-Flow", "Soc-Help Mutual Aid"; if no obvious framework behavior, write "No framework label">
Context Positioning: <1-2 sentences, **based on the complete transcript in [Historical Context]**, explain: ①What happened before this moment ②Current stage in the overall activity flow ③The role/significance of this moment; write "No historical context" if history is empty>
Evidence Excerpt: <1-3 items, quote ASR or historical context verbatim, preserve timestamps; write "None" if unavailable>
"""


            ai_analysis = self._run_vision_llm(
                image_base64=image_base64,
                prompt=prompt,
                model_override=self.vision_model,
                temperature=0.7,
                max_tokens=900
            )

            # 可选：用更强的文本模型（默认 qwen3-max）做二次整理，提升“贴纸标签/详细解说/证据摘录”的一致性
            use_text_postprocess = os.environ.get("KEY_MOMENT_TEXT_POSTPROCESS", "1").strip().lower() in {"1", "true", "yes"}
            final_text = ai_analysis
            if use_text_postprocess:
                refine_prompt = f"""You are an intelligent mirror, objectively organizing the visual model's output.

Scene description: This is a Maker Marathon / Hackathon venue (making prototypes, writing code, debugging, discussing solutions).

You will receive three inputs:
1) Visual model's interpretation of the frame (may be incomplete/inaccurate)
2) Historical context (with timestamps, may be truncated)
3) This segment's ASR text (may have noise)

Hard requirements:
- You can ONLY use text from [Historical Context] and [ASR] as "Evidence Excerpt"; excerpts must be verbatim with timestamps.
- For the frame, only describe what you "can confirm from the visual interpretation"; if uncertain, write "Cannot determine".
- Output in English, objective description style: faithfully reflect the frame and dialogue, do not add subjective evaluation.
- Describe specific visible content, do not use vague abstract vocabulary.

[Button Reason/Note] {user_note or "(none)"}

[Visual Interpretation (from model, may have errors)]
{(ai_analysis or "").strip() or "(none)"}

[Historical Context (may be truncated)]
{context_excerpt or "(none)"}

[This Segment ASR (may have noise)]
{transcript_clean or "(no voice/not recognized)"}

⚠️ **Priority Principle**:
- Voice content > Frame content (voice is the core activity record)
- If ASR has content, you MUST describe with voice as the main line
- Only describe frame if ASR is empty

Output format strictly as follows (请用中文回复):
标签: <10-14字，必须基于语音内容或画面动作；可包含0-1个表情符号>
卡片摘要: <**必须20-30字**，生动有趣，像新闻标题一样吸引眼球！必须包含1-2个表情符号🎯。禁止以"团队成员"、"参与者"、"发言人"开头❌；用动词或场景开头✅。好例子："机器狗终于跑起来了！凌晨4:30的突破时刻🤖⚡️"，"从虚拟游戏到实际创作，这次认知飞跃太史诗了🧠🎮"；坏例子："团队成员讨论技术问题"（太无聊❌）>
详细描述: <**必须3-5句完整句子**，总字数**必须达到100-150字**。优先详细引用ASR对话（带引号），然后描述画面：具体人数、位置、动作、表情、物体。用连贯的叙事风格，就像给盲人描述场景一样。禁止：抽象词汇>
分析框架标签: <如果对话/行为符合协作学习编码框架（如[R2]论证推理、Eng-Flow、Soc-Help等），标注相应标签；无明显框架行为则写"无框架标签">
上下文定位: <1-2句话，**基于[历史上下文]中的完整转写**，解释：①该时刻之前发生了什么②当前在整体活动流程中的阶段③该时刻的角色/意义；如无历史则写"无历史上下文">
证据摘录: <1-3条，逐字引用ASR或历史上下文，保留时间戳；无可用则写"无">
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
                    print(f"⚠️ 二次文本整理失败，回退到视觉输出: {e}")
                    final_text = ai_analysis
            
            # 更新关键时刻的 AI 分析结果
            for moment in self.moments:
                if moment.id == moment_id:
                    tagline, body = self._extract_tagline(final_text)
                    detail_desc = self._extract_detail_description(body)
                    card_summary = self._extract_card_summary(body)  # 提取卡片摘要
                    framework_tags = self._extract_framework_tags(body)
                    
                    # 优先使用card_summary（20-25字）显示在卡片上
                    #  回退到detail_desc或tagline
                    new_description = (card_summary or "").strip() or (detail_desc or "").strip() or (tagline or "").strip()

                    moment.ai_tagline = (tagline or "").strip()
            
                    moment.ai_framework_tags = framework_tags
                    moment.analysis = body

                    # 防止“降级”：不要用很短的新文本覆盖已有的高信息密度描述
                    existing_desc = (moment.ai_description or "").strip()
                    existing_is_placeholder = existing_desc in {"", "AI处理中…", "AI分析失败"}
                    has_card_summary = bool((card_summary or "").strip())
                    if has_card_summary or existing_is_placeholder:
                        # 有card_summary或是占位符：直接更新
                        moment.ai_description = new_description
                    else:
                        # 过短的新文本通常是“标签截断/抽取失败”，不覆盖
                        if len(new_description) < 12:
                            pass
                        # 新文本显著更短且没有明显增量时，不覆盖
                        elif len(new_description) + 10 < len(existing_desc):
                            pass
                        else:
                            moment.ai_description = new_description

                    moment.llm_provider = self.llm_provider
                    moment.llm_model = (
                        f"vision={self.vision_model};text={self.text_model}"
                        if use_text_postprocess else self.vision_model
                    )
                    print(f"✅ AI 分析完成: {moment_id}")
                    if (moment.ai_tagline or "").strip():
                        print(f"   🏷️ 标签: {moment.ai_tagline}")
                    if framework_tags:
                        print(f"   🔖 框架标签: {framework_tags}")
                    break
            
            # 保存更新
            self._save_moments()
            
        except Exception as e:
            print(f"⚠️ AI 分析失败: {e}")
            import traceback
            traceback.print_exc()

            # 回写一个可见的失败信息，避免前端显示空白
            for moment in self.moments:
                if moment.id == moment_id:
                    if not (moment.ai_description or "").strip():
                        moment.ai_description = "AI Analysis Failed"
                    if not (moment.analysis or "").strip():
                        moment.analysis = "[AI Analysis Failed] No summary generated (model/network/timeout)."
                    moment.llm_provider = self.llm_provider
                    moment.llm_model = moment.llm_model or (self.vision_model or "")
                    break
            try:
                self._save_moments()
            except Exception:
                pass
    
    # ============================================================
    # 🎤📷 多模态分析 (音频 + 图像联合)
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
                m.ai_tagline = "🎧 No Audio"
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
        """多模态联合分析（音频窗口转写 + 单帧图像）。

        Args:
            frame: 当前帧图像
            frame_number: 帧号
            transcript_text: 与该帧对齐的短窗口转写文本（通常为±10秒窗口）
            person_count: 当前人数
            track_ids: 统一后的 person_id 列表
            timestamp: 该帧对应的 epoch 时间戳（用于与转写/视频片段对齐）
            video_frames: 可选的视频帧窗口（来自 5 分钟切片缓冲），用于生成与该时刻匹配的视频片段

        Returns:
            LLM 分析结果 dict（仅当命中关键时刻并成功记录时返回），否则 None
        """
        if not self.qwen_available:
            print("⚠️ LLM 不可用，跳过多模态分析")
            return None

        # 默认：无有效语音转写时不做“关键时刻判定/落库”，避免纯视觉在证据不足时乱说。
        # 若确实需要图像-only 兜底：MULTIMODAL_REQUIRE_TRANSCRIPT=0 且 ALLOW_IMAGE_ONLY_KEY_MOMENTS=1。
        require_transcript = (os.environ.get("MULTIMODAL_REQUIRE_TRANSCRIPT", "1") or "1").strip().lower() in {
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
            # 将帧编码为 base64
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            image_base64 = base64.b64encode(buffer).decode('utf-8')

            track_ids = track_ids or []

            prompt = f"""You are a collaborative learning research expert using a professional behavior coding framework to analyze collaborative scenes.
            
Scene Description: This is a "Maker Marathon / Hackathon" site (prototyping, coding, debugging, discussing solutions), but we want the card text to be rhythmic and distinctive like a sports commentary.

You will receive: A video frame + a short window of speech transcript aligned with that frame (usually ±10 seconds).

【Judgment Principles (Very Important)】
1) Do not force a search: If evidence is insufficient/unclear/just normal process dialogue, please return is_key_moment=false.
2) Key moments should reflect a clear "cognitive/collaborative transition", prioritizing R2/R3.
    But in "lecture/viewpoint output/structured explanation" scenes, if there are:
    - Clear concept definitions/framework proposals (Und-Exp)
    - Structured summaries/bullet points (e.g., "Three points/First, Second, Third")
    - Key questions driving thinking (Init-Feed/Und-Exp)
    These can also be judged as key (importance 0.50–0.75, depending on evidence strength).
3) Importance calibration must be conservative:
    - 0.00–0.39: Ordinary interaction/repeated info/process
    - 0.40–0.59: Valuable but not "key" (usually should be is_key_moment=false)
    - 0.60–0.79: Key (clear evidence, retellable)
    - 0.80–1.00: Strong Key (obvious breakthrough/turn/consensus/method change)
4) Output must be short: description/meeting_note controlled within 1-2 sentences, high information density, retellable.
5) Must provide card_summary: A short summary for the card, **strictly 20-30 words**, "Sports Commentary Style + Hackathon Context", more colloquial and fun; can include 2-3 light emojis (e.g. 🏁🛠️⚡️🎯🤖💡), but nothing vulgar.

【Visual Info】 Scene in the frame
【Audio Content】 Window dialogue transcript aligned with the frame:
"{transcript_text}"

Please identify according to the following complete coding framework:

=================================================================
Dimension 1: Engagement (Eng) - Time investment, emotional state, flow experience
=================================================================

【Eng-Flow Flow/Immersion】
Engage Phase:
- [R1] Exploratory Confusion: [EVT] Expressing curiosity/confusion "I wonder..."
- [R1] Authenticity Confirmation: [KB] Real problems derived from efforts to understand the world
Investigate Phase:
- [R1] Problem Naming: [DT] Define - Problem reframing/insight generation; [Co-ref] Naming - Identifying related problems
- [R1] Info Supply: [EVT] Informative - Providing info related to topic
Act Phase:
- [R0] Concrete Action: [DT] Prototype - Sketching/physical/low-fi models; [Co-ref] Action - Explaining preliminary solutions
- [R1] Improvement Intent: [KB] Knowledge building discourse - Discourse aimed at improving ideas

【Eng-Emo Emotion/Atmosphere】
Engage Phase:
- [R0] Emotional Connection: [SSBC] Emotional support - Expressing fondness/ice-breaking "Stresses the closeness of the relationship"
- [R0] Respect Confirmation: [SSBC] Respect support - Affirming/confirming views "Validation: Expresses agreement"
- [R1] Mutual Corroboration: [IAM] PhI/C - Corroborating examples
Investigate Phase:
- [R0] Resource Access: [SSBC] Network support - Accessing people/resources
- [R0] Physical Company: [SSBC] Company - "Spend time with the recipient"
- [R1] Inviting Thought: [EVT] Inviting - "What do you think?" - "Inviting others to think together"
Act Phase:
- [R0] Substantial Assistance: [SSBC] Substantial support - Direct task help/lending items
- [R1] Praise Evaluation: [SSBC] Praise - "Says positive things about abilities"
- [R1] Collective Pride: [KB] Knowledge democratization - Pride in group progress

【Eng-Strug Struggle/Persistence】
Engage Phase:
- [R1] Difficulty ID: [IAM] PhI/E - "Definition, description, or identification of a problem"
- [R1] Handling Difficulties: [KB] Real problems - Dealing with problems significant to self
Investigate Phase:
- [R1] Disagreement ID: [IAM] PhII/A - "Identifying and stating areas of disagreement"
- [R1] Setting Limits: [Co-ref] Limits - Setting norms/identifying constraints
Act Phase:
- [R1] Potential Assessment: [Co-ref] Assessment - Judging potential/adaptability, including questioning/private thinking
- [R2] Hypothesis Verification: [DT] Test - Verifying assumptions/what doesn't work

=================================================================
Dimension 2: Initiative (Init) - Goal setting, feedback seeking, risk taking
=================================================================

【Init-Goal Goal/Plan】
Engage Phase:
- [R1] Goal Anchoring: [Co-ref] Determining goals - Determining priorities
- [R1] Plan Formulation: [KB] Epistemic agency - Setting goals and plans
- [R1] Clarifying Details: [IAM] PhI/D - Asking questions to clarify details
Investigate Phase:
- [R1] Role Assignment: [Co-ref] Determining roles/tasks - Assigning work
- [R1] Process Suggestion: [Co-ref] Proposing process - Suggesting action steps
- [R2] Cognitive Agency: [KB] Epistemic agency - Handling problems usually left to teachers
Act Phase:
- [R2] Ideation Divergence: [DT] Ideate - Quantity priority/deferring judgement
- [R2] Decision Stacking: [Co-ref] Making decisions - Stacking interests within team
- [R2] Compromise Statement: [IAM] PhIII/D - Proposing new statements reflecting compromise

【Init-Feed Feedback/Verification】
Engage Phase:
- [R1] Viewpoint Statement: [IAM] PhI/A - "A statement of observation or opinion"
- [R1] Understanding Ideas: [KB] Idea diversity - Understanding surrounding ideas
Investigate Phase:
- [R2] Reason Questioning: [Co-ref] Questioning/asking for reasons
- [R2] Clarifying Divergence: [IAM] PhII/B - Asking to clarify source of disagreement
- [R2] Comprehensive Analysis: [EVT] Analytical - Comprehensively evaluating others' understanding
Act Phase:
- [R2] Iterative Modification: [DT] Test - User feedback/iterative modification
- [R2] Fact Testing: [IAM] PhIV/A - Testing against accepted facts
- [R2] Experience Testing: [IAM] PhIV/C - Testing against personal experience

【Init-Risk Risk/Argument】
Engage Phase:
- [R2] Contrasting Ideas: [KB] Idea diversity - Including contrasting ideas
- [R2] Wild Ideas: [DT] Ideate - Wild ideas
Investigate Phase:
- [R2] Exploring Inconsistency: [IAM] PhII/A - Discovering and exploring inconsistency
- [R2] Argumentation: [EVT] Argumentative - "Expressing reasoning with analogies"
- [R2] Critical Challenge: [EVT] Critical - Challenging or playing devil's advocate
Act Phase:
- [R3] Rise Above: [KB] Rise Above - Beyond best practices/new synthesis
- [R2] Argument Weight: [IAM] PhIII/B - Negotiating relative weight of arguments
- [R3] Frame Reframing: [Co-ref] Frame/Reframing - Leading to new boundaries

=================================================================
Dimension 3: Social Scaffolding (Soc) - Mutual aid, inspiration, physical connection
=================================================================

【Soc-Ind Independent/Monologue】
- [R0] Monologue: [IAM] PhI/A Stating observation or opinion but not responding to others
- [R0] Parallel Study: [LDF] Focusing on material but no interaction
- [R0] Parallel Co-acting: [LDF] Physically together but no cognitive intersection

【Soc-Help Mutual Aid/Teaching】
Engage Phase:
- [R0] Relationship Confirmation: [SSBC] Relationship confirmation - Emphasizing bonds
- [R1] Advice: [SSBC] Informational support - "Offers ideas or suggests actions"
Investigate Phase:
- [R1] Blind Spot Removal: [SSBC] Teaching - Providing detailed facts/removing blind spots
- [R1] Info Provision: [Co-ref] Providing info - Giving info/external examples
- [R1] Literature Support: [IAM] PhII/C - Citing literature/data to support views
Act Phase:
- [R0] Direct Task: [SSBC] Substantial support - Direct task/indirect task
- [R1] Active Participation: [SSBC] Active participation - Participating in activities together for stress relief
- [R3] Symmetric Contribution: [KB] Symmetric knowledge advancement - Cross-team interaction contributing resources

【Soc-Insp Inspiration/Sharing】
Engage Phase:
- [R1] Corroborating Examples: [IAM] PhI/C - Mutually corroborating examples
- [R2] Enriching Environment: [KB] Idea diversity - Creating rich evolutionary environment
Investigate Phase:
- [R2] Data Support: [IAM] PhII/C - Citing literature/data to support views
- [R2] Authority Extension: [KB] Authoritative sources - Extending understanding beyond set materials
- [R2] Explanation Refinement: [EVT] Explanatory - Refining on basis of predecessors
Act Phase:
- [R3] Heuristic Discovery: [EVT] Heuristic "A ha!" - "Expressing discovery... directing others' attention"
- [R3] Integrated Viewpoint: [Co-ref] Proposing integrated viewpoint
- [R3] Integrating Metaphor: [IAM] PhIII/E - Proposing integrating metaphor or analogy

【Soc-Conn Connection/Synergy】
Engage Phase:
- [R0] Physical Presence: [SSBC] Company - Physical presence
- [R1] Shared Responsibility: [KB] Collective responsibility - Shared responsibility for advancing knowledge
Investigate Phase:
- [R1] Facilitating Understanding: [Co-ref] Facilitating understanding
- [R0] Peer Relationship: [SSBC] Peer relationship - Reminding that others support
Act Phase:
- [R3] Contributing Expertise: [KB] Symmetric knowledge advancement - Different members contributing expertise
- [R3] Co-construction: [IAM] PhIII/D - "Co-construction"
- [R2] Interest Stacking: [Co-ref] Internal stacking - Team interest stacking

=================================================================
Dimension 4: Understanding Development (Und) - Epiphany, explanation strategy, application
=================================================================

【Und-Exp Explanation/Deduction】
Engage Phase:
- [R1] Defining Problem: [IAM] PhI/E - Defining or describing problem
- [R1] Problem Naming: [Co-ref] Naming - Identifying related problems
Investigate Phase:
- [R1] Referencing Experience: [Co-ref] Reference past experience - Known elements
- [R2] Explanatory Connection: [EVT] Explanatory - Connection chain aimed at explaining clearly
- [R2] Citing Support: [IAM] PhII/C - Citing experience/literature support
Act Phase:
- [R2] Explaining Solution: [Co-ref] Proposing change suggestions - Explaining preliminary solution
- [R2] Negotiating Terminology: [IAM] PhIII/A - Negotiating terminology meaning
- [R2] Refining Viewpoint: [EVT] Explanatory - Elaborate ideas

【Und-Aha Epiphany/Breakthrough】 ⭐ Key ID
Engage Phase:
- [R3] Real Cornerstone: [KB] Real Ideas - Real cornerstone
- [R3] Insight: [DT] Insight generation
Investigate Phase:
- [R3] Discovery Moment: [EVT] Heuristic "I find it!" / Discovery ⭐ "Expressing discovery (A ha! moments)"
- [R3] Improvable: [KB] Improvable ideas - Ideas are improvable
Act Phase:
- [R3] New Synthesis: [KB] Rise Above - Achieving new synthesis ⭐
- [R3] Applying New Knowledge: [IAM] PhV/B - Applying new knowledge
- [R3] Metacognitive Change: [IAM] PhV/C - Change at metacognitive level ⭐ "Ways of thinking have changed"

【Und-Strive Deep Thinking/Internalization】
Engage Phase:
- [R1] Cognitive Confusion: [EVT] Exploratory - Cognitive confusion/Curiosity
- [R2] Mental Life: [KB] Pervasive knowledge building - Pervasive mental life
Investigate Phase:
- [R2] Personal Thinking: [Co-ref] Personal thinking - Private reflection
- [R2] Examining Practice: [EVT] Reflective - Examining past practice/understanding
- [R2] Identifying Problems: [KB] Embedded assessment - Identifying problems
Act Phase:
- [R2] Listening to Back-talk: [Co-ref] Reflection - Listening to situational "back-talk"
- [R2] Cognitive Schema Testing: [IAM] PhIV/B - Testing against existing cognitive schema
- [R2] Implicit Decision: [EVT] Implicit - Proposing decision based on insight

=================================================================
Theoretical Source Legend
=================================================================
[LDF]: Tinkering Learning Dimension  [Hack4CBL]: Time Phase
[IAM]: Interaction Analysis Model    [DT]: d.school Design Thinking
[EVT]: Valued Educational Talk       [KB]: Knowledge Building Principles
[Co-ref]: Co-reflective Practice     [SSBC]: Social Support Behavior Codes
R0-R3: Fleck & Fitzpatrick (2010) Reflection Hierarchy

=================================================================

Please analyze and return in JSON format (请用中文回复所有内容):
{{
    "is_key_moment": true/false,
    "importance": 0.0-1.0 (provide a precise score to 2 decimal places, e.g. 0.37, 0.52, avoid round numbers like 0.3, 0.5),
    "reflection_level": "R0|R1|R2|R3",
    "phase": "Engage|Investigate|Act",
    "primary_dimension": "Engagement|Initiative|Social|Understanding",
    "behavior_code": "L1 behavior code e.g. Eng-Flow/Eng-Emo/Init-Goal/Soc-Help/Und-Aha etc.",
    "specific_behavior": "具体子行为，如 [R2]论证推理/[R3]发现时刻/[R1]问题命名等",
    "theoretical_source": "理论来源 e.g. [IAM] PhII/A/[EVT] Heuristic/[KB] Rise Above etc.",
    "description": "一句话描述正在发生什么（客观、可复述）",
    "card_summary": "一句话卡片摘要（更口语化/有趣，可用表情符号）",
    "key_quote": "如有关键对话，引用最重要的一句",
    "observable_evidence": "可观察的行为证据",
    "meeting_note": "简明会议纪要记录"
}}

Return JSON only, no other content."""

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

            # 追踪：打印模型原始JSON（截断/全量由 LLM_TRACE_* 控制）
            self._llm_trace_decision("multimodal parsed_json", result if isinstance(result, dict) else {"raw": result})

            # 多模态分析阈值（与AI检测阈值保持一致）
            threshold = float(os.environ.get("MULTIMODAL_KEY_THRESHOLD", "0.35"))
            # 降低冷却时间，避免漏记重要时刻
            cooldown_s = float(os.environ.get("MULTIMODAL_COOLDOWN_SECONDS", "8"))
            debug_flag = (os.environ.get("MULTIMODAL_DEBUG", "0") or "0").strip().lower()
            debug_enabled = debug_flag in ("1", "true", "yes", "y", "on")
            debug_mode = (os.environ.get("MULTIMODAL_DEBUG_MODE", "concise") or "concise").strip().lower()

            now_ts = float(timestamp) if isinstance(timestamp, (int, float)) else time.time()
            last_ts = float(getattr(self, "_last_multimodal_moment_ts", 0.0) or 0.0)
            too_close = (now_ts - last_ts) < cooldown_s

            importance = float(result.get("importance", 0) or 0)
            is_key = bool(result.get("is_key_moment", False))

            allow_bypass_cooldown = importance >= 0.85
            ok_to_record = is_key and importance >= threshold and (not too_close or allow_bypass_cooldown)

            # 总是打印清晰的判定结果（命中或未命中），方便用户直接在终端看到
            summary_desc = (result.get("description") or result.get("meeting_note") or "")[:40].replace("\n", " ")
            rl = (result.get("reflection_level") or "").strip()
            phase = (result.get("phase") or "").strip()
            dim = (result.get("primary_dimension") or result.get("dimension") or "").strip()
            
            if ok_to_record:
                # 命中会由后续逻辑打印 "✨ 发现关键时刻"
                pass 
            else:
                # 分析拒绝原因
                reasons = []
                if not is_key:
                    reasons.append("AI判定非关键")
                if importance < threshold:
                    reasons.append(f"重要性不足({importance:.2f}<{threshold})")
                if too_close and not allow_bypass_cooldown:
                    reasons.append(f"冷却中({int(now_ts - last_ts)}s<{int(cooldown_s)}s)")
                
                reason_str = ", ".join(reasons)
                print(f"🧾 未命中: {reason_str} | 重要性:{importance:.2f} | 标签:{dim}/{phase}/{rl} | 摘要:{summary_desc}...")

            # Debug 输出：默认只打印“判定关键字段”，避免把全文/长转写刷屏
            if debug_enabled:
                rl = (result.get("reflection_level") or "").strip()
                phase = (result.get("phase") or "").strip()
                code = (result.get("behavior_code") or "").strip()
                print(
                    f"🧠 MM frame={frame_number} key={is_key} imp={importance:.2f} thr={threshold:.2f} "
                    f"cooldown={too_close}({cooldown_s:.0f}s) ok={ok_to_record} rl={rl} phase={phase} code={code}"
                )

                if debug_mode in {"verbose", "full"}:
                    spec = (result.get("specific_behavior") or "").strip()
                    if spec:
                        print(f"   🔎 {spec}")
                    preview = (transcript_text or "").replace("\n", " ").strip()
                    if len(preview) > 120:
                        preview = preview[:120] + "…"
                    if preview:
                        print(f"   🗣️ {preview}")

            # 追踪：打印判定依据
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
                print(f"   🧯 skip: {reason}")

            return None
                
        except json.JSONDecodeError as e:
            print(f"⚠️ Multimodal Analysis JSON parse error: {e}")
            return None
        except Exception as e:
            print(f"⚠️ Multimodal Analysis failed: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _analyze_frame_only(self, frame, frame_number: int,
                            person_count: int, track_ids: List[int]) -> Optional[Dict]:
        """纯图像分析（无语音时的回退）"""
        allow = (os.environ.get("ALLOW_IMAGE_ONLY_KEY_MOMENTS", "0") or "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
            "on",
        }
        if not allow:
            return None
        # 调用原有的图像分析（可能会落库 AI_DETECTED）
        self._analyze_frame_with_ai(frame, frame_number, person_count, track_ids or [])
        return None
    
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
        """记录多模态分析的关键时刻，并尽量生成与之匹配的视频片段。"""
        import cv2

        timestamp = float(timestamp) if isinstance(timestamp, (int, float)) else time.time()
        duration = timestamp - self.start_time
        time_str = self._format_time(duration)

        moment_id = f"multimodal_{int(timestamp)}_{frame_number}"

        # 保存关键帧
        frame_filename = f"{moment_id}.jpg"
        frame_path = self.moments_dir / frame_filename
        cv2.imwrite(str(frame_path), frame)

        # 构建描述（优先使用简短的card_summary显示在卡片上）
        card_summary = (ai_result.get("card_summary") or "").strip()
        full_description = (ai_result.get("description", "") or "").strip()
        description = card_summary or full_description  # 优先简短摘要
        key_quote = (ai_result.get("key_quote") or "").strip()
        if key_quote and key_quote not in description:
            description += f' 💬 "{key_quote}"'
        
        # 🏷️ 自动生成tags（从existing text content提取关键词）
        tags = ai_result.get("tags", [])
        if not tags or len(tags) == 0:
            # 从tagline/description自动提取关键词作为tags
            tagline = (ai_result.get("tagline") or "").strip()
            text_for_tags = tagline or description or transcript or ""
            # 改进的分词：按标点符号分割，提取短语
            import re
            # 移除emoji
            clean_text = re.sub(r'[😀-🙏💀-🛿🎀-🏿🐀-🦿🌀-🗿⚀-⛿✀-➿]', '', text_for_tags)
            # 按标点和空格分割
            clean_text = re.sub(r'[，。！？、：；""''（）【】\s]+', '|', clean_text)
            words = [w.strip() for w in clean_text.split('|') if w.strip()]
            
            # 过滤：只保留2-8字的短语，排除常见词
            stopwords = {'的', '了', '和', '与', '在', '是', '有', '这', '那', '就', '不', '也', '都', '还', '从', '到'}
            filtered = []
            for w in words:
                if 2 <= len(w) <= 8 and w not in stopwords:
                    filtered.append(w)
            
            tags = filtered[:3]  # 只取前3个
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
            ai_tags=tags,  # 使用自动生成的tags
            analysis=ai_result.get("meeting_note", "") or description,
            person_count=person_count,
            track_ids=track_ids,
            user_note=ai_result.get("observable_evidence", ""),
        )
        
        self.moments.append(moment)
        self.stats["ai_detected"] += 1
        self.stats["total_moments"] += 1

        # 先保存，再生成视频（确保后台处理可回写 transcript/analysis）
        self._save_moments()

        before_s = float(os.environ.get("MULTIMODAL_BEFORE_SECONDS", "15"))
        after_s = float(os.environ.get("MULTIMODAL_AFTER_SECONDS", "15"))

        # 🎬 统一使用frame_buffer生成完整30秒视频（保证一致性）
        # 移除min_required_frames阈值判断，确保所有AI检测的关键时刻都是固定时长
        video_path, video_duration = self._save_video_clip(
            moment_id=moment_id,
            clip_duration_before=float(before_s),
            clip_duration_after=float(after_s),  # 前后15秒=30秒
            frame_number=frame_number,
            frame=frame,
            center_timestamp=float(timestamp),
        )
        if video_path:
            moment.video_path = video_path
            moment.video_duration = video_duration
            self._save_moments()
            print(f"   ✅ 完整视频已生成: {video_duration:.1f}秒 (前{before_s:.0f}s + 后{after_s:.0f}s)")
        else:
            print(f"   ⚠️  视频生成失败")
        
        moment_type = ai_result.get("moment_type", "unknown")
        print(f"🎤📷 多模态关键时刻: {time_str} [{moment_type}]")
        print(f"   📝 {description}")
        if ai_result.get("meeting_note"):
            print(f"   📋 纪要: {ai_result['meeting_note']}")
        print(f"   🏷️ 标签: {', '.join(ai_result.get('tags', []))}")
        
        return moment
    
    def generate_meeting_notes(self, transcript_segments: List[Dict] = None) -> Dict[str, Any]:
        """
        生成智能会议纪要
        
        Args:
            transcript_segments: 完整的转写片段列表 [{"text": "...", "timestamp": ...}, ...]
            
        Returns:
            会议纪要字典
        """
        if not self.qwen_available:
            return self._generate_simple_meeting_notes(transcript_segments)
        
        try:
            # 准备时刻摘要
            moments_summary = []
            for m in sorted(self.moments, key=lambda x: x.timestamp):
                summary = {
                    "time": m.time_str,
                    "type": "用户标记" if m.source == "user_anchor" else "AI识别",
                    "description": m.ai_description or m.user_note or "未描述",
                    "tags": m.ai_tags,
                    "note": m.user_note if m.source != "user_anchor" else ""
                }
                moments_summary.append(summary)
            
            # 准备转写文本
            full_transcript = ""
            if transcript_segments:
                full_transcript = " ".join([s.get("text", "") for s in transcript_segments])
            
            prompt = f"""你是创客马拉松现场解说员，像NFL赛事解说员一样播报——专业、客观、但有画面感。

【解说原则】
- 忠实镜子：描述看到和听到的内容，不夸张、不瞎猜
- 口语化表达：用"正在...""刚刚...""看到..."等自然语言
- 适度热情：有节奏感，但不过度煽情
- 少用网络梗：偶尔可以，但要自然（每段最多1个）

【语音内容】
{full_transcript[:3000] if full_transcript else "（暂无语音记录）"}

【标记时刻】
{json.dumps(moments_summary, ensure_ascii=False, indent=2) if moments_summary else "（暂无标记）"}

🎙️ 播报要求：

**summary（20-35字）：**
客观描述现场状态，有画面感
✅ 好："团队正在调试硬件，传感器出现数据不稳定的情况，大家在排查原因"
✅ 好："看到他们找到了Bug位置，正在修改代码，进展不错"
❌ 差："讨论了硬件问题"（太书面）
❌ 差："芭比Q了！传感器炸了！"（太夸张）

**key_points（3-5个要点，每条15-25字）：**
客观事实，口语化短句
✅ 好："电路板第三个接口接触不良，王工正在重新焊接"
✅ 好："测试了A、B、C三个传感器型号，最后决定用A型"
✅ 好："张工提出加滤波电路的建议，团队讨论后采纳了"
❌ 差："硬件问题"（信息太少）
❌ 差："这波操作YYDS，绝了！"（太娱乐化）

**action_items（下一步计划）：**
客观具体的下一步
✅ 好："需要采购A型传感器模块，预计今天完成"
✅ 好："准备修复接口Bug，然后重新测试"
❌ 差："买传感器"（太简略）
❌ 差："赶紧修Bug，不然芭比Q！"（太夸张）

**decisions（已确定的决策）：**
说清选择和原因
✅ 好："决定使用React框架，因为团队更熟悉这个技术栈"
✅ 好："采纳方案B，理由是虽然复杂但稳定性更好"
❌ 差："用React"（没说为什么）

💡 **解说技巧：**
- 用现场感："正在...""看到...""听到...""刚刚..."
- 描述动作："张工走向白板""两人正在讨论""小李在敲代码"
- 转述对话：直接引用重要的话
- 说明进度："已完成X""正在处理Y""下一步Z"
- 适度评价：可以说"进展顺利""遇到困难"等客观评价

返回JSON格式:
{{
    "summary": "客观描述现场状态（20-35字）",
    "key_points": ["事实要点1（15-25字）", "事实要点2", "事实要点3"],
    "action_items": ["具体的下一步计划"],
    "decisions": ["决策内容（含理由）"]
}}

⚠️ 禁忌：
- 别用书面语："根据""综上""会议讨论""本次"
- 别太娱乐化：少用"YYDS""芭比Q""DNA动了"等网络梗
- 别瞎夸张：基于实际内容，不煽情不吐槽
- 内容不足时，summary写："现场较安静，等待下一步动作"
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
            
            # 保存会议纪要
            notes_file = self.moments_dir / "meeting_notes.json"
            with open(notes_file, 'w', encoding='utf-8') as f:
                json.dump(meeting_notes, f, ensure_ascii=False, indent=2)
            
            print(f"📋 会议纪要生成完成")
            return meeting_notes
            
        except Exception as e:
            print(f"⚠️ 会议纪要生成失败: {e}")
            return self._generate_simple_meeting_notes(transcript_segments)
    
    def _generate_simple_meeting_notes(self, transcript_segments: List[Dict] = None) -> Dict[str, Any]:
        """生成简单会议纪要（无 AI）"""
        full_transcript = ""
        if transcript_segments:
            full_transcript = " ".join([s.get("text", "") for s in transcript_segments])
        
        # 从关键时刻提取要点
        key_points = []
        for m in self.moments:
            if m.ai_description:
                key_points.append(m.ai_description)
            elif m.user_note:
                key_points.append(f"[用户标记] {m.user_note}")
        
        return {
            "summary": f"本次会议共记录 {len(self.moments)} 个关键时刻，转写文本约 {len(full_transcript)} 字。",
            "discussion_topics": [],
            "decisions": [],
            "action_items": [],
            "key_quotes": key_points[:5],  # 最多5个
            "participants_count": max([m.person_count for m in self.moments]) if self.moments else 0,
            "generated_at": datetime.now().isoformat(),
            "total_moments": len(self.moments),
            "transcript_length": len(full_transcript)
        }


    def _record_ai_moment(self, frame, frame_number: int,
                          person_count: int, track_ids: List[int],
                          ai_result: Dict[str, Any]):
        """记录 AI 识别的关键时刻（原始方法）"""
        import cv2
        
        timestamp = time.time()
        duration = timestamp - self.start_time
        time_str = self._format_time(duration)
        
        # 生成唯一ID
        moment_id = f"ai_{int(timestamp)}_{frame_number}"
        
        # 保存关键帧
        frame_filename = f"{moment_id}.jpg"
        description = ai_result.get("description", "")
        tagline = ai_result.get("tagline", "")
        analysis_text = ai_result.get("analysis", "")
        
        # 提取框架标签（从分析文本中）
        framework_tags = KeyMomentsManager._extract_framework_tags(analysis_text)
        
        # 创建关键时刻对象
        moment = KeyMoment(
            id=moment_id,
            timestamp=float(timestamp),
            source=MomentSource.MULTIMODAL_AI.value,
            frame_number=frame_number,
            frame_path=frame_path,
            ai_description=description,
            ai_tagline=tagline,
            ai_tags=tags,  # 使用自动生成的tags
            ai_framework_tags=framework_tags,  # 添加框架标签
            ai_importance=float(ai_result.get("importance", 0.5)),
            transcript=transcript_segment,
            person_count=person_count,
            analysis=analysis_text,
            user_note=ai_result.get("observable_evidence", ""),
        )
        
        self.moments.append(moment)
        self.stats["ai_detected"] += 1
        self.stats["total_moments"] += 1
        
        # 保存
        self._save_moments()
        
        print(f"🤖 AI 识别关键时刻: {time_str} (帧 {frame_number})")
        print(f"   📝 {ai_result.get('description', '')}")
        print(f"   🏷️ 标签: {', '.join(ai_result.get('tags', []))}")
    
    # ============================================================
    # 📖 叙事生成 (The Narrative)
    # ============================================================
    
    def generate_narrative(self) -> Dict[str, Any]:
        """
        生成团队叙事 (Oeuvre)
        
        像纪录片导演一样，将碎片化的痕迹剪辑成连贯的团队叙事
        """
        if not self.moments:
            return {"narrative": "暂无关键时刻记录", "chapters": []}
        
        if not self.qwen_available:
            return self._generate_simple_narrative()
        
        try:
            # 准备时刻摘要
            moments_summary = []
            for m in sorted(self.moments, key=lambda x: x.timestamp):
                summary = {
                    "time": m.time_str,
                    "source": "User Marked" if m.source == "user_anchor" else "AI Detected",
                    "description": m.user_note or m.ai_description or "No description",
                    "person_count": m.person_count,
                    "importance": m.ai_importance if m.source == "ai_detected" else 0.8,
                    "tags": m.ai_tags
                }
                moments_summary.append(summary)
            
            prompt = f"""You are a documentary director and educational researcher. Based on the following key moments from a collaborative learning activity, create a team narrative report.

Key Moments Record:
{json.dumps(moments_summary, ensure_ascii=False, indent=2)}

Please generate:
1. Narrative Summary (3-5 sentences overall storyline)
2. Key Chapters (Organize moments into meaningful stages)
3. Team Insights (Collaboration patterns and highlights observed from these moments)
4. Reflection Questions (2-3 questions to guide student reflection)

Return in JSON format:
{{
    "narrative_summary": "Overall narrative...",
    "chapters": [
        {{
            "title": "Chapter Title",
            "time_range": "00:00-05:00",
            "description": "What happened in this stage",
            "moment_ids": ["related moment ids"]
        }}
    ],
    "team_insights": ["Insight 1", "Insight 2"],
    "reflection_questions": ["Question 1", "Question 2"]
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
        """生成简单叙事 (无 AI)"""
        sorted_moments = sorted(self.moments, key=lambda x: x.timestamp)
        
        chapters = []
        current_chapter_moments = []
        chapter_start_time = 0
        
        # 按时间间隔分章节 (5分钟一章)
        for m in sorted_moments:
            if m.duration_seconds - chapter_start_time > 300 and current_chapter_moments:
                chapters.append({
                    "title": f"阶段 {len(chapters) + 1}",
                    "time_range": f"{self._format_time(chapter_start_time)}-{self._format_time(current_chapter_moments[-1].duration_seconds)}",
                    "description": f"记录了 {len(current_chapter_moments)} 个关键时刻",
                    "moment_ids": [cm.id for cm in current_chapter_moments]
                })
                current_chapter_moments = []
                chapter_start_time = m.duration_seconds
            
            current_chapter_moments.append(m)
        
        # 添加最后一个章节
        if current_chapter_moments:
            chapters.append({
                "title": f"阶段 {len(chapters) + 1}",
                "time_range": f"{self._format_time(chapter_start_time)}-{self._format_time(current_chapter_moments[-1].duration_seconds)}",
                "description": f"记录了 {len(current_chapter_moments)} 个关键时刻",
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
                "回顾这些关键时刻，哪个最让你印象深刻？为什么？",
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
            source: 可选过滤 - 'user_anchor' 或 'ai_detected'
        """
        moments = self.moments
        if source:
            moments = [m for m in moments if m.source == source]
        
        return [m.to_dict() for m in sorted(moments, key=lambda x: x.timestamp)]
    
    def get_stats(self) -> Dict:
        """获取统计信息"""
        return {
            **self.stats,
            "session_duration": self._format_time(time.time() - self.start_time),
            "ai_enabled": self.qwen_available,
            "ai_interval": self.ai_interval_seconds
        }
    
    def get_moment_image_path(self, moment_id: str) -> Optional[str]:
        """获取关键时刻图片路径"""
        for m in self.moments:
            if m.id == moment_id:
                return m.frame_path
        return None
    
    def get_moment_video_path(self, moment_id: str) -> Optional[str]:
        """获取关键时刻视频片段路径"""
        for m in self.moments:
            if m.id == moment_id:
                return m.video_path if m.video_path else None
        return None

    def generate_linkography(self, moments: List[Dict]) -> Dict:
        """生成 Linkography 图：nodes + edges（使用 LLM 从卡片内容推断跨时刻关联）。

        说明：
        - 仅允许引用输入 moments 的信息，不足则返回空 edges。
        - 输出结构用于前端可视化：{"status":"ok", "nodes":[], "edges":[]}。
        """

        # 兜底
        if not isinstance(moments, list) or not moments:
            return {"status": "ok", "nodes": [], "edges": []}

        # 缓存：避免频繁轮询触发重复 LLM 调用
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

        # 组织 prompt：尽量短、但信息足够
        def _short(s: str, n: int) -> str:
            s = (s or "").strip().replace("\n", " ")
            return s if len(s) <= n else (s[:n] + "…")

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
            "You are a rigorous collaborative analysis assistant.\n"
            "Task: Based on the given key moment cards, find interpretable links between different moments (Linkography).\n"
            "Must obey: 1) Only cite input fields, do not fabricate; 2) If evidence is insufficient, do not link; 3) Output must be strict JSON (no code blocks, no extra text).\n"
            "Edge type suggestions: same_topic, follow_up, cause_effect, supports, contradicts, decision_related."
        )

        prompt = (
            "Given a set of moments (sorted by time). Please output a JSON object:\n"
            "{\n"
            "  \"nodes\": [{\"id\":\"...\",\"t\":1700000000.0,\"label\":\"...\"}],\n"
            "  \"edges\": [{\"source\":\"id1\",\"target\":\"id2\",\"type\":\"same_topic\",\"reason\":\"<=20 words\"}]\n"
            "}\n"
            "Requirements:\n"
            "- nodes must cover all input ids; label: use English phrase to summarize (<=16 words).\n"
            "- edges: max 60 items, connect clearly related or potentially related relations; reason must be short and inferred from input.\n"
            "- Do not use non-existent ids.\n\n"
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
            # 尝试从文本中抽取第一个 JSON 对象
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
            # 最坏兜底：仅节点
            print(f"❌ JSON PARSE FAILED. Raw Output:\n{txt}")
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

        # 按时间排序 nodes，前端更好画
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
    
    print("\n📍 测试用户标记...")
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
    
    # 获取所有时刻
    print("\n📋 所有关键时刻:")
    moments = manager.get_moments()
    for m in moments:
        print(f"   [{m['source']}] {m['time_str']} - {m.get('user_note') or m.get('ai_description', 'N/A')}")
    
    # 生成叙事
    print("\n📖 生成叙事...")
    narrative = manager.generate_narrative()
    print(f"   摘要: {narrative.get('narrative_summary', '')}")
    
    print("\n✅ 测试完成!")
