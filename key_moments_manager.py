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

                # ✅ 历史卡片修复：使用 LLM 为历史 moments 生成“适合卡片扫读”的 ai_tagline
                # 入口：KEY_MOMENTS_REGEN_TAGLINES=1
                # - 只在 ai_tagline 为空/明显不合适时触发
                # - 基于 transcript + ai_description + context.txt（全局 + 每条 moment _context.txt）
                try:
                    if (os.environ.get("KEY_MOMENTS_REGEN_TAGLINES", "0") or "0").strip() in {"1", "true", "yes"}:
                        self._regen_history_taglines_with_llm()
                except Exception as e:
                    print(f"   ⚠️ 历史卡片 ai_tagline 修复失败: {e}")

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

            except Exception as e:
                print(f"   ❌ 加载历史数据失败: {e}")
                # JSON 读取/解析失败，也尝试从目录重建一次
                self._rebuild_moments_index_from_dir()
        else:
            # moments.json 不存在时，尝试从目录重建
            self._rebuild_moments_index_from_dir()

    def _regen_history_taglines_with_llm(self):
        """为历史 moments 生成/修复 ai_tagline（卡片扫读字段）。

        触发：KEY_MOMENTS_REGEN_TAGLINES=1
        限制：默认最多处理 KEY_MOMENTS_REGEN_TAGLINES_LIMIT 条（默认 50），避免启动过慢。

        输入：
        - moment.transcript（转写）
        - moment.ai_description（旧描述，可能是口播/长段）
        - 每条 moment 的 {id}_context.txt（如存在）
        - 全局 context.txt（如存在）

        输出：
        - 仅写入 m.ai_tagline（短、适合卡片扫读）
        """
        if not getattr(self, "qwen_available", False):
            print("   ⚠️ LLM 未配置，跳过历史 ai_tagline 生成")
            return

        limit = int((os.environ.get("KEY_MOMENTS_REGEN_TAGLINES_LIMIT", "50") or "50").strip())
        dry_run = (os.environ.get("KEY_MOMENTS_REGEN_TAGLINES_DRYRUN", "0") or "0").strip() in {"1", "true", "yes"}

        # 全局 KB
        global_kb = ""
        try:
            kb_path = self.data_dir.parent / "context.txt"
            if kb_path.exists():
                global_kb = kb_path.read_text(encoding="utf-8", errors="replace").strip()
        except Exception:
            global_kb = ""

        def needs_fix(m) -> bool:
            tg = (m.ai_tagline or "").strip()
            # 为空必修
            if not tg:
                return True
            # 过长/像整段口播/包含多行结构化分析，也认为不适合卡片
            if len(tg) > 60:
                return True
            if "\n" in tg:
                return True
            if "详细描述" in tg or "证据摘录" in tg or "上下文定位" in tg:
                return True
            return False

        changed = 0
        processed = 0

        for m in list(self.moments):
            if processed >= limit:
                break
            if not needs_fix(m):
                continue

            processed += 1

            # per-moment context
            per_ctx = ""
            try:
                ctx_path = self.moments_dir / f"{m.id}_context.txt"
                if ctx_path.exists():
                    per_ctx = ctx_path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                per_ctx = ""

            transcript = (m.transcript or "").strip()
            old_desc = (m.ai_description or "").strip()

            # LLM prompt：只产出一行 tag（不带“标签：”前缀），用于卡片展示
            prompt = f"""你是一个提示词严格的‘卡片摘要生成器’。

目标：为一条“历史关键时刻”生成一个适合卡片扫读的一句话摘要（ai_tagline）。

硬性要求：
1) 输出必须是【单行中文】（不要换行）
2) 20~35字最佳（最长不超过45字）
3) 必须包含：人数/主体 + 具体动作/事件 + 关键对象（如电脑/代码/屏幕/白板/相机/调试等）
4) 禁止主观评价/煽情词（不要“热烈/精彩/深度/氛围”）
5) 不要编造事实；如果信息不足，用“有人/多人/画面未明确”表达
6) 不要输出“标签：”前缀，不要输出引号，不要输出列表

可用信息：
【旧AI描述（可能很长/口播）】
{old_desc or "(无)"}

【转写（可能有噪声）】
{transcript or "(无语音)"}

【该时刻上下文（可能截断）】
{per_ctx.strip() or "(无)"}

【全局背景信息/知识库】
{global_kb[:1500] if global_kb else "(无)"}

请只输出一行 ai_tagline："""

            try:
                tagline = (self._run_text_llm(prompt, temperature=0.2, max_tokens=80) or "").strip()
                # 清洗：去掉可能的前缀
                for prefix in ("标签：", "卡片摘要：", "摘要："):
                    if tagline.startswith(prefix):
                        tagline = tagline[len(prefix):].strip()
                tagline = tagline.replace("\n", " ").strip()

                if not tagline:
                    continue

                if dry_run:
                    print(f"   🧪 [DRYRUN] {m.id}: {tagline}")
                    continue

                m.ai_tagline = tagline
                changed += 1

                # 逐条保存避免突然断电/中断导致丢改动
                if changed % 5 == 0:
                    self._save_moments()
            except Exception as e:
                print(f"   ⚠️ 生成 ai_tagline 失败: {m.id}: {e}")
                continue

        if changed:
            self._save_moments()
            print(f"   ✅ 历史 ai_tagline 已修复: {changed} 条（处理 {processed} 条，limit={limit}）")
        else:
            print(f"   ℹ️ 历史 ai_tagline 无需修复（检查 {processed} 条，limit={limit}）")
