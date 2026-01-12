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
from urllib.parse import quote
import threading
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any
from enum import Enum

# ============================================================
# ? 关键时刻时间窗（默认前后各15秒，可用环境变量覆盖）
# ============================================================

KEY_MOMENT_BEFORE_SECONDS = float(os.environ.get("KEY_MOMENT_BEFORE_SECONDS", "15"))
KEY_MOMENT_AFTER_SECONDS = float(os.environ.get("KEY_MOMENT_AFTER_SECONDS", "15"))

# ============================================================
# ? 数据结构
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
    time_str: str = ""               # 只读时间 HH:MM:SS
    duration_seconds: float = 0      # 从开始到这一刻的秒数
    
    # 用户输入 (从 user_anchor)
    user_note: str = ""              # 用户备注 (可选)
    
    # 语音数据
    transcript: str = ""             # 语音转文字内容

    # 语音/模型元信息（用于回答“现在ASR是什么模型”）
    asr_provider: str = ""           # fireredasr | dashscope | ...
    asr_model: str = ""              # 例如 aed:FireRedASR-AED-L 或 paraformer-realtime-v2
    asr_model_dir: str = ""          # FireRedASR 模型目录（如适用）
    
    # AI 分析结果 (从 ai_detected)
    ai_description: str = ""         # AI 对这一刻的描述
    ai_tagline: str = ""             # AI 短标题（用于贴纸/短标识；可选）
    ai_importance: float = 0.0       # AI 评估的重要性 0-1
    ai_tags: List[str] = field(default_factory=list)  # AI 提取的标签
    ai_framework_tags: str = ""      # 协作学习框架标题（如[R2]论证、Eng-Flow等）
    analysis: str = ""               # AI 综合分析/总结

    # LLM 元信息
    llm_provider: str = ""           # qwen | claude
    llm_model: str = ""              # 实际调用的模型（此处多为 vision_model）

    # Debug info (optional)
    last_error: str = ""             # 最近一次 AI/ASR 失败的错误信息（便于 UI 排查）
    
    # 场景信息
    person_count: int = 0            # 当前画面人数
    track_ids: List[int] = field(default_factory=list)  # 活跃的追踪ID
    
    # 叙事元素 (由 LLM 生成)
    narrative_role: str = ""         # 在叙事中的角色: opening/rising/climax/falling/resolution
    narrative_text: str = ""         # 叙事文本
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        d = asdict(self)
        # 鍓嶇??鐢? `||` 鍋氬厹搴曟椂锛岀┖瀛楃?︿覆/None 鎵嶄細姝ｇ‘鍥為��锛涚函绌虹櫧瀛楃?︿覆浼氬?艰嚧鈥滅湅璧锋潵娌″唴瀹光�濄�?
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
# 馃幀 鍏抽敭鏃跺埢绠＄悊鍣?
# ============================================================

class KeyMomentsManager:
    """鍙岃建鍏抽敭鏃跺埢绠＄悊鍣?"""

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
        鍒濆?嬪寲绠＄悊鍣?
        
        Args:
            data_dir: 鏁版嵁瀛樺偍鐩?褰?
            api_key: DashScope API Key (鐢ㄤ簬 Qwen-VL)
            video_source: 鍘熷?嬭?嗛?戞枃浠惰矾寰勬垨鎽勫儚澶碔D (鐢ㄤ簬鎻愬彇闊抽??)
            audio_source: 闊抽?戞簮璺?寰? (鍙?閫?, 濡傛灉涓庤?嗛?戜笉鍚?)
            microphone_recorder: 楹﹀厠椋庡綍鍒跺櫒瀹炰緥 (鎽勫儚澶存ā寮忎娇鐢?)
        """
        self.data_dir = data_dir or Path(__file__).parent / "integrated_data"
        self.moments_dir = self.data_dir / "key_moments"
        self.moments_dir.mkdir(parents=True, exist_ok=True)
        
        # 楹﹀厠椋庡綍鍒跺櫒
        self.microphone_recorder = microphone_recorder

        # API 配置 (LLM provider: qwen | claude)
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

        # FireRedASR 妯″瀷缂撳瓨锛堝叧閿?鏃跺埢杞?鍐欎細棰戠箒瑙﹀彂锛涢伩鍏嶆瘡娆? from_pretrained 瀵艰嚧鍗￠】/楂樺欢杩燂級
        self._fireredasr_lock = threading.Lock()
        self._fireredasr_model = None

        # moments 鐨勫苟鍙戞洿鏂帮紙鐢ㄦ埛鏍囪?扮嚎绋? / after 鎵╁睍绾跨▼ / AI绾跨▼閮藉彲鑳藉啓鍏ワ級
        self._moments_lock = threading.Lock()

        # 閲嶄换鍔￠檺娴侊細鍏抽敭鏃跺埢鈥滄彁鍙栭煶棰戔啋ASR鈫掑?氭ā鎬丄I鈥濅細鍗犵敤杈冨?? CPU/GIL銆?
        # 榛樿?や覆琛岋紝閬垮厤鐐瑰嚮鏍囪?板悗鎶婂疄鏃? ASR 鎷栧埌楂樺欢杩熴�?
        heavy_n = int(os.environ.get("KEY_MOMENT_HEAVY_CONCURRENCY", "1"))
        if heavy_n < 1:
            heavy_n = 1
        self._heavy_job_sema = threading.Semaphore(heavy_n)

        # 璁板綍鏈�杩戜竴娆? ASR 璋冪敤鐨勫厓淇℃伅锛屼究浜庡啓鍏? moment
        self._last_asr_meta: Dict[str, str] = {}
        self.llm_api_key = self.claude_api_key if self.llm_provider.startswith("claude") else self.dashscope_api_key
        self.api_key = self.dashscope_api_key  # 鍏煎?规棫瀛楁?碉紙涓昏?佺敤浜庤??闊?/闊抽?戣皟鐢?锛?
        self.qwen_available = bool(self.llm_api_key)
        
        # 馃幀 瑙嗛??/闊抽?戞簮閰嶇疆 (鐢ㄤ簬鎻愬彇闊抽?戣建閬?)
        self.video_source = video_source  # 鍘熷?嬭?嗛?戞枃浠惰矾寰?
        self.audio_source = audio_source or video_source  # 闊抽?戞簮 (榛樿?や笌瑙嗛?戠浉鍚?)
        self.video_fps = float(video_fps) if video_fps else None
        
        # 鐘舵�?
        self.moments: List[KeyMoment] = []
        self.start_time: float = time.time()
        self.frame_count: int = 0
        
        # 馃幀 瑙嗛?戝抚缂撳啿鍖? (鐢ㄤ簬褰曞埗鍏抽敭鏃跺埢鍓嶅悗鐨勮?嗛?戠墖娈?)
        self.frame_buffer: list = []      # 瀛樺偍 (frame, frame_num, timestamp) 鍏冪粍
        # 缂撳啿鍖烘渶澶т繚鐣欑?掓暟锛堥渶瑕嗙洊鍏抽敭鏃跺埢绐楀彛 + AI鍒嗘瀽寤惰繜 + 浣欓噺锛?
        # 浠?60绉掑?炲姞鍒?120绉掞紝浠ラ�傚簲AI鍒嗘瀽寤惰繜锛堢害60绉掞級
        self.buffer_max_seconds = int(max(120, KEY_MOMENT_BEFORE_SECONDS + KEY_MOMENT_AFTER_SECONDS + 90))
        # 鎸夋渶楂樺彲鑳紽PS(60)璁＄畻锛岀‘淇滷PS娉㈠姩鏃朵粛鑳借?嗙洊120绉?
        self.buffer_fps = 60.0
        self.buffer_max_frames = int(self.buffer_max_seconds * self.buffer_fps)
        print(f"   🧠 [BUFFER] Config: max_seconds={self.buffer_max_seconds}, fps={self.buffer_fps}, max_frames={self.buffer_max_frames}, format=JPEG")
        self.buffer_lock = threading.Lock()
        
        # 馃攰 闊抽?戠紦鍐插尯 (鐢ㄤ簬褰曞埗瀵瑰簲鐨勯煶棰戠墖娈?)
        self.audio_buffer: list = []      # 瀛樺偍 (audio_chunk, timestamp) 鍏冪粍
        self.audio_buffer_lock = threading.Lock()
        
        # AI 分析配置
        self.ai_interval_seconds = 210  # 3.5鍒嗛挓涓�娆″垏鐗?
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
        print(f"   📁 存储: {self.moments_dir}")
        print(f"   🎧 音频: {audio_status}")
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

                # 杞婚噺杩佺Щ锛氬巻鍙叉暟鎹?閲屾湁浜? moment 鐨? ai_description 鏄?鈥滅煭鏍囩?锯�?(<=14瀛?)锛?
                # 浣? analysis 涓?鍖呭惈鈥滆?︾粏鎻忚堪锛氣�︹�濓紝浼氬?艰嚧鍗＄墖淇℃伅瀵嗗害涓嬮檷銆傝繖閲岃嚜鍔ㄦ彁鍗囦竴娆°�?
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
                
                # 涓哄巻鍙叉暟鎹?琛ュ厖tags骞朵繚瀛?
                tags_updated = False
                for m in self.moments:
                    # 馃彿锔? 鑷?鍔ㄧ敓鎴恡ags锛堝?傛灉涓嶅瓨鍦?锛?
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
                        
                        # 杩囨护锛氬彧淇濈暀2-8瀛楃殑鐭?璇?
                        stopwords = {'鐨?', '浜?', '鍜?', '涓?', '鍦?', '鏄?', '鏈?', '杩?', '閭?', '灏?', '涓?', '涔?', '閮?', '杩?', '浠?', '鍒?'}
                        filtered = [w for w in words if 2 <= len(w) <= 8 and w not in stopwords]
                        
                        tags = filtered[:3]
                        if not tags:
                            tags = []
                        m.ai_tags = tags
                        tags_updated = True
                
                if tags_updated:
                    print("   🏷️ 为历史数据补充了 tags")
                    self._save_moments()
                
                # print(f"   宸插姞杞? {len(self.moments)} 涓?鍘嗗彶鍏抽敭鏃跺埢")
            except Exception as e:
                print(f"   鈿狅笍 鍔犺浇鍘嗗彶鏁版嵁澶辫触: {e}")
                # JSON 读取/解析失败，也尝试从目录重建一次
                self._rebuild_moments_index_from_dir()
        else:
            # moments.json 不存在时，尝试从目录重建
            self._rebuild_moments_index_from_dir()
    
    def _save_moments(self):
        """淇濆瓨鍏抽敭鏃跺埢鍒版枃浠?"""
        moments_file = self.moments_dir / "moments.json"
        try:
            # print(f"馃敡 [DEBUG] Saving moments... count={len(self.moments)} (stats={self.stats})")
            # if len(self.moments) > 0:
            #     print(f"馃敡 [DEBUG] Sample moment: {self.moments[0].to_dict()}")
            
            data = {
                'moments': [m.to_dict() for m in self.moments],
                'stats': self.stats,
                'last_updated': datetime.now().isoformat()
            }
            with open(moments_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print("🧾 [DEBUG] Save complete.")
        except Exception as e:
            print(f"鈿狅笍 淇濆瓨鍏抽敭鏃跺埢澶辫触: {e}")
            import traceback
            traceback.print_exc()

    def _build_llm_client(self):
        """鏍规嵁鎻愪緵鑰呭垱寤? LLM 瀹㈡埛绔?"""
        if not self.llm_api_key:
            raise RuntimeError("LLM API Key 鏈?閰嶇疆")
        # 閬垮厤缃戠粶鎶栧姩/闄愭祦瀵艰嚧璇锋眰鏃犻檺鏈熷崱浣?
        llm_timeout = float(os.environ.get("LLM_TIMEOUT_SECONDS", "45"))
        if self.llm_provider.startswith("claude"):
            try:
                from anthropic import Anthropic
            except ImportError as e:
                raise ImportError("璇峰厛瀹夎?? anthropic 搴?: pip install anthropic") from e
            # anthropic 鐨? timeout 閰嶇疆鍦ㄤ笉鍚岀増鏈?宸?寮傝緝澶э紱姝ゅ?勫厛淇濇寔鍏煎?癸紝浠呮帶鍒? OpenAI 璺?寰?
            return Anthropic(api_key=self.llm_api_key)
        try:
            from openai import OpenAI
        except ImportError as e:
            raise ImportError("璇峰厛瀹夎?? openai 搴?: pip install openai>=1.0.0") from e
        # 绂佺敤httpx鐨勪唬鐞嗚嚜鍔ㄦ?�娴嬶紙trust_env=False锛夛紝閬垮厤GNOME绯荤粺socks浠ｇ悊瀵艰嚧閿欒??
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
    # 馃Ь LLM Trace锛堟墦鍗? Prompt/杩斿洖/鍒ゅ畾渚濇嵁锛?
    # ============================================================

    def _llm_trace_mode(self) -> str:
        """Trace 杈撳嚭绛夌骇锛歰ff / meta / compact / full

        - off: 涓嶆墦鍗?
        - meta: 鍙?鎵撳嵃 meta锛堜笉鎵撳嵃 prompt/response锛?
        - compact: 鎵撳嵃 meta + response/decision锛屼絾闅愯棌 prompt锛堥伩鍏嶅埛灞?/娉勯湶鎻愮ず璇嶏級
        - full: 鎵撳嵃 meta + prompt + response
        """
        # 鏄惧紡 LLM_TRACE=1 鏃舵墠璁や负鐢ㄦ埛瑕佺湅 trace锛涢粯璁ょ粰 compact锛岄伩鍏? prompt 鍒峰睆
        flag = (os.environ.get("LLM_TRACE", "") or "").strip().lower()
        if flag in {"1", "true", "yes", "y", "on"}:
            mode = (os.environ.get("LLM_TRACE_MODE", "") or "").strip().lower() or "compact"
            return mode if mode in {"off", "meta", "compact", "full"} else "compact"

        # 鍏煎?癸細鎵撳紑 MULTIMODAL_DEBUG 涔熷惎鐢? trace锛屼絾鍙?鎵撳嵃 meta
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

        # meta 妯″紡锛氬彧鎵撳嵃 meta
        if mode == "meta" and title != "meta":
            return

        # compact 妯″紡锛氶殣钘? prompt锛堜繚鐣? response/decision锛?
        if mode == "compact" and (" prompt" in title or title.endswith("prompt")):
            content = "<hidden prompt; set LLM_TRACE_MODE=full to show>"

        txt = (content or "")
        if not self._llm_trace_full():
            mx = self._llm_trace_max_chars()
            if len(txt) > mx:
                txt = txt[:mx] + f"\n... (truncated, {len(content)} chars total; set LLM_TRACE_FULL=1 to print all)"
        print("\n" + ("=" * 88))
        print(f"🧪 LLM TRACE | {title}")
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
        """鍦ㄧ敤鎴锋爣璁板悗锛堝挨鍏? AFTER 绉掍箣鍚庯級琛ラ綈/淇?姝ｅ睍绀烘枃鏈?銆?

        - user_note: 鐢ㄤ簬鍗＄墖鐭?鎻忚堪锛堝墠绔?浼樺厛灞曠ず锛?
        - transcript: 鐢ㄤ簬璇︽儏椤碘�淭ranscription鈥?
        - context_transcript: 浼氬啓鍏? *_context.txt锛屼緵鍚庣画 AI 鍒嗘瀽寮曠敤
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
                        or "[0" in incoming  # 鍏煎?? [0:xx] / [00:xx]
                    )
                    if looks_like_window:
                        if incoming and incoming != existing:
                            m.transcript = transcript
                            updated = True
                    else:
                        # 闈炵獥鍙ｆ枃鏈?锛氫粛鎸夆�滄洿闀垮垯瑕嗙洊鈥濈殑瑙勫垯
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

        # 鍚屾?ュ啓鍥? context 鏂囦欢锛堜緵 AI 鍒嗘瀽璇佹嵁寮曠敤锛?
        if context_transcript:
            try:
                context_path = self.moments_dir / f"{moment_id}_context.txt"
                # 杩藉姞鍐欏叆锛屼笉瑕嗙洊宸叉湁 header/user_note
                with open(context_path, "a", encoding="utf-8") as f:
                    f.write("\n=== transcript_context ===\n")
                    f.write(context_transcript.strip())
                    f.write("\n")
            except Exception:
                pass
        return updated

    @staticmethod
    def _extract_anthropic_text(message):
        """鎻愬彇 Anthropic 娑堟伅涓?鐨勬枃鏈?"""
        return "".join([block.text for block in getattr(message, "content", []) if getattr(block, "type", None) == "text"]).strip()

    @staticmethod
    def _extract_tagline(text: str) -> tuple[str, str]:
        """浠庢ā鍨嬭緭鍑轰腑鎶藉彇鐭?鏍囩?撅紙鐢ㄤ簬鍗＄墖/璐寸焊锛夊拰姝ｆ枃銆傛敮鎸佷腑鑻辨枃鏍煎紡銆?"""
        if not text:
            return "", ""
        lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
        tagline = ""
        body_lines = []
        for ln in lines:
            # 鏀?鎸佷腑鏂囧拰鑻辨枃鏍囩?炬牸寮?
            if ln.startswith("鏍囩?撅細") or ln.startswith("鏍囩??:") or ln.lower().startswith("label:"):
                if "锛?" in ln:
                    tagline = ln.split("锛?", 1)[1].strip()
                else:
                    tagline = ln.split(":", 1)[1].strip()
                continue
            body_lines.append(ln)

        # 鍏滃簳锛氬?傛灉娌℃湁鏄惧紡鏍囩?撅紝鍙栫??涓�鍙ュ墠 14 涓?瀛?
        if not tagline:
            first = lines[0] if lines else ""
            tagline = first

        tagline = tagline.replace("\"", "").strip()
        if len(tagline) > 50:  # 鑻辨枃鏍囩?惧彲鑳芥洿闀匡紝澧炲ぇ闄愬埗
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
        # Matches: **Detailed Description:**, Detailed Description:, 详细描述：, etc.
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
        """浠庢?ｆ枃涓?鎶藉彇\"鍗＄墖鎽樿?乗"锛?20-30 words鐨勭畝鐭?鐗堟湰锛夈�傛敮鎸佷腑鑻辨枃鏍煎紡銆?"""
        if not body:
            return ""
        lines = [ln.strip() for ln in body.splitlines()]
        for ln in lines:
            # 鏀?鎸佷腑鏂囧拰鑻辨枃鏍煎紡
            if ln.startswith("鍗＄墖鎽樿?侊細") or ln.startswith("鍗＄墖鎽樿??:") or ln.lower().startswith("card summary:"):
                if "锛?" in ln:
                    txt = ln.split("锛?", 1)[-1].strip()
                else:
                    txt = ln.split(":", 1)[-1].strip()
                return txt
        return ""
    
    @staticmethod
    def _extract_framework_tags(body: str) -> str:
        """浠庢?ｆ枃涓?鎶藉彇'鍒嗘瀽妗嗘灦鏍囩??'娈佃惤銆傛敮鎸佷腑鑻辨枃鏍煎紡銆?"""
        if not body:
            return ""
        lines = [ln.strip() for ln in body.splitlines()]
        for i, ln in enumerate(lines):
            # 鏀?鎸佷腑鏂囧拰鑻辨枃鏍煎紡
            if (ln.startswith("鍒嗘瀽妗嗘灦鏍囩?撅細") or ln.startswith("鍒嗘瀽妗嗘灦鏍囩??:") or 
                ln.startswith("妗嗘灦鏍囩?撅細") or ln.lower().startswith("analysis framework label:")):
                # 鎻愬彇鍐呭?癸紙鍘绘帀鍓嶇紑锛?
                if "锛?" in ln:
                    content = ln.split("锛?", 1)[-1].strip()
                else:
                    content = ln.split(":", 1)[-1].strip()
                return content
        return ""


    def _run_text_llm(self, prompt: str, system: str = "", model_override: str = None,
                      temperature: float = 0.3, max_tokens: int = 1500) -> str:
        """杩愯?屾枃鏈? LLM锛堟敮鎸? Qwen / Claude锛?"""
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
                timeout=120.0  # 120绉掕秴鏃?,搴斿?瑰?嶆潅鍒嗘瀽
            )
            out = response.choices[0].message.content.strip()
            print(f"\n[DEBUG] Qwen Response (len={len(out)}):\n{out}\n[DEBUG] END Response\n")
            self._llm_trace_print("text response", out)
            return out
        except Exception as e:
            error_msg = f"鉂? LLM API璋冪敤澶辫触: {str(e)}"
            print(error_msg)
            if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                print("鈴憋笍 鎻愮ず: API瓒呮椂,璇锋?�鏌ョ綉缁滄垨澧炲姞timeout鍊?")
            return ""  # 杩斿洖绌哄瓧绗︿覆,璁╄皟鐢ㄦ柟澶勭悊fallback閫昏緫

    def _run_vision_llm(self, image_base64: str, prompt: str, model_override: str = None,
                         temperature: float = 0.7, max_tokens: int = 500) -> str:
        """杩愯?屽?氭ā鎬?/瑙嗚?? LLM"""
        model_name = model_override or self.vision_model
        # 鍙?鎵撳嵃鍥剧墖闀垮害锛岄伩鍏嶆妸base64鍒峰睆
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
            max_candidates: 杩斿洖鍊欓�夋暟閲忎笂闄?
            base_timestamp: 鐢ㄤ簬鎶? epoch 鏄犲皠鍒扮浉瀵规椂闂达紙None 鍒欒嚜鍔ㄧ敤 transcript_items 鏈�鏃? timestamp锛?

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
                txt = txt[:120] + "鈥?"
            line = f"[{tstr}] {txt}"
            lines.append(line)
            line_by_time.setdefault(tstr, line)

        if not lines:
            return []

        # 鎺у埗 prompt 闀垮害锛氭渶澶? 220 琛?
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
            "蹇呴』缁欏嚭璇佹嵁锛歟vidence 蹇呴』鏄?浠庡師杞?鍐欎腑閫愬瓧鎽樺綍鐨勭煭鐗囨?碉紙涓嶅厑璁哥紪閫狅級銆?"
            "杈撳嚭蹇呴』鏄?涓ユ牸 JSON锛堜笉瑕佷唬鐮佸潡銆佷笉瑕侀?濆?栨枃瀛楋級銆?"
        )
        prompt = (
            f"璇蜂粠浠ヤ笅杞?鍐欎腑閫夊嚭鏈�澶? {max_candidates} 涓?鍊欓�夊叧閿?鏃跺埢銆俓n"
            "杈撳嚭鏍煎紡锛歔{\"time_str\":\"HH:MM:SS\",\"reason\":\"...\",\"evidence\":\"...\"}, ...]\n"
            "time_str 蹇呴』涓庤浆鍐欓噷鐨勬椂闂存埑瀹屽叏涓�鑷淬�俓n\n"
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

            # time_str -> timestamp 鏄犲皠锛堣嫢 time 涓虹┖锛屼娇鐢? base_ts 鐢熸垚鐨勭浉瀵规椂闂达級
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
        provided_frames 鐨勫厓绱犳牸寮忎负 {"frame": np.ndarray, "frame_number": int, "ts": float}銆?
        
        Args:
            center_timestamp: 濡傛灉鎻愪緵锛屽垯鍙?浣跨敤璇ユ椂闂存埑鍓嶅悗鐨勫抚锛堥粯璁ぢ?10绉掞級
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
        
        # 馃幆 濡傛灉鎻愪緵浜哻enter_timestamp锛屽彧淇濈暀璇ユ椂闂村墠鍚庣殑甯?
        if center_timestamp is not None:
            import os
            window_before = float(os.environ.get("MULTIMODAL_BEFORE_SECONDS", "15"))
            window_after = float(os.environ.get("MULTIMODAL_AFTER_SECONDS", "15"))
            
            start_ts = center_timestamp - window_before
            end_ts = center_timestamp + window_after
            
            filtered_frames = [f for f in clip_frames if start_ts <= f[2] <= end_ts]
            # 修复 f-string 乱码导致的 SyntaxError
            print(f"   🎞️ [视频帧筛选] 原始帧数: {len(clip_frames)}, 筛选后: {len(filtered_frames)}, 窗口: 前{window_before}s + 后{window_after}s = {window_before + window_after}s")
            if filtered_frames:
                clip_frames = filtered_frames
            else:
                # 濡傛灉杩囨护鍚庝负绌猴紝鍙?鑳芥槸鏃堕棿绐楀お绐勬垨甯уお灏戯紝灏濊瘯鎵炬渶杩戠殑甯?
                closest_frame = min(clip_frames, key=lambda f: abs(f[2] - center_timestamp))
                clip_frames = [closest_frame]
            
            if len(clip_frames) < 2: # 纭?淇濊嚦灏戞湁涓ゅ抚鎵嶈兘褰㈡垚瑙嗛??
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
                '-preset', 'slow',  # slow鎻愪緵鏇村ソ鐨勫帇缂╄川閲忥紙姣攎edium鎱?浣嗚川閲忔洿楂橈級
                '-crf', '15',  # 闄嶄綆鍒?15鑾峰緱鏇撮珮鐢昏川锛?0-51锛岃秺灏忚秺濂斤紝18鏄?榛樿?ら珮璐ㄩ噺锛?
                '-b:v', '5M',  # 鏄庣‘璁剧疆鐮佺巼涓?5Mbps锛岀‘淇濋珮璐ㄩ噺
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
        """閲嶇疆浼氳瘽 (鏂扮殑褰曞埗)"""
        self.moments = []
        self.start_time = time.time()
        self.frame_count = 0
        self.last_ai_analysis_time = 0
        self.ai_analysis_buffer = []
        self.stats = {"user_anchors": 0, "ai_detected": 0, "total_moments": 0}
    print("🔄 KeyMomentsManager 会话已重置")

    def delete_frame_from_timeline(self, person_id: int, frame_num: int):
        """鍒犻櫎 timeline 涓?鐨勭壒瀹氬抚
        
        鐩?鍓嶅疄鐜颁负绌烘搷浣滐紝鍥犱负 timeline 鏁版嵁鏉ヨ嚜 face_db.detection_history
        鐪熸?ｇ殑鍒犻櫎鍦? FaceDatabase.delete_person() 涓?澶勭悊
        """
        # Timeline 鏁版嵁鏉ヨ嚜 face_db锛屾墍浠ュ垹闄ょ敱鍚庣??鍦? face_db 涓?澶勭悊
        print(f"鉁? 宸蹭粠 timeline 鍒犻櫎 Frame {frame_num}")
    
    def delete_moment(self, moment_id: str):
        """鍒犻櫎涓�涓?鍏抽敭鏃跺埢
        
        Args:
            moment_id: 鍏抽敭鏃跺埢 ID
        """
        # 浠庡垪琛ㄤ腑鍒犻櫎
        self.moments = [m for m in self.moments if m.id != moment_id]
        
        # 鍒犻櫎瀵瑰簲鐨勬枃浠?
        moment_dir = self.moments_dir / moment_id
        if moment_dir.exists():
            import shutil
            shutil.rmtree(moment_dir)
            print(f"鉁? 宸插垹闄ゅ叧閿?鏃跺埢 {moment_id}")
        
        # 閲嶆柊淇濆瓨
        self._save_moments()
        print(f"鉁? 宸叉洿鏂板叧閿?鏃跺埢鏁版嵁")
    
    # ============================================================
    # 馃敶 鐢ㄦ埛鏍囪?? (The Anchor)
    # ============================================================
    
    def add_frame_to_buffer(self, frame, frame_number: int):
        """
        灏嗗抚娣诲姞鍒扮紦鍐插尯 (姣忓抚璋冪敤)
        
        Args:
            frame: 褰撳墠甯? (numpy array)
            frame_number: 甯у彿
        """
        import cv2
        
        # 閽堝?归珮鍒嗚鲸鐜?(濡?8083澶氭憚)浼樺寲锛氬?傛灉鍒嗚鲸鐜囪繃楂橈紝缂╁皬瀛樺偍浠ラ槻姝?OOM鍜屽崱椤?
        frame_to_store = frame
        h, w = frame.shape[:2]
        if w > 1920:
            scale = 1920 / w
            new_h = int(h * scale)
            frame_to_store = cv2.resize(frame, (1920, new_h))
        
        # 浣跨敤 JPEG 鍘嬬缉瀛樺偍浠ヨ妭鐪佸唴瀛? (1280x720 raw=2.7MB, jpeg~=200KB)
        # 闄嶄綆 quality 鍒? 80 浠ヨ繘涓�姝ヤ紭鍖?
        success, buffer = cv2.imencode('.jpg', frame_to_store, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if not success:
            return
            
        with self.buffer_lock:
            # 瀛樺偍鏍煎紡: (jpeg_buffer, frame_num, timestamp)
            self.frame_buffer.append((buffer, frame_number, time.time()))
            # 淇濇寔缂撳啿鍖哄ぇ灏忓湪闄愬埗鍐?
            while len(self.frame_buffer) > self.buffer_max_frames:
                if len(self.frame_buffer) % 500 == 0:
                     print(f"   🧠 [BUFFER] Popping frame! Size={len(self.frame_buffer)}, Max={self.buffer_max_frames}")
                self.frame_buffer.pop(0)
    
    def add_audio_frame_to_buffer(self, audio_chunk: bytes, timestamp: float = None):
        """
        灏嗛煶棰戝抚娣诲姞鍒扮紦鍐插尯 (瀹炴椂璋冪敤)
        
        Args:
            audio_chunk: 闊抽?戞暟鎹?鍧? (bytes)
            timestamp: 鏃堕棿鎴? (濡傛灉涓篘one锛屼娇鐢ㄥ綋鍓嶆椂闂?)
        """
        if timestamp is None:
            timestamp = time.time()
        
        with self.audio_buffer_lock:
            self.audio_buffer.append((audio_chunk, timestamp))
            # 淇濇寔闊抽?戠紦鍐插尯澶у皬鍦ㄩ檺鍒跺唴锛?25绉掗煶棰? @16kHz 16-bit锛?
            # 浼拌?℃瘡绉? 16000 * 2 = 32KB
            while len(self.audio_buffer) > self.buffer_max_frames * 32768:  
                self.audio_buffer.pop(0)
    
    def _add_audio_to_video(self, moment_id: str, video_path: str, frame_number: int, video_duration: float,
                            frame=None, center_timestamp: float = None, window_before: float = None, window_after: float = None):
        """
        娣诲姞闊抽?戝埌瑙嗛?戯紙楹﹀厠椋庢垨瑙嗛?戞簮锛?
        
        Args:
            moment_id: 鍏抽敭鏃跺埢ID
            video_path: 瑙嗛?戣矾寰?
            frame_number: 甯у彿
            video_duration: 瑙嗛?戞椂闀?
            frame: 鍏抽敭甯у浘鍍? (鐢ㄤ簬AI鍒嗘瀽)
        """
        import math

        # 浼樺厛浣跨敤楹﹀厠椋庡綍鍒剁殑闊抽??
        if self.microphone_recorder:
            print("   🎤 从麦克风保存音频...")
            # 涓洪伩鍏嶆埅鏂?锛屽彇 ceil + 1 绉?
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
                print(f"   鈿狅笍 楹﹀厠椋庨煶棰戜繚瀛樺け璐ワ紝璺宠繃璇?闊宠浆鏂囧瓧")
        # 鍚﹀垯浠庤?嗛?戞簮鎻愬彇闊抽??
        elif self.audio_source and Path(self.audio_source).exists():
            print("   🎧 从视频源提取音频...")
            self._extract_and_merge_audio_async(moment_id, video_path, frame_number, video_duration, frame)
        else:
            print(f"   鈿狅笍 鏃犲彲鐢ㄩ煶棰戞簮 (楹﹀厠椋?: {bool(self.microphone_recorder)}, 瑙嗛?戞簮: {self.audio_source})")
            print(f"   鈩癸笍 瑙嗛?戝皢鍙?鍖呭惈鐢婚潰锛岃??闊宠浆鏂囧瓧鍔熻兘涓嶅彲鐢?")
            # 鍗充娇鏃犻煶棰戯紝涔熷簲瑙﹀彂绾?瑙嗚?堿I鍒嗘瀽 / 妯℃嫙鎸夐敭鍚庣殑澶勭悊
            print("   🤖 触发无音频模式的 AI 分析...")
            if frame is not None:
                # 鏀惧湪鍚庡彴绾跨▼閬垮厤闃诲??
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
                print(f"      瑙嗛??: {temp_video}")
                print(f"      闊抽??: {audio_path}")
                print(f"      杈撳嚭: {video_path}")
                
                # 鍏抽敭鐐癸細涓嶈?佺敤 -shortest锛屽惁鍒欎細鎶婅緭鍑鸿?佸埌鏇寸煭鐨勯偅涓�璺?锛屽?艰嚧鈥滃彧璇嗗埆涓�鍗?/瑙嗛?戝彉鐭?鈥濄�?
                # 杩欓噷鍥哄畾杈撳嚭涓鸿?嗛?戞椂闀匡紝骞剁敤 apad 鍦ㄩ渶瑕佹椂缁欓煶棰戣ˉ闈欓煶銆?
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
                    # apad 璁╅煶棰戜笉瓒虫椂琛ラ潤闊筹紝-t 鍥哄畾杈撳嚭鏃堕暱
                    cmd += ['-af', f"apad=pad_dur={max(0.1, duration):.3f}", '-t', f"{duration:.3f}"]
                cmd += ['-movflags', '+faststart', str(video_path)]
                
                print(f"   🧾 [DEBUG] FFmpeg命令: {' '.join(cmd)}")
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                
                if result.returncode == 0:
                    print(f"   鉁? [鍚庡彴] 闊抽?戝悎骞舵垚鍔?")
                    temp_video.unlink()
                    Path(audio_path).unlink()  # 娓呯悊涓存椂闊抽?戞枃浠?
                    
                    # 馃帳馃摴 瑙﹀彂璇?闊宠浆鏂囧瓧 + AI澶氭ā鎬佸垎鏋?
                    print(f"   馃帳 寮�濮嬭??闊宠浆鏂囧瓧鍜孉I鍒嗘瀽...")
                    self._process_video_with_multimodal_analysis(moment_id, video_path, frame)
                else:
                    print(f"   鉂? [鍚庡彴] FFmpeg杩斿洖閿欒??鐮?: {result.returncode}")
                    print(f"   鉂? stderr: {result.stderr}")
                    print(f"   鈿狅笍 [鍚庡彴] 鎭㈠?嶅師瑙嗛??")
                    temp_video.rename(video_path)
            except Exception as e:
                print(f"   鈿狅笍 [鍚庡彴] 闊抽?戝悎骞跺紓甯?: {e}")
                import traceback
                traceback.print_exc()
        
        thread = threading.Thread(target=merge_task, daemon=True)
        thread.start()
    
    def _extract_and_merge_audio_async(self, moment_id: str, video_path: str, frame_number: int, video_duration: float, frame=None):
        """
        鍚庡彴寮傛?ユ彁鍙栬?嗛?戞枃浠朵腑鐨勯煶棰戝苟鍚堝苟鍒板凡淇濆瓨鐨勮?嗛?戯紝瀹屾垚鍚庤繘琛岃??闊宠浆鏂囧瓧鍜孉I鍒嗘瀽
        
        Args:
            moment_id: 鍏抽敭鏃跺埢ID
            video_path: 宸蹭繚瀛樼殑瑙嗛?戣矾寰?
            frame_number: 甯у彿锛堢敤浜庤?＄畻鏃堕棿浣嶇疆锛?
            video_duration: 瑙嗛?戞椂闀?
            frame: 鍏抽敭甯у浘鍍? (鐢ㄤ簬AI鍒嗘瀽)
        """
        def merge_task():
            try:
                import subprocess
                
                # 璁＄畻鍦ㄦ簮瑙嗛?戜腑鐨勪綅缃?锛堝敖閲忎娇鐢ㄧ湡瀹? fps锛?
                assumed_fps = self.video_fps if (self.video_fps and self.video_fps > 1e-6) else 30.0
                source_start_time = frame_number / float(assumed_fps)
                
                print(f"   馃攰 [鍚庡彴] 浠庢簮瑙嗛?戞彁鍙栭煶棰? (甯?{frame_number} = {source_start_time:.1f}s)...")
                
                # 涓存椂闊抽?戞枃浠?
                audio_path = Path(video_path).parent / f"{moment_id}_audio.m4a"
                output_path = Path(video_path).parent / f"{moment_id}_with_audio.mp4"
                
                # 姝ラ??1: 浠庢簮瑙嗛?戞彁鍙栭煶棰?
                cmd_extract = [
                    'ffmpeg', '-y', '-loglevel', 'error',
                    '-ss', str(source_start_time),
                    '-t', str(video_duration + 1),  # 澶氭彁鍙?1绉掍綔涓虹紦鍐?
                    '-i', str(self.audio_source),
                    '-vn',
                    '-map', '0:a:0?',
                    '-c:a', 'aac', '-b:a', '128k',
                    str(audio_path)
                ]
                
                result = subprocess.run(cmd_extract, timeout=30)

                def _maybe_backfill_transcript_from_source():
                    """褰撳悎骞堕煶棰戝け璐ユ椂锛屼粛灏濊瘯浠庢簮瑙嗛?戠洿鎺ユ彁鍙? WAV 骞跺仛 ASR锛岄伩鍏? transcript 涓虹┖銆?"""
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
                                # 鍙?鍦ㄧ己澶辨椂鍥炲～锛岄伩鍏嶈?嗙洊鏇村畬鏁寸粨鏋?
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
                    print(f"   鈿狅笍 [鍚庡彴] 闊抽?戞彁鍙栧け璐?")
                    _maybe_backfill_transcript_from_source()
                    return
                
                print(f"   鉁? [鍚庡彴] 闊抽?戞彁鍙栨垚鍔?")
                
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
                    print(f"   鉁? [鍚庡彴] 闊抽?戝悎骞舵垚鍔?")
                    
                    # 馃帳馃摴 瑙﹀彂璇?闊宠浆鏂囧瓧 + AI澶氭ā鎬佸垎鏋?
                    print(f"   馃帳 寮�濮嬭??闊宠浆鏂囧瓧鍜孉I鍒嗘瀽...")
                    self._process_video_with_multimodal_analysis(moment_id, video_path, frame)
                else:
                    print(f"   鈿狅笍 [鍚庡彴] 闊抽?戝悎骞跺け璐ワ紝淇濈暀鍘熻?嗛??")
                    _maybe_backfill_transcript_from_source()
                    
            except subprocess.TimeoutExpired:
                print(f"   鈿狅笍 [鍚庡彴] 闊抽?戝?勭悊瓒呮椂")
            except Exception as e:
                print(f"   鈿狅笍 [鍚庡彴] 闊抽?戝?勭悊寮傚父: {e}")
        
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
            duration: 鎻愬彇鏃堕暱 (绉?)
            output_audio_path: 杈撳嚭闊抽?戞枃浠惰矾寰?
            
        Returns:
            True 濡傛灉鎴愬姛, False 濡傛灉澶辫触
        """
        try:
            import subprocess
            
            # 浣跨敤 ffmpeg 鎻愬彇闊抽??
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
                if file_size > 100:  # 鑷冲皯100瀛楄妭
                    print(f"   馃攰 闊抽?戝凡鎻愬彇: {Path(output_audio_path).name} ({file_size} bytes)")
                    return True
            
            return False
            
        except Exception as e:
            print(f"   鈿狅笍 闊抽?戞彁鍙栧け璐?: {e}")
            return False
    
    def _merge_audio_to_video(self, video_path: str, audio_path: str, 
                              output_path: str) -> bool:
        """
        灏嗛煶棰戣建閬撳悎骞跺埌瑙嗛?戞枃浠?
        
        Args:
            video_path: 瑙嗛?戞枃浠惰矾寰? (鍚?瑙嗛?戜絾鏃犻煶棰?)
            audio_path: 闊抽?戞枃浠惰矾寰?
            output_path: 杈撳嚭鏂囦欢璺?寰?
            
        Returns:
            True 濡傛灉鎴愬姛, False 濡傛灉澶辫触
        """
        try:
            import subprocess
            
            # 浣跨敤 ffmpeg 鍚堝苟闊宠?嗛??
            ffmpeg_cmd = [
                'ffmpeg', '-y',
                '-i', str(video_path),
                '-i', str(audio_path),
                '-c:v', 'copy',  # 鐩存帴澶嶅埗瑙嗛?戞祦
                '-c:a', 'aac',   # 閲嶆柊缂栫爜闊抽?戜负AAC
                '-shortest',  # 浠ヨ緝鐭?鐨勬祦闀垮害涓哄噯
                '-n',  # 涓嶈?嗙洊
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
                print(f"   馃幀 闊宠?嗛?戝凡鍚堝苟: {Path(output_path).name} ({merged_size} bytes)")
                
                # 鍒犻櫎涓存椂鏂囦欢
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
            moment_id: 鍏抽敭鏃跺埢ID
            clip_duration_before: 鏍囪?版椂鍒诲墠淇濈暀鐨勭?掓暟 (榛樿??10绉?)
            clip_duration_after: 鏍囪?版椂鍒诲悗绛夊緟鐨勭?掓暟 (闇�瑕佸紓姝ュ疄鐜?)
            
        Returns:
            (video_path, duration) 鎴? (None, 0) 濡傛灉澶辫触
        """
        import cv2
        
        with self.buffer_lock:
            if len(self.frame_buffer) < 10:  # 鑷冲皯闇�瑕?10甯?
                print(f"   鈿狅笍 甯х紦鍐插尯涓嶈冻锛屾棤娉曠敓鎴愯?嗛?? ({len(self.frame_buffer)} 甯?)")
                return None, 0
            
            # 馃攳 璋冭瘯锛氭墦鍗癰uffer鐘舵�?
            if self.frame_buffer:
                buffer_start_ts = self.frame_buffer[0][2]
                buffer_end_ts = self.frame_buffer[-1][2]
                buffer_span = buffer_end_ts - buffer_start_ts
                print(f"   馃攳 [DEBUG] Buffer鐘舵�?: {len(self.frame_buffer)} 甯?, 鏃堕棿璺ㄥ害: {buffer_span:.1f}绉?")
                print(f"   馃攳 [DEBUG] Buffer鑼冨洿: [{buffer_start_ts:.2f}, {buffer_end_ts:.2f}]")
            
            # 鑾峰彇浠? center_timestamp 涓轰腑蹇冪殑甯э紙榛樿?ょ敤褰撳墠鏃跺埢锛?
            center_ts = float(center_timestamp) if isinstance(center_timestamp, (int, float)) else time.time()
            start_ts = center_ts - float(clip_duration_before)
            end_ts = center_ts + float(clip_duration_after)
            
            print(f"   馃攳 [DEBUG] 鐩?鏍囩獥鍙?: [{start_ts:.2f}, {end_ts:.2f}], 涓?蹇?: {center_ts:.2f}")
            print(f"   馃攳 [DEBUG] 绐楀彛瀹藉害: {clip_duration_before:.1f}s (鍓?) + {clip_duration_after:.1f}s (鍚?) = {clip_duration_before + clip_duration_after:.1f}s")
            
            clip_frames = []
            for frame_buf, frame_num, ts in self.frame_buffer:
                if start_ts <= ts <= end_ts:
                    # 瑙ｇ爜 JPEG
                    frame = cv2.imdecode(frame_buf, cv2.IMREAD_COLOR)
                    if frame is not None:
                        clip_frames.append((frame, frame_num, ts))
            
            print(f"   馃攳 [DEBUG] 绛涢�夌粨鏋?: 鏀堕泦鍒? {len(clip_frames)} 甯?")
        
        if len(clip_frames) == 0:
            # timestamp涓嶅湪buffer鑼冨洿锛堝巻鍙叉椂鍒诲凡杩囨湡锛夛紝浣跨敤褰撳墠鏃堕棿閲嶈瘯
            print(f"   鈿狅笍 鍘嗗彶timestamp涓嶅湪buffer鑼冨洿锛屼娇鐢ㄥ綋鍓嶆椂闂撮噸鏂扮瓫閫?")
            center_ts = time.time()
            start_ts = center_ts - float(clip_duration_before)
            end_ts = center_ts + float(clip_duration_after)
            
            print(f"   馃攳 [RETRY] 鏂扮獥鍙?: [{start_ts:.2f}, {end_ts:.2f}], 涓?蹇?: {center_ts:.2f}")
            
            # 鍏堟敹闆嗗綋鍓嶅彲鐢ㄧ殑甯?
            for frame_buf, frame_num, ts in self.frame_buffer:
                if start_ts <= ts <= end_ts:
                    # 瑙ｇ爜 JPEG
                    frame = cv2.imdecode(frame_buf, cv2.IMREAD_COLOR)
                    if frame is not None:
                        clip_frames.append((frame, frame_num, ts))
            
            print(f"   馃攳 [RETRY] 鍒濇?ョ瓫閫夌粨鏋?: 鏀堕泦鍒? {len(clip_frames)} 甯?")
            
            # 濡傛灉闇�瑕佸悗缁?甯э紝绛夊緟buffer鏀堕泦
            if clip_duration_after > 0 and len(clip_frames) < 1800:
                wait_seconds = float(clip_duration_after)
                print(f"   鈴? 绛夊緟 {wait_seconds:.0f}绉? 鏀堕泦鍚庣画甯?...")
                time.sleep(wait_seconds)
                
                # 閲嶆柊绛涢�夛紝鍖呭惈鏂版敹闆嗙殑甯?
                clip_frames = []
                with self.buffer_lock:
                    for frame_buf, frame_num, ts in self.frame_buffer:
                        if start_ts <= ts <= end_ts:
                            frame = cv2.imdecode(frame_buf, cv2.IMREAD_COLOR)
                            if frame is not None:
                                clip_frames.append((frame, frame_num, ts))
                
                print(f"   馃攳 [RETRY] 绛夊緟鍚庣瓫閫夌粨鏋?: 鏀堕泦鍒? {len(clip_frames)} 甯?")
        
        if len(clip_frames) < 10:
            # 濡傛灉浠嶇劧涓嶅?燂紙buffer鏈?韬?澶?灏忥級锛屼娇鐢ㄦ渶杩戜竴娈电紦鍐插尯鍏滃簳
            print(f"   鈿狅笍 绛涢�夊抚鏁颁粛鐒朵笉瓒? ({len(clip_frames)} < 10)锛屼娇鐢ㄦ渶杩?300甯у厹搴?")
            # 鍚屾牱闇�瑕佽В鐮?
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
            
            # 鑾峰彇甯у昂瀵?
            first_frame = clip_frames[0][0]
            h, w = first_frame.shape[:2]
            
            # 璁＄畻瀹為檯甯х巼
            time_span = clip_frames[-1][2] - clip_frames[0][2]
            actual_fps = len(clip_frames) / time_span if time_span > 0 else 30
            actual_fps = min(max(actual_fps, 15), 60)  # 闄愬埗鍦?15-60fps
            
            video_duration = len(clip_frames) / actual_fps
            
            # 鏂规硶1: 灏濊瘯浣跨敤 ffmpeg 绠￠亾鐩存帴杈撳嚭 H.264 MP4
            try:
                # 浣跨敤 ffmpeg 浠庡師濮嬪抚鏁版嵁鍒涘缓瑙嗛??
                ffmpeg_cmd = [
                    'ffmpeg', '-y',
                    '-f', 'rawvideo', '-pix_fmt', 'bgr24',
                    '-s', f'{w}x{h}', '-r', str(int(actual_fps)),
                    '-i', 'pipe:0',
                    '-c:v', 'libx264',
                    '-preset', 'slow',  # slow鎻愪緵鏇村ソ鐨勫帇缂╄川閲?
                    '-crf', '15',  # 楂樼敾璐?锛堜笌LLM璇嗗埆淇濇寔涓�鑷达級
                    '-b:v', '5M',  # 5Mbps鐮佺巼纭?淇濋珮璐ㄩ噺
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
                    print(f"   馃幀 瑙嗛?戠墖娈靛凡淇濆瓨 (H.264): {video_filename} ({len(clip_frames)}甯?, {video_duration:.1f}绉?)")
                    
                    # 馃攰 娣诲姞闊抽??
                    self._add_audio_to_video(moment_id, str(video_path), frame_number, video_duration, frame)
                    
                    return str(video_path), video_duration
                    
            except Exception as e:
                print(f"   鈿狅笍 ffmpeg 鏂规硶澶辫触: {e}")
            
            # 鏂规硶2: 鍥為��鍒? OpenCV 淇濆瓨 (鍙?鑳芥棤娉曞湪娴忚?堝櫒鎾?鏀?)
            fourcc = cv2.VideoWriter_fourcc(*'avc1')  # 灏濊瘯 H.264
            writer = cv2.VideoWriter(str(video_path), fourcc, actual_fps, (w, h))
            
            if not writer.isOpened():
                # 濡傛灉 avc1 涓嶅彲鐢?锛屼娇鐢? mp4v
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                writer = cv2.VideoWriter(str(video_path), fourcc, actual_fps, (w, h))
            
            for frame, _, _ in clip_frames:
                writer.write(frame)
            
            writer.release()
            
            print(f"   馃幀 瑙嗛?戠墖娈靛凡淇濆瓨 (OpenCV): {video_filename} ({len(clip_frames)}甯?, {video_duration:.1f}绉?)")
            
            # 馃攰 娣诲姞闊抽??
            self._add_audio_to_video(moment_id, str(video_path), frame_number, video_duration, frame)
            
            return str(video_path), video_duration
            
        except Exception as e:
            print(f"   鉂? 淇濆瓨瑙嗛?戝け璐?: {e}")
            import traceback
            traceback.print_exc()
            return None, 0
    
    def _add_audio_to_clip_async(self, moment_id: str, video_path: str, 
                                  start_timestamp: float, duration: float, frame_number: int = 0):
        """
        鍦ㄥ悗鍙扮嚎绋嬩腑浠庢簮瑙嗛?戜腑鎻愬彇闊抽?戝苟娣诲姞鍒板叧閿?鏃跺埢瑙嗛??
        姝ゅ嚱鏁板湪鍚庡彴杩愯?岋紝涓嶉樆濉炰富瑙嗛?戝?勭悊绾跨▼
        
        Args:
            moment_id: 鍏抽敭鏃跺埢ID
            video_path: 瑙嗛?戞枃浠惰矾寰? (涓嶅惈闊抽??)
            start_timestamp: 瑙嗛?戠墖娈靛湪绯荤粺涓?鐨勫紑濮嬫椂闂存埑 (鐢ㄤ簬鏃ュ織)
            duration: 瑙嗛?戠墖娈垫椂闀? (绉?)
            frame_number: 鍏抽敭鏃跺埢鐨勫抚鍙? (鐢ㄤ簬璁＄畻瑙嗛?戜腑鐨勪綅缃?)
        """
        try:
            print(f"   馃幀 [鍚庡彴绾跨▼寮�濮媇 moment_id={moment_id}, audio_source={self.audio_source}")
            
            if not self.audio_source:
                print(f"   鈿狅笍 [鍚庡彴绾跨▼] audio_source 涓? None")
                return
                
            if not Path(self.audio_source).exists():
                print(f"   鈿狅笍 [鍚庡彴绾跨▼] 闊抽?戞簮涓嶅瓨鍦?: {self.audio_source}")
                return
            
            # 璁＄畻鍦ㄦ簮瑙嗛?戜腑鐨勮捣濮嬫椂闂? (鍩轰簬甯у彿鍜屽敖閲忕湡瀹炵殑FPS)
            assumed_fps = self.video_fps if (self.video_fps and self.video_fps > 1e-6) else 30.0
            source_start_time = frame_number / float(assumed_fps)
            
            # 鎻愬彇闊抽??
            audio_path = Path(video_path).parent / f"{moment_id}_audio.m4a"
            
            print(f"   馃幀 [鍚庡彴] 姝ｅ湪浠庢簮瑙嗛?戞彁鍙栭煶棰? (甯?{frame_number} = {source_start_time:.1f}s)...")
            
            audio_extracted = self._extract_audio_from_video(
                self.audio_source,
                source_start_time,
                duration + 1,  # 澶氭彁鍙?1绉掍綔涓虹紦鍐?
                str(audio_path)
            )
            
            if not audio_extracted:
                print(f"   鈿狅笍 [鍚庡彴] 鏈?鑳戒粠婧愯?嗛?戞彁鍙栭煶棰?")
                return
            
            # 鍚堝苟闊宠?嗛??
            temp_video_path = Path(video_path).parent / f"{moment_id}_temp.mp4"
            if Path(video_path).exists():
                Path(video_path).rename(temp_video_path)
            
            print(f"   馃敆 [鍚庡彴] 姝ｅ湪鍚堝苟闊宠?嗛??...")
            audio_merged = self._merge_audio_to_video(
                str(temp_video_path),
                str(audio_path),
                video_path
            )
            
            if not audio_merged:
                # 濡傛灉鍚堝苟澶辫触, 鎭㈠?嶅師濮嬭?嗛??
                print(f"   鈿狅笍 [鍚庡彴] 鍚堝苟澶辫触锛屼娇鐢ㄦ棤闊抽?戠増鏈?")
                try:
                    if temp_video_path.exists():
                        temp_video_path.rename(video_path)
                except:
                    pass
            else:
                print(f"   鉁? [鍚庡彴] 闊抽?戝凡鎴愬姛鍚堝苟")
            
            print(f"   鉁? [鍚庡彴绾跨▼瀹屾垚]")
            
        except Exception as e:
            print(f"   鈿狅笍 [鍚庡彴绾跨▼寮傚父] {e}")
            import traceback
            traceback.print_exc()
    
    def _add_audio_to_clip(self, moment_id: str, video_path: str, 
                           start_timestamp: float, duration: float, frame_number: int = 0):
        """
        鍦ㄥ悗鍙扮嚎绋嬩腑寮傛?ユ坊鍔犻煶棰戣建閬? (涓嶉樆濉炰富绾跨▼)
        """
        print(f"   馃攰 [涓荤嚎绋媇 _add_audio_to_clip 琚?璋冪敤锛宮oment_id={moment_id}")
        thread = threading.Thread(
            target=self._add_audio_to_clip_async,
            args=(moment_id, video_path, start_timestamp, duration, frame_number),
            daemon=True
        )
        print(f"   馃攰 [涓荤嚎绋媇 鍚?鍔ㄥ悗鍙扮嚎绋?...")
        thread.start()
        print(f"   馃攰 [涓荤嚎绋媇 鍚庡彴绾跨▼宸插惎鍔?")

    def mark_user_anchor(self, frame, frame_number: int, 
                         person_count: int = 0, track_ids: List[int] = None,
                         user_note: str = "", transcript: str = "", context_transcript: str = "",
                         source: str = None) -> KeyMoment:
        """
        鐢ㄦ埛鎸変笅鎸夐挳鏍囪?板綋鍓嶆椂鍒? (0.5绉掓剰鍥鹃敋瀹?)
        淇濆瓨鍓? KEY_MOMENT_BEFORE_SECONDS 绉掔殑瑙嗛?戯紝骞跺惎鍔ㄥ悗鍙颁换鍔＄瓑寰? KEY_MOMENT_AFTER_SECONDS 绉?
        
        Args:
            frame: 褰撳墠甯у浘鍍? (numpy array)
            frame_number: 甯у彿
            person_count: 褰撳墠浜烘暟
            track_ids: 娲昏穬鐨勮拷韪狪D
            user_note: 鐢ㄦ埛澶囨敞
            transcript: 鏈�杩戠殑璇?闊宠浆鏂囧瓧鍐呭?癸紙鐢ㄤ簬鍗虫椂灞曠ず锛?
            context_transcript: 鏇撮暱鐨勫巻鍙蹭笂涓嬫枃锛堢敤浜庡悗缁瑼I鍒嗘瀽锛屽彲鑳借??鎴?鏂?锛?
            source: 鏉ユ簮 (榛樿?? USER_ANCHOR, 鍙?鎸囧畾 AI_DETECTED)
            
        Returns:
            鍒涘缓鐨? KeyMoment 瀵硅薄
        """
        import cv2
        
        timestamp = time.time()
        duration = timestamp - self.start_time
        time_str = self._format_time(duration)
        
        # 鐢熸垚鍞?涓�ID
        moment_id = f"anchor_{int(timestamp)}_{frame_number}"
        
        try:
            # 淇濆瓨鍏抽敭甯?
            frame_filename = f"{moment_id}.jpg"
            frame_path = self.moments_dir / frame_filename
            print(f"   馃敡 [DEBUG] Saving keyframe to {frame_path}")
            
            # 浣跨敤楂樼敾璐ㄤ繚瀛?
            cv2.imwrite(str(frame_path), frame, [cv2.IMWRITE_JPEG_QUALITY, 95])
            
            # 楠岃瘉鏂囦欢鏄?鍚︾敓鎴?
            if not frame_path.exists() or frame_path.stat().st_size == 0:
                print(f"   鉂? [ERROR] Keyframe file creation failed: {frame_path}")
        except Exception as e:
            print(f"   鉂? [ERROR] Failed to save keyframe image: {e}")
            import traceback
            traceback.print_exc()

        # 涓鸿?ュ叧閿?鏃跺埢淇濆瓨涓婁笅鏂囷紙鎸夐敭鍘熷洜 + 鍘嗗彶杞?鍐欙級锛屼緵鍚庣画AI鍒嗘瀽璇诲彇
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

        # 鍒涘缓鍏抽敭鏃跺埢 (瑙嗛?戣矾寰勬殏绌猴紝鐢卞悗鍙扮嚎绋嬬敓鎴?)
        try:
            moment = KeyMoment(
                id=moment_id,
                timestamp=timestamp,
                frame_number=frame_number,
                source=moment_source,
                frame_path=str(frame_path),
                video_path="",  # 鏆傛椂涓虹┖
                video_duration=0.0,
                time_str=time_str,
                duration_seconds=duration,
                user_note=user_note,
                transcript=transcript,  # 淇濆瓨璇?闊宠浆鏂囧瓧
                person_count=person_count,
                track_ids=track_ids or []
            )
            
            self.moments.append(moment)
            self.stats["user_anchors"] += 1
            self.stats["total_moments"] += 1
            print(f"   ✅ [DEBUG] Moment object created and appended. Total: {len(self.moments)}")
            
        except Exception as e:
            print(f"   鉂? [ERROR] Failed to create KeyMoment object: {e}")
            import traceback
            traceback.print_exc()
            return None
        
        # 绔嬪嵆淇濆瓨涓�娆★紝纭?淇濆墠绔?鑳界珛鍗冲埛鍑哄崱鐗囧苟瑙﹀彂鐗规晥
        self._save_moments()
        
        print(f"馃敶 鐢ㄦ埛鏍囪?板叧閿?鏃跺埢: {time_str} (甯? {frame_number})")
        if user_note:
            print(f"   馃摑 澶囨敞: {user_note}")
        if transcript:
            print(f"   馃帳 瀹炴椂璇?闊崇墖娈?: {transcript[:50]}...")
        
        # 馃幀 鍚?鍔ㄥ悗鍙扮嚎绋?: 1.淇濆瓨鍒濆?嬭?嗛?? -> 2.绛夊緟鎵╁睍 -> 3.瑙﹀彂AI鍒嗘瀽
        def async_video_processing():
            # 1. 淇濆瓨鍓? KEY_MOMENT_BEFORE_SECONDS 绉掔殑瑙嗛?戠墖娈?
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
                    self._save_moments() # 鏇存柊瑙嗛?戣矾寰?
            except Exception as e:
                print(f"   鉂? 鍒濆?嬭?嗛?戠敓鎴愬け璐?: {e}")

            # 2. 绛夊緟 after 绉掑悗鐢熸垚鍖呭惈鍚庢?电殑瀹屾暣瑙嗛??
            print(f"   鈴? {KEY_MOMENT_AFTER_SECONDS:.0f}绉掑悗灏嗘墿灞曞畬鏁磋?嗛?戝苟杩涜?孉I鍒嗘瀽...")
            time.sleep(float(KEY_MOMENT_AFTER_SECONDS))  # 绛夊緟鏀堕泦鍚庣画甯?
            self._extend_video_with_after_frames(moment_id, timestamp, frame.copy())
        
        processing_thread = threading.Thread(target=async_video_processing, daemon=True)
        processing_thread.start()
        
        return moment

    def _extend_video_with_after_frames(self, moment_id: str, original_timestamp: float, frame=None):
        """
        寤惰繜璋冪敤锛氬悎骞舵爣璁版椂鍒诲墠鍚庡悇10绉掔殑瑙嗛??
        
        Args:
            moment_id: 鍏抽敭鏃跺埢ID
            original_timestamp: 鍘熷?嬫爣璁扮殑鏃堕棿鎴?
            frame: 鍏抽敭甯у浘鍍? (鐢ㄤ簬鍚庣画AI鍒嗘瀽)
        """
        import cv2
        
        print(f"   馃幀 [瀹屾暣瑙嗛?戞墿灞昡 寮�濮嬪?勭悊 moment_id={moment_id}, timestamp={original_timestamp:.2f}")
        
        try:
            with self.buffer_lock:
                before_s = float(KEY_MOMENT_BEFORE_SECONDS)
                after_s = float(KEY_MOMENT_AFTER_SECONDS)

                # 璇婃柇鏃ュ織
                print(f"   馃敡 [DEBUG] 甯х紦鍐插尯鎬诲ぇ灏?: {len(self.frame_buffer)} 甯?")
                if len(self.frame_buffer) > 0:
                    buffer_start_ts = self.frame_buffer[0][2]
                    buffer_end_ts = self.frame_buffer[-1][2]
                    buffer_span = buffer_end_ts - buffer_start_ts
                    print(f"   馃敡 [DEBUG] 缂撳啿鍖烘椂闂磋法搴?: {buffer_span:.1f}绉?")
                    print(f"   馃敡 [DEBUG] 鐩?鏍囩獥鍙?: [{original_timestamp - before_s:.1f}, {original_timestamp + after_s:.1f}] = {before_s + after_s:.0f}绉?")
                
                # 鑾峰彇鏍囪?版椂鍒诲墠鍚庣獥鍙ｇ殑甯?
                clip_frames = []
                for frame_buf, frame_num, ts in self.frame_buffer:
                    if original_timestamp - before_s <= ts <= original_timestamp + after_s:
                        # 瑙ｇ爜 JPEG
                        frame = cv2.imdecode(frame_buf, cv2.IMREAD_COLOR)
                        if frame is not None:
                            clip_frames.append((frame, frame_num, ts))
                
                print(f"   馃敡 [DEBUG] 绐楀彛鍐呮敹闆嗗埌甯ф暟: {len(clip_frames)} 甯?")
                
                if len(clip_frames) < 30:  # 鑷冲皯闇�瑕?1绉?
                    print(f"   鈿狅笍 甯т笉瓒筹紝鏃犳硶鎵╁睍瑙嗛?? ({len(clip_frames)} 甯?). Buffer Range: {buffer_start_ts:.1f}-{buffer_end_ts:.1f}, Target: {original_timestamp - before_s:.1f}-{original_timestamp + after_s:.1f}")
                    return
            
            # 鐢熸垚鏂拌?嗛?戣矾寰?
            video_filename = f"{moment_id}.mp4"
            video_path = self.moments_dir / video_filename
            
            # 璁＄畻甯х巼鍜岃?嗛?戞椂闀?
            if len(clip_frames) >= 2:
                time_span = clip_frames[-1][2] - clip_frames[0][2]
                actual_fps = len(clip_frames) / time_span if time_span > 0 else 30
                # 涓嶉檺鍒舵渶灏廎PS锛屼繚鎸佺湡瀹炴椂闂磋法搴?
                actual_fps = min(max(actual_fps, 5), 60)  # 鏈�灏?5fps锛屼繚鎸?30绉掕?嗛?戝畬鏁?
                print(f"   馃敡 [DEBUG] 瀹為檯鏃堕棿璺ㄥ害: {time_span:.2f}绉?")
                print(f"   馃敡 [DEBUG] 璁＄畻FPS: {actual_fps:.1f}")
                # 浣跨敤瀹為檯鏃堕棿璺ㄥ害浣滀负瑙嗛?戞椂闀匡紝鑰屼笉鏄?璁＄畻鍊?
                video_duration = time_span
            else:
                actual_fps = 30
                video_duration = len(clip_frames) / actual_fps
            
            print(f"   馃敡 [DEBUG] 瑙嗛?戞椂闀?: {video_duration:.2f}绉? ({len(clip_frames)}甯? @ {actual_fps:.1f}fps)")
            
            # 鑾峰彇甯у昂瀵?
            first_frame = clip_frames[0][0]
            h, w = first_frame.shape[:2]
            
            # 浣跨敤 ffmpeg 缂栫爜
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
            print(f"   鉂? 鎵╁睍瑙嗛?戝け璐?: {e}")
            import traceback
            traceback.print_exc()
    
    # ============================================================
    # 馃?? AI 鑷?鍔ㄨ瘑鍒? (Smart Mirror)
    # ============================================================
    
    def update_frame(self, frame, frame_number: int, 
                    person_count: int = 0, track_ids: List[int] = None):
        """
        姣忓抚璋冪敤, 鐢ㄤ簬 AI 鍒嗘瀽缂撳啿
        
        Args:
            frame: 褰撳墠甯?
            frame_number: 甯у彿
            person_count: 浜烘暟
            track_ids: 杩借釜ID
        """
        self.frame_count = frame_number
        current_time = time.time()
        
        # 妫�鏌ユ槸鍚﹂渶瑕佽繘琛? AI 鍒嗘瀽 (姣?3.5鍒嗛挓)
        if current_time - self.last_ai_analysis_time >= self.ai_interval_seconds:
            if person_count > 0:  # 鍙?鍦ㄦ湁浜烘椂鍒嗘瀽
                # 鈿狅笍 鍏抽敭锛氬厛鏇存柊鏃堕棿鎴冲啀瑙﹀彂鍒嗘瀽锛岀‘淇濆垏鐗囦箣闂存棤閬楁紡
                # 鍗充娇澶勭悊鑰楁椂30绉掞紝涓嬩竴娆′篃鏄?浠庢湰娆＄殑210绉掑悗瑙﹀彂锛岃�岄潪澶勭悊瀹屾垚鍚庣殑210绉?
                self.last_ai_analysis_time = current_time
                # 寮傛?ヨ繘琛? AI 鍒嗘瀽
                self._trigger_ai_analysis(frame.copy(), frame_number, person_count, track_ids or [])
    
    def _trigger_ai_analysis(self, frame, frame_number: int, 
                             person_count: int, track_ids: List[int]):
        """瑙﹀彂 AI 鍒嗘瀽 (寮傛??)"""
        if not self.qwen_available:
            return
        
        # 鍦ㄥ悗鍙扮嚎绋嬫墽琛屽垎鏋?
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
        
        # 鍦ㄥ悗鍙扮嚎绋嬫墽琛屽垎鏋?
        thread = threading.Thread(
            target=self._analyze_moment_with_ai,
            args=(frame, moment_id, transcript),
            daemon=True
        )
        thread.start()
    
    def _analyze_frame_with_ai(self, frame, frame_number: int,
                               person_count: int, track_ids: List[int]):
        """
        浣跨敤 Qwen-VL 鍒嗘瀽甯? (绾?瑙嗚??)
        
        鍩轰簬缂栫爜妗嗘灦璇嗗埆鍗忎綔瀛︿範琛屼负
        """
        import cv2
        
        try:
            # 浼樺寲锛氱缉灏忓浘鍍忎互鍔犲揩浼犺緭鍜屽垎鏋? (Max width 1280)
            frame_for_ai = frame
            h, w = frame.shape[:2]
            if w > 1280:
                scale = 1280 / w
                new_h = int(h * scale)
                frame_for_ai = cv2.resize(frame, (1280, new_h))

            # 灏嗗抚缂栫爜涓? base64
            _, buffer = cv2.imencode('.jpg', frame_for_ai, [cv2.IMWRITE_JPEG_QUALITY, 85])
            image_base64 = base64.b64encode(buffer).decode('utf-8')

            prompt = """浣犳槸涓�浣嶅崗浣滃?︿範鐮旂┒涓撳?躲�傚垎鏋愯繖寮犲崗浣滃?︿範鍦烘櫙鐨勫浘鐗囥�?

璇锋牴鎹?浠ヤ笅瀹屾暣缂栫爜妗嗘灦璇嗗埆琛屼负锛?

鈿狅笍 鍏抽敭鍘熷垯锛?
1. 鍙?鏈夊綋纭?瀹炶?傚療鍒般�愭槑鏄剧殑鍗忎綔浜掑姩銆戯紙濡傝?ㄨ?恒�佹墜鎸囧睆骞曘�佸叡鍚屾搷浣溿�佺溂绁炰氦娴侊級鏃讹紝鎵嶆爣璁颁负 is_key_moment: true銆?
2. 濡傛灉鐢婚潰鍙?鏄?澶у?跺悇鑷?鐪嬬數鑴戙�佺帺鎵嬫満銆佸彂鍛嗭紝鎴栬�呮病鏈変汉锛岃?风洿鎺ヨ繑鍥? "is_key_moment": false銆備笉瑕佸己琛屽?楃敤浠ヤ笅鍒嗙被锛?

=================================================================
缁村害涓�锛氬弬涓庝笌娌夋蹈 (Engagement) - 鎶曞叆鏃堕棿銆佹儏鎰熺姸鎬佷笌蹇冩祦浣撻獙
=================================================================

銆怑ng-Flow 娌夋蹈/蹇冩祦銆?
- Engage: [R1]鎺㈢储鎬у洶鎯?(濂藉??/鍥版儜), [R1]鐪熷疄鎬х‘璁?
- Investigate: [R1]闂?棰樺懡鍚?(閲嶆瀯闂?棰?), [R1]淇℃伅渚涚粰
- Act: [R0]鍏疯薄鍖栬?屽姩(鍒朵綔鑽夊浘/妯″瀷), [R1]鏀硅繘鎰忓浘

銆怑ng-Emo 鎯呮劅/姘涘洿銆?
- Engage: [R0]鎯呮劅杩炴帴(鐮村啺), [R0]灏婇噸纭?璁?(鑲?瀹氳?傜偣), [R1]鐩镐簰鍗拌瘉
- Investigate: [R0]璧勬簮鎺ュ叆, [R0]鐗╃悊闄?浼?, [R1]閭�璇锋�濊�?
- Act: [R0]瀹炶川鍗忓姪, [R1]璧炵編璇勪环, [R1]闆嗕綋鑷?璞?

銆怑ng-Strug 鎸ｆ墡/鍧氭寔銆?
- Engage: [R1]璇嗗埆鍥伴毦, [R1]澶勭悊闅鹃??
- Investigate: [R1]璇嗗埆鍒嗘??, [R1]璁惧畾闄愬埗
- Act: [R1]娼滃姏璇勪及, [R2]楠岃瘉鍋囪??

=================================================================
缁村害浜岋細涓诲姩鎬т笌鎰忓浘 (Initiative) - 璁惧畾鐩?鏍囥�佸?绘眰鍙嶉?堛�佹壙鎷呴?庨櫓
=================================================================

銆怚nit-Goal 鐩?鏍?/璁″垝銆?
- Engage: [R1]鐩?鏍囬敋瀹?, [R1]璁″垝鍒跺畾, [R1]婢勬竻缁嗚妭
- Investigate: [R1]瑙掕壊鍒嗛厤, [R1]娴佺▼寤鸿??, [R2]璁ょ煡浠ｇ悊
- Act: [R2]鏋勬�濆彂鏁?(鏁伴噺浼樺厛), [R2]鍐崇瓥鍙犲姞, [R2]濡ュ崗闄堣堪

銆怚nit-Feed 鍙嶉??/楠岃瘉銆?
- Engage: [R1]瑙傜偣闄堣堪, [R1]鐞嗚В鎯虫硶
- Investigate: [R2]鐞嗙敱璐ㄧ枒, [R2]婢勬竻鍒嗘??, [R2]缁煎悎鍒嗘瀽
- Act: [R2]杩?浠ｄ慨鏀?, [R2]浜嬪疄娴嬭瘯, [R2]缁忛獙娴嬭瘯

銆怚nit-Risk 椋庨櫓/浜夎?恒�?
- Engage: [R2]瀵规瘮鎯虫硶, [R2]鐤?鐙傛兂娉?
- Investigate: [R2]鎺㈢储涓嶄竴鑷?, [R2]璁鸿瘉鎺ㄧ悊, [R2]鎵瑰垽鎸戞垬
- Act: [R3]瓒呰秺鑷?鎴?(鏂扮患鍚?), [R2]璁烘嵁鏉冮噸, [R3]妗嗘灦閲嶆瀯

=================================================================
缁村害涓夛細绀句細鏀?鏋? (Social Scaffolding) - 浜掑姪銆佹縺鍙戠伒鎰熴�佺墿鐞嗚繛鎺?
=================================================================

銆怱oc-Ind 鐙?绔?/鑷?璇磋嚜璇濄�?
- [R0]鐙?绔嬮檲杩?(Monologue), [R0]骞宠?岀爺涔?, [R0]骞宠?屽埗浣?(Co-acting)

銆怱oc-Help 浜掑姪/鏁欏?︺�?
- Engage: [R0]鍏崇郴纭?璁?, [R1]寤鸿??鍔濆憡
- Investigate: [R1]娑堥櫎鐩插尯, [R1]淇℃伅鎻愪緵, [R1]鏂囩尞鏀?鎸?
- Act: [R0]鐩存帴浠诲姟鍗忓姪, [R1]绉?鏋佸弬涓?, [R3]瀵圭О璐＄尞

銆怱oc-Insp 婵�鍙?/鍏变韩銆?
- Engage: [R1]鍗拌瘉渚嬪瓙, [R2]涓板瘜鐜?澧?
- Investigate: [R2]鏁版嵁鏀?鎸?, [R2]鏉冨▉鎵╁睍, [R2]瑙ｉ噴缁嗗寲
- Act: [R3]鍚?鍙戝彂鐜?("A ha!"), [R3]缁煎悎瑙傜偣, [R3]鏁村悎闅愬柣

銆怱oc-Conn 杩炴帴/鍗忓悓銆?
- Engage: [R0]鐗╃悊鍦ㄥ満, [R1]鍏变韩璐ｄ换
- Investigate: [R1]淇冭繘鐞嗚В, [R0]鍚屼即鍏崇郴
- Act: [R3]璐＄尞涓撻暱, [R3]鍏卞悓寤烘瀯, [R2]鍏磋叮鍙犲姞

=================================================================
缁村害鍥涳細鐞嗚В鐨勫彂灞? (Understanding) - 椤挎偀銆佽В閲婄瓥鐣ャ�佸簲鐢ㄧ煡璇?
=================================================================

銆怳nd-Exp 瑙ｉ噴/鎺ㄦ紨銆?
- Engage: [R1]瀹氫箟闂?棰?, [R1]闂?棰樺懡鍚?
- Investigate: [R1]鍙傝�冪粡楠?, [R2]瑙ｉ噴杩炴帴, [R2]寮曠敤鏀?鎸?
- Act: [R2]瑙ｉ噴鏂规??, [R2]鍗忓晢鏈?璇?, [R2]缁嗗寲瑙傜偣

銆怳nd-Aha 椤挎偀/绐佺牬銆戔瓙鍏抽敭
- Engage: [R3]鐪熷疄鍩虹煶, [R3]娲炲療鍔涚敓鎴?
- Investigate: [R3]鍙戠幇鏃跺埢"I find it!"猸?, [R3]鍙?鏀硅繘鎬濇兂
- Act: [R3]鏂扮殑缁煎悎猸?, [R3]搴旂敤鏂扮煡, [R3]鍏冭?ょ煡鏀瑰彉猸?

銆怳nd-Strive 娣辨�?/鍐呭寲銆?
- Engage: [R1]璁ょ煡鍥版儜, [R2]绮剧?炵敓娲?
- Investigate: [R2]涓?浜烘�濊�?, [R2]妫�鏌ュ疄璺?, [R2]璇嗗埆闂?棰?
- Act: [R2]鍙嶅悜鍙嶉??, [R2]璁ょ煡鍥惧紡娴嬭瘯, [R2]闅愬惈鎬у喅绛?

=================================================================
鍙嶆�濆眰绾?: R0(鍩虹?�) / R1(鍒濇??) / R2(娣卞害) / R3(楂橀樁绐佺牬)
闃舵??: Engage(瀹氫箟) / Investigate(瀛︿範) / Act(鍒朵綔)
=================================================================

璇蜂互JSON鏍煎紡杩斿洖:
{
    "is_key_moment": true/false,
    "importance": 0.0-1.0,
    "reflection_level": "R0|R1|R2|R3",
    "phase": "Engage|Investigate|Act",
    "dimension": "Engagement|Initiative|Social|Understanding",
    "behavior_code": "濡? Eng-Flow",
    "specific_behavior": "濡? [R2]璁鸿瘉鎺ㄧ悊",
    "description": "绠�鐭?鎻忚堪姝ｅ湪鍙戠敓浠�涔?",
    "observable_behaviors": ["鍙?瑙傚療琛屼负1"],
    "emotions": ["鎯呯华鐘舵�?"],
    "tags": ["鏍囩??1"]
}

鍙?杩斿洖JSON锛屼笉瑕佸叾浠栧唴瀹广�?"""

            result_text = self._run_vision_llm(
                image_base64=image_base64,
                prompt=prompt,
                model_override=self.vision_model_fast,
                temperature=0.3,
                max_tokens=500
            )

            # 瑙ｆ瀽 JSON
            # 绉婚櫎鍙?鑳界殑 markdown 浠ｇ爜鍧楁爣璁?
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
            
            result = json.loads(result_text)
            
            # 寮哄埗蹇?鐓фā寮?
            force_snapshot = (os.environ.get("MULTIMODAL_FORCE_SNAPSHOT", "0") or "0").strip() == "1"
            
            # 濡傛灉鏄?鍏抽敭鏃跺埢锛岃?板綍锛堥槇鍊?0.3锛屾彁楂樼伒鏁忓害锛?
            # 鎴栬�? forced
            is_key = result.get("is_key_moment", False)
            importance = result.get("importance", 0)
            
            if (is_key and importance > 0.3) or force_snapshot:
                if force_snapshot:
                    print("鈿狅笍 Visual analysis negative, but forced snapshot enabled.")
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
                print(f"馃?? AI Analysis (Frame {frame_number}): Non-key moment (Importance: {result.get('importance', 0):.2f})")
                
        except Exception as e:
            print(f"鈿狅笍 AI Analysis failed: {e}")
    
    def _record_ai_moment(self, frame, frame_number: int,
                          person_count: int, track_ids: List[int],
                          ai_result: Dict[str, Any]):
        """璁板綍 AI 璇嗗埆鐨勫叧閿?鏃跺埢"""
        import cv2
        
        timestamp = time.time()
        duration = timestamp - self.start_time
        time_str = self._format_time(duration)
        
        # 鐢熸垚鍞?涓�ID
        moment_id = f"ai_{int(timestamp)}_{frame_number}"
        
        # 淇濆瓨鎴?鍥?
        image_filename = f"{moment_id}.jpg"
        image_path = self.moments_dir / image_filename
        cv2.imwrite(str(image_path), frame)
        
        # 鎻愬彇 AI 鍒嗘瀽缁撴灉
        description = ai_result.get("description", "AI璇嗗埆鐨勫叧閿?鏃跺埢")
        tags = ai_result.get("tags", [])
        importance = ai_result.get("importance", 0.5)
        # 鍏煎?逛笉鍚? prompt 鐨勫瓧娈?
        if not tags:
            tags = ai_result.get("tags", [])
        
        # 鍒涘缓鍏抽敭鏃跺埢
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

        # 鍏堣惤鐩? moment锛岀‘淇濆悗鍙扮嚎绋嬫洿鏂版椂鍙?鎵惧埌
        self.moments.append(moment)
        self.stats["ai_detected"] += 1
        self.stats["total_moments"] += 1
        self._save_moments()

        # 馃幀 涓庢墜鍔ㄦ爣璁颁繚鎸佷竴鑷?: 鍏堜繚瀛樺墠15绉掕?嗛?戯紝鐒跺悗寤惰繜鐢熸垚瀹屾暣30绉掕?嗛??
        # 绗?涓�闃舵??: 淇濆瓨鍓?15绉掕?嗛??
        print(f"   馃幀 [AI瑙嗛?慮 绗?涓�闃舵??: 寮�濮嬩繚瀛樺墠{KEY_MOMENT_BEFORE_SECONDS:.0f}绉掕?嗛??...")
        video_path, video_duration = self._save_video_clip(
            moment_id=moment_id,
            clip_duration_before=float(KEY_MOMENT_BEFORE_SECONDS),  # 15绉?
            frame_number=frame_number,
            frame=frame,
            center_timestamp=timestamp  # 浣跨敤AI妫�娴嬫椂鍒讳綔涓轰腑蹇?
        )
        if video_path:
            moment.video_path = video_path
            moment.video_duration = video_duration
            self._save_moments()
            print(f"   鉁? [AI瑙嗛?慮 绗?涓�闃舵?靛畬鎴?: {video_duration:.1f}绉掕?嗛?戝凡淇濆瓨")
        else:
            print(f"   鈿狅笍 AI鍏抽敭鏃跺埢瑙嗛?戠敓鎴愬け璐?: {moment_id}")
            return  # 濡傛灉绗?涓�闃舵?靛け璐ワ紝涓嶇户缁?
        
        # 绗?浜岄樁娈?: 鍚?鍔ㄥ悗鍙扮嚎绋嬶紝绛夊緟15绉掑悗鐢熸垚鍖呭惈鍚庢?电殑瀹屾暣瑙嗛??
        print(f"   馃幀 [AI瑙嗛?慮 绗?浜岄樁娈?: 鍚?鍔ㄥ欢杩熺嚎绋嬶紝{KEY_MOMENT_AFTER_SECONDS:.0f}绉掑悗鐢熸垚瀹屾暣瑙嗛??")
        # 绗?浜岄樁娈?: 鍚?鍔ㄥ悗鍙扮嚎绋嬶紝绛夊緟15绉掑悗鐢熸垚鍖呭惈鍚庢?电殑瀹屾暣瑙嗛??
        print(f"   馃幀 [AI瑙嗛?慮 绗?浜岄樁娈?: 鍚?鍔ㄥ欢杩熺嚎绋嬶紝{KEY_MOMENT_AFTER_SECONDS:.0f}绉掑悗鐢熸垚瀹屾暣瑙嗛??")
        
        # 浣跨敤闂?鍖呮崟鑾峰綋鍓嶆墍闇�鍙橀噺
        def delayed_video_extension(mid, ts, frm):
            try:
                print(f"   鈴? [AI瑙嗛?戝欢杩焆 绾跨▼寮�濮? (moment_id={mid}), 绛夊緟 {KEY_MOMENT_AFTER_SECONDS:.0f} 绉?...")
                time.sleep(float(KEY_MOMENT_AFTER_SECONDS))
                print(f"   馃幀 [AI瑙嗛?戝欢杩焆 鍞ら啋! 寮�濮嬬敓鎴愬畬鏁磋?嗛??: {mid}")
                self._extend_video_with_after_frames(mid, ts, frm)
            except Exception as e:
                print(f"   鉂? [AI瑙嗛?戝欢杩焆 绾跨▼寮傚父: {e}")
        
        # 浼犻�掑弬鏁伴伩鍏嶉棴鍖呭彉閲忔崟鑾烽棶棰?
        extend_thread = threading.Thread(
            target=delayed_video_extension, 
            args=(moment_id, timestamp, frame.copy()),
            daemon=True
        )
        extend_thread.start()
        print(f"   鉁? [AI瑙嗛?慮 寤惰繜绾跨▼宸插惎鍔? (thread_id={extend_thread.ident}, moment_id={moment_id})")
        
        print(f"馃?? AI 璇嗗埆鍏抽敭鏃跺埢: {time_str}")
        print(f"   📝 {description[:60]}...")
        print(f"   🏷️ 标签: {', '.join(tags[:3])}")
        print(f"   ⭐ 重要性: {importance:.2f}")
        print(f"   🎞️ 视频 (前{KEY_MOMENT_BEFORE_SECONDS:.0f}秒): {video_duration:.1f}秒")
        print(f"   ⏳ {KEY_MOMENT_AFTER_SECONDS:.0f}秒后将生成完整视频并进行AI分析...")
    
    def _process_video_with_multimodal_analysis(self, moment_id: str, video_path: str, frame=None):
        """浠庡畬鏁磋?嗛?戜腑鎻愬彇闊抽?戝苟杩涜?岃??闊宠浆鏂囧瓧锛岀劧鍚庤繘琛屽?氭ā鎬丄I鍒嗘瀽
        
        Args:
            moment_id: 鍏抽敭鏃跺埢ID
            video_path: 鍚?闊抽?戠殑瀹屾暣瑙嗛?戣矾寰?
            frame: 鍏抽敭甯у浘鍍?
        """
        from pathlib import Path
        import subprocess

        def _ai_step(step: int, total: int, msg: str):
            # 缁堢??绮剧畝浣嗏�滄瘡涓�姝ラ兘瑕佹湁鈥濃�斺�旂粺涓�鎴愬崟琛屾?ラ?よ緭鍑?
            print(f"   馃З [AI澶勭悊] {step}/{total} {msg}")
        
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

            _ai_step(1, total_steps, "鍑嗗??/鍗犱綅")

            # 璇诲彇涓婁笅鏂囷紙鍙?鑳藉寘鍚? after 绉掕ˉ榻愮殑绐楀彛杞?鍐欙級
            _ai_step(2, total_steps, "璇诲彇 context.txt")
            context_text = ""
            context_transcript = ""
            try:
                ctx_path = Path(video_path).parent / f"{moment_id}_context.txt"
                if ctx_path.exists():
                    context_text = ctx_path.read_text(encoding="utf-8")
                    marker = "=== transcript_context ==="
                    if marker in context_text:
                        # 鍙栨渶鍚庝竴娆″啓鍏ョ殑 transcript_context锛岄伩鍏嶉噸澶嶈拷鍔犲?艰嚧瑙ｆ瀽鍒版棫鍐呭??
                        context_transcript = context_text.rsplit(marker, 1)[1].strip()
                    print(f"   馃?? [AI澶勭悊] context.txt 鎵惧埌锛屼笂涓嬫枃杞?鍐?: {len(context_transcript)} 瀛?")
                else:
                    print(f"   馃?? [AI澶勭悊] {moment_id}_context.txt 涓嶅瓨鍦? (浠呬娇鐢ㄥ叏灞�KB)")

                # GLOBAL KB: 璇诲彇鍏ㄥ眬 context.txt (鐭ヨ瘑搴?)
                # 璺?寰?: integrated_data/../context.txt -> 1215zzh/context.txt
                try:
                    global_kb_path = self.data_dir.parent / "context.txt"
                    if global_kb_path.exists():
                        kb_content = global_kb_path.read_text(encoding="utf-8").strip()
                        if kb_content:
                            print(f"   馃摎 [AI澶勭悊] 鍔犺浇鍏ㄥ眬鐭ヨ瘑搴? (context.txt): {len(kb_content)} 瀛?")
                            # 灏? KB 鎷兼帴鍒? context_text 鍓嶉潰鎴栧悗闈?
                            context_text = f"銆愬叏灞�鐭ヨ瘑搴?/鑳屾櫙淇℃伅銆慭n{kb_content}\n\n" + context_text
                    else:
                        print(f"   鈿狅笍 [AI澶勭悊] 鍏ㄥ眬鐭ヨ瘑搴? context.txt 涓嶅瓨鍦?: {global_kb_path}")
                except Exception as e:
                    print(f"   鈿狅笍 [AI澶勭悊] 璇诲彇鍏ㄥ眬KB澶辫触: {e}")
            except Exception as e:
                print(f"   馃?? [AI澶勭悊] 璇诲彇 context.txt 澶辫触: {e}")
                context_text = ""
                context_transcript = ""

            # 榛樿?ょ?佺敤鈥滀紭鍏堜娇鐢ㄤ笂涓嬫枃杞?鍐欌�濓紝鏀逛负寮哄埗瀵光�滃畬鏁村垏鐗囪?嗛?戔�濆仛 ASR銆?
            # 鍘熷洜锛氫笂涓嬫枃杞?鍐欏彧鍖呭惈鎸夐敭鍓嶇殑鍘嗗彶锛岃�岃?嗛?戝垏鐗囧寘鍚?鎸夐敭鍚庣殑鈥滄湭鏉モ�?15绉掋�傚彧鏈夐噸鍋? ASR 鎵嶈兘鎷垮埌杩欓儴鍒嗗唴瀹圭殑鏂囧瓧銆?
            prefer_ctx_asr = os.environ.get("KEY_MOMENT_PREFER_CONTEXT_TRANSCRIPT", "0").strip().lower() in {"1", "true", "yes"}
            _ai_step(3, total_steps, f"鍒ゅ畾杞?鍐欐潵婧?: prefer_ctx_asr={int(prefer_ctx_asr)} ctx_len={len((context_transcript or '').strip())}")
            if prefer_ctx_asr and context_transcript:
                _ai_step(4, total_steps, "璺宠繃鎻愬彇闊抽??/浜屾??ASR(鐩存帴鐢ㄤ笂涓嬫枃杞?鍐?)")
                # 鏇存柊 moment.transcript锛堥�氬父鏇村畬鏁达級
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
                        _ai_step(9, total_steps, "璺宠繃AI鍒嗘瀽(鏃犳湁鏁堣??闊?)")
                        self._mark_moment_no_audio(moment_id, "涓婁笅鏂囪浆鍐欎负绌?/鏃犳湁鏁堣??闊?")
                    else:
                        _ai_step(9, total_steps, "璋冪敤瑙嗚??/澶氭ā鎬丄I鍒嗘瀽")
                        self._analyze_moment_with_ai(frame, moment_id, context_transcript, context_text=context_text)
                else:
                    _ai_step(9, total_steps, "璺宠繃AI鍒嗘瀽(鏃爁rame)")

                # 琛ラ綈鈥滄瘡涓�姝ラ兘瑕佹湁鈥濈殑杈撳嚭锛氫腑闂存?ラ?ゆ爣璁颁负璺宠繃
                _ai_step(5, total_steps, "璺宠繃(宸茬敤涓婁笅鏂囪浆鍐?)")
                _ai_step(6, total_steps, "璺宠繃(宸茬敤涓婁笅鏂囪浆鍐?)")
                _ai_step(7, total_steps, "璺宠繃(宸茬敤涓婁笅鏂囪浆鍐?)")
                _ai_step(8, total_steps, "璺宠繃(宸茬敤涓婁笅鏂囪浆鍐?)")
                return

            # 闄愭祦锛氶伩鍏嶅?氫釜鍏抽敭鏃跺埢骞惰?屾妸绯荤粺鎷栨參锛堝挨鍏? FireRedASR/LLM 閮戒細鍚冭祫婧愶級
            _ai_step(4, total_steps, "绛夊緟閲嶄换鍔′俊鍙烽噺")
            with self._heavy_job_sema:
                _ai_step(5, total_steps, "鎻愬彇闊抽??(ffmpeg)")
                import subprocess
                from pathlib import Path
            
                # 1. 鎻愬彇闊抽?戠敤浜庤??闊宠浆鏂囧瓧
                audio_for_asr_path = Path(video_path).parent / f"{moment_id}_asr.wav"
            
                cmd_extract_audio = [
                    'ffmpeg', '-y', '-i', str(video_path),
                    '-vn', '-acodec', 'pcm_s16le', '-ar', '16000', '-ac', '1',
                    str(audio_for_asr_path)
                ]
            
                print(f"   馃幍 鎻愬彇闊抽?戠敤浜庤??闊宠瘑鍒?...")
                result = subprocess.run(cmd_extract_audio, capture_output=True, timeout=30)
                _ai_step(6, total_steps, f"ffmpeg rc={result.returncode} wav_exists={int(audio_for_asr_path.exists())}")
            
                if result.returncode != 0 or not audio_for_asr_path.exists():
                    print(f"   鈿狅笍 闊抽?戞彁鍙栧け璐ワ紝璺宠繃璇?闊宠浆鏂囧瓧")
                    self._mark_moment_no_audio(moment_id, "Video segment has no audio track/audio extraction failed")
                    return
            
                # 2. 璋冪敤ASR杩涜?岃??闊宠浆鏂囧瓧
                _ai_step(7, total_steps, "ASR杞?鍐?")
                transcript = self._transcribe_audio(audio_for_asr_path)
            
                # 娓呯悊涓存椂闊抽?戞枃浠?
                try:
                    audio_for_asr_path.unlink()
                except:
                    pass
            
            # 3. 鏇存柊moment鐨則ranscript瀛楁??
            _ai_step(8, total_steps, f"鍥炲啓moment transcript(asr_len={len((transcript or '').strip())})")
            for moment in self.moments:
                if moment.id == moment_id:
                    moment.transcript = transcript
                    moment.asr_provider = (self._last_asr_meta.get("provider") or "")
                    moment.asr_model = (self._last_asr_meta.get("model") or "")
                    moment.asr_model_dir = (self._last_asr_meta.get("model_dir") or "")
                    print(f"   鉁? 璇?闊宠浆鏂囧瓧瀹屾垚: {len(transcript)} 瀛?")
                    # if transcript:
                    #     print(f"   馃摑 鍐呭??: {transcript[:80]}...")
                    break
            
            self._save_moments()

            if self._transcript_is_missing(transcript):
                _ai_step(9, total_steps, "璺宠繃AI鍒嗘瀽(ASR涓虹┖/鏃犳湁鏁堣??闊?)")
                self._mark_moment_no_audio(moment_id, "ASR is empty/no valid speech")
                return
            
            # 4. 杩涜?屽?氭ā鎬丄I鍒嗘瀽 (瑙嗛??+璇?闊?)
            _ai_step(9, total_steps, "璋冪敤瑙嗚??/澶氭ā鎬丄I鍒嗘瀽")
            if frame is not None:
                self._analyze_moment_with_ai(frame, moment_id, transcript, context_text=context_text)
            else:
                _ai_step(9, total_steps, "璺宠繃AI鍒嗘瀽(鏃爁rame)")
            
        except Exception as e:
            print(f"   鈿狅笍 澶氭ā鎬佸?勭悊澶辫触: {e}")
            import traceback
            traceback.print_exc()
    
    def _transcribe_audio(self, audio_path: Path) -> str:
        """
        浣跨敤DashScope杩涜?岄煶棰戣浆鏂囧瓧 (鍙傝�冨疄鏃禔SR鐨勬垚鍔熷疄鐜?)
        
        Args:
            audio_path: 闊抽?戞枃浠惰矾寰? (WAV鏍煎紡, 16kHz, 鍗曞０閬?)
            
        Returns:
            杞?鍐欐枃鏈?
        """
        try:
            # ============================================================
            # ASR 鍚庣??閫夋嫨锛氭敮鎸佹湰鍦? FireRedASR锛堢?荤嚎锛夋垨 DashScope (浜戠??)
            # 鐢ㄦ埛鍋忓ソ锛歈wen (DashScope)
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
                    print(f"   鈿狅笍 FireRedASR 妯″瀷鐩?褰曚笉瀛樺湪: {model_dir}")
                    # 鍏佽?稿洖閫�鍒? DashScope
                else:
                    try:
                        # 鍏抽敭锛氬?嶇敤妯″瀷锛岄伩鍏嶆瘡娆? from_pretrained 瀵艰嚧闀挎椂闂村崱椤?/楂樺欢杩?
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
                        print(f"   鈿狅笍 FireRedASR 杞?鍐欏け璐?(灏嗗洖閫�DashScope): {e}")
                # FireRedASR 鏈?浜у嚭缁撴灉鏃讹紝缁х画璧? DashScope 鍒嗘敮

            # DashScope / Qwen 鍒嗘敮
            self._last_asr_meta = {
                "provider": "dashscope",
                "model": "qwen-audio-turbo",
                "model_dir": "",
            }

            # 妫�鏌?DashScope鍙?鐢ㄦ�?
            if not self.api_key:
                print("   鈿狅笍 DashScope API Key鏈?閰嶇疆")
                return ""
            
            # 鏂规硶1: 浣跨敤 Recognition API (鍚屾?ヨ皟鐢?) - 鍙傝�? realtime_asr.py
            try:
                import dashscope
                from dashscope.audio.asr import Recognition
                
                dashscope.api_key = self.api_key
                
                print(f"   馃帳 姝ｅ湪杩涜?岃??闊宠浆鏂囧瓧 (鏂囦欢澶у皬: {audio_path.stat().st_size} bytes, DashScope)...")
                
                # ASR妯″瀷浼樺厛绾у垪琛?锛堝彧浣跨敤宸茬‘璁ゅ彲鐢ㄧ殑妯″瀷锛?
                models_to_try = [
                    'paraformer-realtime-v2',      # 瀹炴椂ASR妯″瀷锛堜富鍔涳級
                    'paraformer-realtime-8k-v2',   # 8k閲囨牱鐜囩増鏈?锛堝?囩敤锛?
                ]
                
                result = None
                last_error = None
                successful_model = None
                
                for model_name in models_to_try:
                    try:
                        print(f"   馃攧 灏濊瘯妯″瀷: {model_name}")
                        
                        # 鍒涘缓璇嗗埆瀵硅薄 (涓? realtime_asr.py 淇濇寔涓�鑷?)
                        recognition = Recognition(
                            model=model_name,
                            format='wav',       # 鏂囦欢鏍煎紡
                            sample_rate=16000,  # 閲囨牱鐜?
                            callback=None       # 鍚屾?ヨ皟鐢ㄤ笉闇�瑕佸洖璋?
                        )
                        
                        # 鍚屾?ヨ皟鐢?,鐩存帴浼犲叆鏂囦欢璺?寰?
                        result = recognition.call(str(audio_path))
                        
                        # 妫�鏌ョ粨鏋?
                        if result and hasattr(result, 'output') and result.output:
                            successful_model = model_name
                            print(f"   鉁? 妯″瀷 {model_name} 璇嗗埆鎴愬姛")
                            break
                        elif result and hasattr(result, 'status_code'):
                            if result.status_code == 200:
                                # 鐘舵�佹垚鍔熶絾缁撴灉涓虹┖锛屽皾璇曚笅涓�涓?妯″瀷
                                print(f"   鈿狅笍 妯″瀷 {model_name} 杩斿洖鎴愬姛浣嗙粨鏋滀负绌猴紝灏濊瘯涓嬩竴涓?妯″瀷")
                                last_error = f"妯″瀷 {model_name} 鏃犺瘑鍒?缁撴灉"
                                continue  # 缁х画灏濊瘯涓嬩竴涓?妯″瀷
                            else:
                                error_msg = getattr(result, 'message', f'Status {result.status_code}')
                                last_error = error_msg
                                print(f"   鈿狅笍 妯″瀷 {model_name} 澶辫触: {error_msg}")
                                continue
                        else:
                            last_error = f"妯″瀷 {model_name} 杩斿洖绌虹粨鏋?"
                            print(f"   鈿狅笍 {last_error}")
                            continue
                            
                    except Exception as e:
                        last_error = str(e)
                        print(f"   鈿狅笍 妯″瀷 {model_name} 寮傚父: {e}")
                        continue

                if successful_model:
                    self._last_asr_meta = {
                        "provider": "dashscope",
                        "model": str(successful_model),
                        "model_dir": "",
                    }
                
                # 鎻愬彇杞?鍐欐枃鏈?
                transcript_parts = []
                if result and hasattr(result, 'output') and result.output:
                    output = result.output
                    
                    # 馃攳 璋冭瘯杈撳嚭缁撴瀯
                    print(f"   馃攳 [DEBUG] Output type: {type(output)}")
                    if isinstance(output, dict):
                        print(f"   馃攳 [DEBUG] Output keys: {list(output.keys())}")
                        print(f"   馃攳 [DEBUG] Output content: {output}")
                    elif hasattr(output, '__dict__'):
                        print(f"   馃攳 [DEBUG] Output attrs: {vars(output)}")
                    else:
                        print(f"   馃攳 [DEBUG] Output: {output}")
                    
                    # 澶勭悊涓嶅悓鐨勮緭鍑烘牸寮?
                    if isinstance(output, dict):
                        # 鏍煎紡1: sentence (鍒楄〃褰㈠紡 - paraformer-realtime-v2)
                        if 'sentence' in output:
                            sentence = output['sentence']
                            # sentence 鏄?鍒楄〃,鍖呭惈澶氫釜鍙ュ瓙瀵硅薄
                            if isinstance(sentence, list):
                                for sent_obj in sentence:
                                    if isinstance(sent_obj, dict) and 'text' in sent_obj:
                                        text = sent_obj['text'].strip()
                                        if text:
                                            transcript_parts.append(text)
                            # 鍏滃簳:鍗曚釜鍙ュ瓙瀵硅薄
                            elif isinstance(sentence, dict) and 'text' in sentence:
                                text = sentence['text'].strip()
                                if text:
                                    transcript_parts.append(text)
                            elif isinstance(sentence, str):
                                text = sentence.strip()
                                if text:
                                    transcript_parts.append(text)
                        
                        # 鏍煎紡2: sentences (澶氬彞)
                        elif 'sentences' in output:
                            for sentence in output['sentences']:
                                if isinstance(sentence, dict) and 'text' in sentence:
                                    text = sentence['text'].strip()
                                    if text:
                                        transcript_parts.append(text)
                        
                        # 鏍煎紡3: text (鐩存帴鏂囨湰)
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
                    print(f"   鉁? 璇?闊宠浆鏂囧瓧鎴愬姛: {len(transcript)} 瀛?")
                    # print(f"   馃摑 璇嗗埆鍐呭??: {transcript[:100]}{'...' if len(transcript) > 100 else ''}")
                    return transcript
                else:
                    print(f"   鈿狅笍 Recognition API 杩斿洖绌虹粨鏋?")
                    if last_error:
                        print(f"   馃搵 璇婃柇: {last_error}")
                    
            except ImportError as e:
                print(f"   鈿狅笍 dashscope.audio.asr 鏈?瀹夎??: {e}")
            except Exception as e:
                print(f"   鈿狅笍 璇?闊宠浆鏂囧瓧寮傚父: {e}")
                import traceback
                traceback.print_exc()
            
            
            # 鎵�鏈夋柟娉曢兘澶辫触浜?
            print(f"   鈿狅笍 璇?闊宠浆鏂囧瓧鎵�鏈夋柟娉曢兘澶辫触")
            print(f"   馃挕 寤鸿??: 妫�鏌? DashScope API 瀵嗛挜鏉冮檺鎴栨ā鍨嬪彲鐢ㄦ�?")
            
            # 馃幆 鍥為��鏂规?堬細浣跨敤瀹炴椂ASR鐨勫巻鍙茶浆鍐欙紙濡傛灉瀛樺湪锛?
            if context_transcript and len(context_transcript.strip()) > 0:
                print(f"   鉁? 浣跨敤涓婁笅鏂囪浆鍐欎綔涓哄洖閫�鏂规?? ({len(context_transcript)}瀛?)")
                return context_transcript
            
            print(f"   馃攧 绯荤粺灏嗕娇鐢ㄧ函瑙嗚?? AI 鍒嗘瀽")
            return ""
        
        except Exception as e:
            print(f"   鈿狅笍 璇?闊宠浆鏂囧瓧寮傚父: {e}")
            import traceback
            traceback.print_exc()
            return ""
    
    def _analyze_moment_with_ai(self, frame, moment_id: str, transcript: str = "", context_text: str = ""):
        """
        涓虹敤鎴锋爣璁扮殑鍏抽敭鏃跺埢鐢熸垚 AI 鍒嗘瀽 (澶氭ā鎬?)
        
        Args:
            frame: 甯у浘鍍?
            moment_id: 鍏抽敭鏃跺埢ID
            transcript: 璇?闊宠浆鏂囧瓧鍐呭??
        """
        import cv2
        
        try:
            # 浼樺寲锛氱缉灏忓浘鍍忎互鍔犲揩 VLM 鍒嗘瀽 (Max width 1280)
            frame_for_ai = frame
            h, w = frame.shape[:2]
            if w > 1280:
                scale = 1280 / w
                new_h = int(h * scale)
                frame_for_ai = cv2.resize(frame, (1280, new_h))

            # 灏嗗抚缂栫爜涓? base64
            _, buffer = cv2.imencode('.jpg', frame_for_ai, [cv2.IMWRITE_JPEG_QUALITY, 85])
            image_base64 = base64.b64encode(buffer).decode('utf-8')

            # 浠? moment 閲屽彇鎸夐敭鍘熷洜
            user_note = ""
            for m in self.moments:
                if m.id == moment_id:
                    user_note = (m.user_note or "")
                    break

            # 鍏抽敭锛氳?佹眰鈥滃熀浜庤瘉鎹?锛屼笉纭?瀹氬氨璇翠笉纭?瀹氣�濓紝骞剁◢寰?鍙ｈ??骞介粯
            transcript_clean = (transcript or "").strip()

            # 鍏抽敭锛氬彧鍙? context.txt 閲屾渶鍚庝竴娆″啓鍏ョ殑 transcript_context锛堜篃灏辨槸鈥滅獥鍙ｈ浆鍐欌�濓級
            context_excerpt = (context_text or "").strip()
            marker = "=== transcript_context ==="
            if marker in context_excerpt:
                context_excerpt = context_excerpt.rsplit(marker, 1)[1].strip()
            # 鎴?鏂?鏃朵繚鐣欏熬閮?锛堟洿闈犺繎鎸夐敭鏃跺埢/绐楀彛锛夛紝閬垮厤鎴?鍒版棫鍐呭??
            if len(context_excerpt) > 3500:
                context_excerpt = "[...context truncated...]\n" + context_excerpt[-3500:]

            prompt = f"""你是一面“智能魔镜”，负责忠实记录创客马拉松/Hackathon现场发生的瞬间。

场景说明：这是一个创客马拉松/Hackathon现场（制作原型、写代码、调试、讨论方案）。

核心原则 - 魔镜观察法：
1) **如同镜子般忠实反射**：客观描述你从画面中看到的和从ASR中听到的，不带主观评价。
2) **具体可见**：描述具体的动作、对话、表情、物体，不要使用抽象概念（如“深度讨论”-->“两人指着屏幕交谈”）。
3) **所见即所报**：看到几个人写几个人，听到什么对话引用什么对话，观察到什么动作写什么动作。
4) **全语境定位**：⚠️ 必须结合[历史上下文]中的完整转写，理解当前瞬间在整体活动流中的位置，说明之前发生了什么，现在正在做什么，以及此刻的意义。
5) **承认不确定性**：如果画面模糊、ASR为空或无法判断，直接写“画面未显示明显活动”或“无语音内容”。
6) ⚠️ 如果[本段ASR]为“(no voice)”且画面无明显活动，写“画面无明显活动”，严禁编造内容。

[用户标注/按键原因] {user_note or "(无)"}

[历史上下文(可能已截断)]
{context_excerpt or "(无)"}

[本段ASR(可能有噪音)]
{transcript_clean or "(无语音)"}

⚠️ **优先级原则**：
- 语音内容 > 画面内容（语音是核心活动记录）
- 如果ASR有内容，必须以语音为主线进行描述，画面为辅
- 仅在ASR为空时，才纯描述画面

请严格按照以下格式输出：
标题：<10-14字，必须包含：人数+具体动作/事件（优先基于语音内容）+关键物体；可带0-1个相关emoji>
详细描述：<2-3句，**优先描述语音内容**：①如果有ASR，先原样摘录对话（保留原语言） ②然后补充画面：人数、布局、动作 ③可见物体；使用短句；总字数≤120字；禁用词：“热烈”、“深入”、“火花”等抽象词>
分析框架标签：<如果对话/行为符合协作学习编码框架，标注对应标签，如“[R2] 论证”、“Eng-Flow 工程流”、“Soc-Help 互助”；主要基于对话内容判断；如无明显框架行为，写“无框架标签”>
上下文定位：<1-2句，**基于[历史上下文]的完整转写**，说明：①此前发生之事 ②当前处于整体活动流的哪个阶段 ③此刻的作用/意义；如果历史为空写“无历史上下文”>
证据摘录：<1-3条，原样摘录ASR或历史上下文中的关键句，保留时间戳；如无则写“无”>
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
                refine_prompt = f"""你是一面智能魔镜，正在客观整理视觉模型的输出。

场景说明：这是一个创客马拉松/Hackathon现场（制作原型、写代码、调试、讨论方案）。

你将收到三个输入：
1) 视觉模型对画面的解读（可能不完整/不准确）
2) 历史上下文（带时间戳，可能截断）
3) 本段ASR文本（可能有噪音）

硬性要求：
- 你只能使用[历史上下文]和[本段ASR]中的文本作为“证据摘录”；摘录必须原样保留时间戳。
- 对于画面，只描述你“能从视觉解读中确认”的内容；如不确定，写“无法确定”。
- **使用中文输出**，保持客观描述风格：忠实反映画面和对话，不添加主观评价。
- 描述具体可见的内容，不要使用模糊抽象的词汇。

[用户标注/按键原因] {user_note or "(无)"}

[视觉解读(来自模型，可能有误)]
{(ai_analysis or "").strip() or "(无)"}

[历史上下文(可能截断)]
{context_excerpt or "(无)"}

[本段ASR(可能有噪音)]
{transcript_clean or "(无语音/未识别)"}

⚠️ **优先级原则**：
- 语音内容 > 画面内容（语音是核心活动记录）
- 如果ASR有内容，必须以语音为主线
- 仅在ASR为空时才主要描述画面

请严格按照以下格式输出：
标题：<10-14字，必须基于语音内容或画面动作；可带0-1个emoji>
卡片摘要：<**必须20-30字，必须使用中文**，生动有趣，像新闻标题一样吸引人！必须包含1-2个emoji 🎯。不要以“团队成员”、“参与者”、“演讲者”开头 ❌；以动词或场景开头 ✅。好例子：“机器狗终于跑起来了！凌晨4:30的突破时刻 🦿⚡️”，“从虚拟游戏到实体创造，这次认知飞跃史诗级 🎮➡️”，“3D打印让创意落地，创客门槛大幅降低 🖨️✨”；坏例子：“团队成员讨论技术问题”（太无聊 ❌），“参与者分享经验”（太抽象 ❌）>
详细描述：<**必须3-5个完整句子**，总字数**必须达到100-150字**。优先详细引用ASR对话（带引号），然后描述画面：具体人数、位置、动作、表情、物体。使用连贯的叙事风格，就像在给盲人现场解说。禁止：抽象词汇>
分析框架标签：<如果对话/行为符合协作学习编码框架（如 [R2] 论证, Eng-Flow, Soc-Help 等），标注对应标签；如无明显框架行为，写“无框架标签”>
上下文定位：<1-2句，**基于[历史上下文]的完整转写**，说明：①此前发生之事 ②当前处于整体活动流的哪个阶段 ③此刻的作用/意义；如果历史为空写“无历史上下文”>
证据摘录：<1-3条，原样摘录ASR或历史上下文中的关键句，保留时间戳；如无则写“无”>
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
            
            # 鏇存柊鍏抽敭鏃跺埢鐨? AI 鍒嗘瀽缁撴灉
            for moment in self.moments:
                if moment.id == moment_id:
                    tagline, body = self._extract_tagline(final_text)
                    detail_desc = self._extract_detail_description(body)
                    card_summary = self._extract_card_summary(body)  # 鎻愬彇鍗＄墖鎽樿??
                    framework_tags = self._extract_framework_tags(body)
                    
                    # 浼樺厛浣跨敤card_summary锛?20-25瀛楋級鏄剧ず鍦ㄥ崱鐗囦笂
                    #  鍥為��鍒癲etail_desc鎴杢agline
                    new_description = (card_summary or "").strip() or (detail_desc or "").strip() or (tagline or "").strip()

                    moment.ai_tagline = (tagline or "").strip()
            
                    moment.ai_framework_tags = framework_tags
                    moment.analysis = body

                    # 闃叉?⑩�滈檷绾р�濓細涓嶈?佺敤寰堢煭鐨勬柊鏂囨湰瑕嗙洊宸叉湁鐨勯珮淇℃伅瀵嗗害鎻忚堪
                    existing_desc = (moment.ai_description or "").strip()
                    existing_is_placeholder = existing_desc in {"", "AI澶勭悊涓?鈥?", "AI Processing...", "AI鍒嗘瀽澶辫触", "AI Analysis Failed"}
                    has_card_summary = bool((card_summary or "").strip())
                    if has_card_summary or existing_is_placeholder:
                        # 鏈塩ard_summary鎴栨槸鍗犱綅绗︼細鐩存帴鏇存柊
                        moment.ai_description = new_description
                    else:
                        # 杩囩煭鐨勬柊鏂囨湰閫氬父鏄?鈥滄爣绛炬埅鏂?/鎶藉彇澶辫触鈥濓紝涓嶈?嗙洊
                        if len(new_description) < 12:
                            pass
                        # 鏂版枃鏈?鏄捐憲鏇寸煭涓旀病鏈夋槑鏄惧?為噺鏃讹紝涓嶈?嗙洊
                        elif len(new_description) + 10 < len(existing_desc):
                            pass
                        else:
                            moment.ai_description = new_description

                    moment.llm_provider = self.llm_provider
                    moment.llm_model = (
                        f"vision={self.vision_model};text={self.text_model}"
                        if use_text_postprocess else self.vision_model
                    )
                    print(f"鉁? AI Analysis completed: {moment_id}")
                    if (moment.ai_tagline or "").strip():
                        print(f"   馃彿锔? Tag: {moment.ai_tagline}")
                    if framework_tags:
                        print(f"   馃敄 Framework tags: {framework_tags}")
                    break
            
            # 淇濆瓨鏇存柊
            self._save_moments()
            
        except Exception as e:
            print(f"鈿狅笍 AI Analysis failed: {e}")
            import traceback
            traceback.print_exc()

            # 鍥炲啓涓�涓?鍙?瑙佺殑澶辫触淇℃伅锛岄伩鍏嶅墠绔?鏄剧ず绌虹櫧
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
    # 馃帳馃摲 澶氭ā鎬佸垎鏋? (闊抽?? + 鍥惧儚鑱斿悎)
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
                m.ai_tagline = "馃帶 No Audio"
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
            frame: 褰撳墠甯у浘鍍?
            frame_number: 甯у彿
            transcript_text: 涓庤?ュ抚瀵归綈鐨勭煭绐楀彛杞?鍐欐枃鏈?锛堥�氬父涓郝?10绉掔獥鍙ｏ級
            person_count: 褰撳墠浜烘暟
            track_ids: 缁熶竴鍚庣殑 person_id 鍒楄〃
            timestamp: 璇ュ抚瀵瑰簲鐨? epoch 鏃堕棿鎴筹紙鐢ㄤ簬涓庤浆鍐?/瑙嗛?戠墖娈靛?归綈锛?
            video_frames: 鍙?閫夌殑瑙嗛?戝抚绐楀彛锛堟潵鑷? 5 鍒嗛挓鍒囩墖缂撳啿锛夛紝鐢ㄤ簬鐢熸垚涓庤?ユ椂鍒诲尮閰嶇殑瑙嗛?戠墖娈?

        Returns:
            LLM 鍒嗘瀽缁撴灉 dict锛堜粎褰撳懡涓?鍏抽敭鏃跺埢骞舵垚鍔熻?板綍鏃惰繑鍥烇級锛屽惁鍒? None
        """
        if not self.qwen_available:
            print("鈿狅笍 LLM 涓嶅彲鐢?锛岃烦杩囧?氭ā鎬佸垎鏋?")
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
            # 灏嗗抚缂栫爜涓? base64
            _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            image_base64 = base64.b64encode(buffer).decode('utf-8')

            track_ids = track_ids or []

            prompt = f"""浣犳槸涓�浣嶅崗浣滃?︿範鐮旂┒涓撳?讹紝浣跨敤涓撲笟鐨勮?屼负缂栫爜妗嗘灦鍒嗘瀽鍗忎綔鍦烘櫙銆?

鍦烘櫙璇存槑锛氳繖鏄?鈥滃垱瀹㈤┈鎷夋澗 / Hackathon鈥濈幇鍦猴紙鍋氬師鍨嬨�佸啓浠ｇ爜銆佽皟璇曘�佽?ㄨ?烘柟妗堬級锛屼絾鎴戜滑甯屾湜鍗＄墖鏂囨?堝儚浣撹偛璧涗簨鐩存挱涓�鏍锋湁鑺傚?忋�佹湁姊椼�?

浣犲皢鏀跺埌锛氫竴甯ц?嗛?戠敾闈? + 涓庤?ュ抚鏃堕棿瀵归綈鐨勭煭绐楀彛璇?闊宠浆鍐欙紙閫氬父卤10绉掞級銆?

銆愬垽瀹氬師鍒欙紙闈炲父閲嶈?侊級銆?
1) 涓嶈?佷负浜嗘壘鑰屾壘锛氬?傛灉璇佹嵁涓嶈冻/涓嶆槑纭?/鍙?鏄?鏅?閫氭祦绋嬪?硅瘽锛岃?疯繑鍥? is_key_moment=false銆?
2) 鍏抽敭鏃跺埢搴斿綋浣撶幇娓呮櫚鐨勨�滆?ょ煡/鍗忎綔璺冭縼鈥濓紝浼樺厛 R2/R3銆?
    浣嗗湪鈥滆?叉巿/瑙傜偣杈撳嚭/缁撴瀯鍖栬?茶В鈥濆満鏅?閲岋紝濡傛灉鍑虹幇锛?
    - 娓呮櫚鐨勬?傚康瀹氫箟/妗嗘灦鎻愬嚭锛圲nd-Exp锛?
    - 缁撴瀯鍖栨�荤粨/鍒楃偣锛堜緥濡傗�滄湁涓変釜鐐?/绗?涓�绗?浜岀??涓夆�濓級
    - 鍏抽敭鎻愰棶鎺ㄥ姩鎬濊�冿紙Init-Feed/Und-Exp锛?
    涔熷彲浠ュ垽涓哄叧閿?锛坕mportance 缁欏埌 0.50鈥?0.75锛岃?嗚瘉鎹?寮哄害锛夈�?
3) importance 鏍囧畾瑕佷繚瀹堬細
    - 0.00鈥?0.39锛氭櫘閫氫簰鍔?/閲嶅?嶄俊鎭?/娴佺▼
    - 0.40鈥?0.59锛氭湁浠峰�间絾涓嶅?熲�滃叧閿?鈥濓紙閫氬父浠嶅簲 is_key_moment=false锛?
    - 0.60鈥?0.79锛氬叧閿?锛堣瘉鎹?娓呮櫚锛屽彲澶嶈堪锛?
    - 0.80鈥?1.00锛氬己鍏抽敭锛堟槑鏄剧獊鐮?/杞?鎶?/鍏辫瘑/鏂规硶鏀瑰彉锛?
4) 杈撳嚭瑕佺煭锛歞escription/meeting_note 鎺у埗鍦? 1-2 鍙ワ紝淇℃伅瀵嗗害楂橈紝鍙?澶嶈堪銆?
5) 闇�瑕佹彁渚? card_summary锛氱敤浜庡崱鐗囩殑绠�鐭?鎽樿?侊紝**涓ユ牸20-30瀛?**锛?"浣撹偛璧涗簨鎾?鎶ラ?? + 鍒涘?㈤┈鎷夋澗璇?澧?"锛屾洿鍙ｈ??鏇村ソ鐜╋紱鍙?甯? 2-3 涓?杞婚噺琛ㄦ儏绗﹀彿锛堝?? 馃弫馃洜锔忊殹锔忦煄?馃?栶煉★級锛屼絾涓嶈?佷綆淇椼�?

銆愯?嗚?変俊鎭?銆戠敾闈?涓?鐨勫満鏅?
銆愯??闊冲唴瀹广�戜笌璇ュ抚瀵归綈鐨勭獥鍙ｅ?硅瘽杞?鍐?:
"{transcript_text}"

璇锋牴鎹?浠ヤ笅瀹屾暣缂栫爜妗嗘灦杩涜?岃瘑鍒?锛?

=================================================================
缁村害涓�锛氬弬涓庝笌娌夋蹈 (Engagement) - 鎶曞叆鏃堕棿銆佹儏鎰熺姸鎬佷笌蹇冩祦浣撻獙
=================================================================

銆怑ng-Flow 娌夋蹈/蹇冩祦銆?
Engage闃舵??:
- [R1] 鎺㈢储鎬у洶鎯?: [EVT]琛ㄨ揪濂藉??/鍥版儜 "I wonder..." - "Recognition of some confusion... posing a problem."
- [R1] 鐪熷疄鎬х‘璁?: [KB]鐪熷疄闂?棰樻潵婧愪簬鐞嗚В涓栫晫鐨勫姫鍔?
Investigate闃舵??:
- [R1] 闂?棰樺懡鍚?: [DT]瀹氫箟(Define) 闂?棰橀噸鏋?/娲炲療鍔涚敓鎴?; [Co-ref]鍛藉悕-璇嗗埆鐩稿叧闂?棰?
- [R1] 淇℃伅渚涚粰: [EVT]淇℃伅鎬?-鎻愪緵淇℃伅鍏宠仈璇濋??
Act闃舵??:
- [R0] 鍏疯薄鍖栬?屽姩: [DT]鍘熷瀷(Prototype) 鍒朵綔鑽夊浘/瀹炰綋/浣庝繚鐪熸ā鍨?; [Co-ref]琛屽姩-瑙ｉ噴鍒濇?ヨВ鍐虫柟妗?
- [R1] 鏀硅繘鎰忓浘: [KB]鐭ヨ瘑寤烘瀯璇濊??-鏃ㄥ湪鏀硅繘鎬濇兂鐨勮瘽璇?

銆怑ng-Emo 鎯呮劅/姘涘洿銆?
Engage闃舵??:
- [R0] 鎯呮劅杩炴帴: [SSBC]鎯呮劅鏀?鎸?-琛ㄨ揪濂芥劅/鐮村啺 "Stresses the closeness of the relationship"
- [R0] 灏婇噸纭?璁?: [SSBC]灏婇噸鏀?鎸?-鑲?瀹?/纭?璁よ?傜偣 "Validation: Expresses agreement"
- [R1] 鐩镐簰鍗拌瘉: [IAM]PhI/C-鐩镐簰鍗拌瘉渚嬪瓙 "Corroborating examples"
Investigate闃舵??:
- [R0] 璧勬簮鎺ュ叆: [SSBC]缃戠粶鏀?鎸?-鎺ュ叆浜鸿剦/璧勬簮
- [R0] 鐗╃悊闄?浼?: [SSBC]闄?浼?-鑺辨椂闂村湪涓�璧? "Spend time with the recipient"
- [R1] 閭�璇锋�濊�?: [EVT]閭�璇锋�? "What do you think?" - "Inviting others to think together"
Act闃舵??:
- [R0] 瀹炶川鍗忓姪: [SSBC]瀹炶川鎬ф敮鎸?-鐩存帴浠诲姟鍗忓姪/鍊熻捶鐗╁搧
- [R1] 璧炵編璇勪环: [SSBC]璧炵編-璇勪环鑳藉姏/鐗硅川 "Says positive things about abilities"
- [R1] 闆嗕綋鑷?璞?: [KB]鐭ヨ瘑姘戜富鍖?-涓虹兢浣撹繘姝ユ劅鍒拌嚜璞?

銆怑ng-Strug 鎸ｆ墡/鍧氭寔銆?
Engage闃舵??:
- [R1] 璇嗗埆鍥伴毦: [IAM]PhI/E-璇嗗埆闂?棰樼殑鍥伴毦 "Definition, description, or identification of a problem"
- [R1] 澶勭悊闅鹃??: [KB]鐪熷疄闂?棰?-澶勭悊瀵硅嚜宸辨湁閲嶈?佹剰涔夌殑闅鹃??
Investigate闃舵??:
- [R1] 璇嗗埆鍒嗘??: [IAM]PhII/A-璇嗗埆鍒嗘?ч?嗗煙 "Identifying and stating areas of disagreement"
- [R1] 璁惧畾闄愬埗: [Co-ref]闄愬埗-璁惧畾瑙勮寖/璇嗗埆闄愬埗
Act闃舵??:
- [R1] 娼滃姏璇勪及: [Co-ref]璇勪及-鍒ゆ柇娼滃姏/閫傚簲鎬?, 鍖呮嫭璐ㄧ枒/绉佷汉鎬濊�?
- [R2] 楠岃瘉鍋囪??: [DT]娴嬭瘯(Test)-楠岃瘉鍋囪??/浠�涔堟棤鏁?

=================================================================
缁村害浜岋細涓诲姩鎬т笌鎰忓浘 (Initiative) - 璁惧畾鐩?鏍囥�佸?绘眰鍙嶉?堛�佹壙鎷呴?庨櫓
=================================================================

銆怚nit-Goal 鐩?鏍?/璁″垝銆?
Engage闃舵??:
- [R1] 鐩?鏍囬敋瀹?: [Co-ref]纭?瀹氱洰鏍?-纭?瀹氫紭鍏堢骇
- [R1] 璁″垝鍒跺畾: [KB]璁ょ煡鑳藉姩鎬?-璁惧畾鐩?鏍囧拰璁″垝
- [R1] 婢勬竻缁嗚妭: [IAM]PhI/D-鎻愰棶浠ユ緞娓呯粏鑺?
Investigate闃舵??:
- [R1] 瑙掕壊鍒嗛厤: [Co-ref]纭?瀹氳?掕壊/浠诲姟-鍒嗛厤宸ヤ綔
- [R1] 娴佺▼寤鸿??: [Co-ref]鎻愬嚭娴佺▼-寤鸿??琛屽姩姝ラ??
- [R2] 璁ょ煡浠ｇ悊: [KB]璁ょ煡鑳藉姩鎬?-澶勭悊閫氬父鐣欑粰鏁欏笀鐨勯棶棰?
Act闃舵??:
- [R2] 鏋勬�濆彂鏁?: [DT]鏋勬�?(Ideate)-鏁伴噺浼樺厛/鎺ㄨ繜鍒ゆ柇
- [R2] 鍐崇瓥鍙犲姞: [Co-ref]鍋氬喅瀹?-鍥㈤槦鍐呴儴鍙犲姞鍏磋叮
- [R2] 濡ュ崗闄堣堪: [IAM]PhIII/D-鎻愬嚭浣撶幇濡ュ崗鐨勬柊闄堣堪

銆怚nit-Feed 鍙嶉??/楠岃瘉銆?
Engage闃舵??:
- [R1] 瑙傜偣闄堣堪: [IAM]PhI/A-闄堣堪瑙傚療鎴栨剰瑙? "A statement of observation or opinion"
- [R1] 鐞嗚В鎯虫硶: [KB]瑙傜偣澶氭牱鎬?-鐞嗚В鍛ㄥ洿鐨勬兂娉?
Investigate闃舵??:
- [R2] 鐞嗙敱璐ㄧ枒: [Co-ref]璐ㄧ枒/瑕佹眰鐞嗙敱
- [R2] 婢勬竻鍒嗘??: [IAM]PhII/B-鎻愰棶婢勬竻鍒嗘?ф潵婧?
- [R2] 缁煎悎鍒嗘瀽: [EVT]鍒嗘瀽鎬?-缁煎悎璇勪及浠栦汉鐞嗚В
Act闃舵??:
- [R2] 杩?浠ｄ慨鏀?: [DT]娴嬭瘯-鐢ㄦ埛鍙嶉??/杩?浠ｄ慨鏀?
- [R2] 浜嬪疄娴嬭瘯: [IAM]PhIV/A-瀵圭収鍏?璁や簨瀹炴祴璇?
- [R2] 缁忛獙娴嬭瘯: [IAM]PhIV/C-瀵圭収涓?浜虹粡楠屾祴璇?

銆怚nit-Risk 椋庨櫓/浜夎?恒�?
Engage闃舵??:
- [R2] 瀵规瘮鎯虫硶: [KB]瑙傜偣澶氭牱鎬?-鍖呭惈瀵规瘮鎯虫硶
- [R2] 鐤?鐙傛兂娉?: [DT]鏋勬�?-鐤?鐙傜殑鎯虫硶(Wild ideas)
Investigate闃舵??:
- [R2] 鎺㈢储涓嶄竴鑷?: [IAM]PhII/A-鍙戠幇涓庢帰绱?涓嶄竴鑷?
- [R2] 璁鸿瘉鎺ㄧ悊: [EVT]璁鸿瘉鎬?-浣跨敤鎺ㄧ悊瑙﹀彂璁ㄨ?? "Expressing reasoning with analogies"
- [R2] 鎵瑰垽鎸戞垬: [EVT]鎵瑰垽鎬?-鎸戞垬鎴栨壆婕旀伓榄斾唬瑷�浜?
Act闃舵??:
- [R3] 瓒呰秺鑷?鎴?: [KB]瓒呰秺鑷?鎴?(Rise Above)-瓒呰秺鏈�浣冲疄璺?/鏂扮殑缁煎悎
- [R2] 璁烘嵁鏉冮噸: [IAM]PhIII/B-鍗忓晢璁烘嵁鐨勭浉瀵规潈閲?
- [R3] 妗嗘灦閲嶆瀯: [Co-ref]妗嗘灦/閲嶆瀯-瀵艰嚧鏂扮殑杈圭晫

=================================================================
缁村害涓夛細绀句細鏀?鏋? (Social Scaffolding) - 浜掑姪銆佹縺鍙戠伒鎰熴�佺墿鐞嗚繛鎺?
=================================================================

銆怱oc-Ind 鐙?绔?/鑷?璇磋嚜璇濄�?
- [R0] 鐙?绔嬮檲杩?(Monologue): [IAM]PhI/A闄堣堪瑙傚療鎴栨剰瑙佷絾鏈?鍥炲簲浠栦汉
- [R0] 骞宠?岀爺涔?(Parallel Study): [LDF]涓撴敞鏉愭枡浣嗘棤浜掑姩
- [R0] 骞宠?屽埗浣?(Co-acting): [LDF]鐗╃悊浣嶇疆鍦ㄤ竴璧蜂絾鏃犺?ょ煡浜ら泦

銆怱oc-Help 浜掑姪/鏁欏?︺�?
Engage闃舵??:
- [R0] 鍏崇郴纭?璁?: [SSBC]鍏崇郴纭?璁?-寮鸿皟绾藉甫
- [R1] 寤鸿??鍔濆憡: [SSBC]淇℃伅鏀?鎸?-寤鸿??/鍔濆憡 "Offers ideas or suggests actions"
Investigate闃舵??:
- [R1] 娑堥櫎鐩插尯: [SSBC]鏁欏??-鎻愪緵璇︾粏浜嬪疄/娑堥櫎鐩插尯
- [R1] 淇℃伅鎻愪緵: [Co-ref]鎻愪緵淇℃伅-缁欎簬淇℃伅/澶栭儴绀轰緥
- [R1] 鏂囩尞鏀?鎸?: [IAM]PhII/C-寮曠敤鏂囩尞/鏁版嵁鏀?鎸佽?傜偣
Act闃舵??:
- [R0] 鐩存帴浠诲姟: [SSBC]瀹炶川鎬ф敮鎸?-鐩存帴浠诲姟/闂存帴浠诲姟
- [R1] 绉?鏋佸弬涓?: [SSBC]绉?鏋佸弬涓?-涓�璧峰弬涓庢椿鍔ㄥ噺鍘?
- [R3] 瀵圭О璐＄尞: [KB]瀵圭О鐭ヨ瘑杩涙??-璺ㄥ洟闃熶簰鍔ㄨ础鐚?璧勬簮

銆怱oc-Insp 婵�鍙?/鍏变韩銆?
Engage闃舵??:
- [R1] 鍗拌瘉渚嬪瓙: [IAM]PhI/C-鐩镐簰鍗拌瘉渚嬪瓙
- [R2] 涓板瘜鐜?澧?: [KB]瑙傜偣澶氭牱鎬?-鍒涢�犱赴瀵岀殑婕斿彉鐜?澧?
Investigate闃舵??:
- [R2] 鏁版嵁鏀?鎸?: [IAM]PhII/C-寮曠敤鏂囩尞/鏁版嵁鏀?鎸佽?傜偣
- [R2] 鏉冨▉鎵╁睍: [KB]鏉冨▉璧勬枡搴旂敤-瓒呰秺鏃㈠畾璧勬枡鎵╁睍鐞嗚В
- [R2] 瑙ｉ噴缁嗗寲: [EVT]瑙ｉ噴鎬?-鍦ㄥ墠浜哄熀纭�涓婄粏鍖?
Act闃舵??:
- [R3] 鍚?鍙戝彂鐜?: [EVT]鍚?鍙戝紡(Heuristic) "A ha!" - "Expressing discovery... directing others' attention"
- [R3] 缁煎悎瑙傜偣: [Co-ref]鎻愬嚭缁煎悎瑙傜偣
- [R3] 鏁村悎闅愬柣: [IAM]PhIII/E-鎻愬嚭鏁村悎鎬х殑闅愬柣鎴栫被姣?

銆怱oc-Conn 杩炴帴/鍗忓悓銆?
Engage闃舵??:
- [R0] 鐗╃悊鍦ㄥ満: [SSBC]闄?浼?-鐗╃悊涓婄殑鍦ㄥ満
- [R1] 鍏变韩璐ｄ换: [KB]闆嗕綋璐ｄ换-鍏变韩鎺ㄨ繘鐭ヨ瘑鐨勮矗浠?
Investigate闃舵??:
- [R1] 淇冭繘鐞嗚В: [Co-ref]淇冭繘鐞嗚В
- [R0] 鍚屼即鍏崇郴: [SSBC]鍚屼即鍏崇郴-鎻愰啋杩樻湁浠栦汉鏀?鎸?
Act闃舵??:
- [R3] 璐＄尞涓撻暱: [KB]瀵圭О鐭ヨ瘑杩涙??-涓嶅悓鎴愬憳璐＄尞涓撻暱
- [R3] 鍏卞悓寤烘瀯: [IAM]PhIII/D-鍏卞悓寤烘瀯 "Co-construction"
- [R2] 鍏磋叮鍙犲姞: [Co-ref]鍐呴儴鍙犲姞-鍥㈤槦鍏磋叮鍙犲姞

=================================================================
缁村害鍥涳細鐞嗚В鐨勫彂灞? (Understanding) - 椤挎偀銆佽В閲婄瓥鐣ャ�佸簲鐢ㄧ煡璇?
=================================================================

銆怳nd-Exp 瑙ｉ噴/鎺ㄦ紨銆?
Engage闃舵??:
- [R1] 瀹氫箟闂?棰?: [IAM]PhI/E-瀹氫箟鎴栨弿杩伴棶棰?
- [R1] 闂?棰樺懡鍚?: [Co-ref]鍛藉悕-璇嗗埆鐩稿叧闂?棰?
Investigate闃舵??:
- [R1] 鍙傝�冪粡楠?: [Co-ref]鍙傝�冭繃鍘荤粡楠?-宸茬煡瑕佺礌
- [R2] 瑙ｉ噴杩炴帴: [EVT]瑙ｉ噴鎬?-鏃ㄥ湪瑙ｉ噴娓呮?氱殑杩炴帴閾?
- [R2] 寮曠敤鏀?鎸?: [IAM]PhII/C-寮曠敤缁忛獙/鏂囩尞鏀?鎸?
Act闃舵??:
- [R2] 瑙ｉ噴鏂规??: [Co-ref]鎻愬嚭鏀瑰彉寤鸿??-瑙ｉ噴鍒濇?ヨВ鍐虫柟妗?
- [R2] 鍗忓晢鏈?璇?: [IAM]PhIII/A-鍗忓晢鏈?璇?鍚?涔?
- [R2] 缁嗗寲瑙傜偣: [EVT]瑙ｉ噴鎬?-Elaborate ideas

銆怳nd-Aha 椤挎偀/绐佺牬銆戔瓙鍏抽敭璇嗗埆
Engage闃舵??:
- [R3] 鐪熷疄鍩虹煶: [KB]鐪熷疄鎬濇兂Real Ideas-鐪熷疄鍩虹煶
- [R3] 娲炲療鍔?: [DT]娲炲療鍔涚敓鎴?-Insight generation
Investigate闃舵??:
- [R3] 鍙戠幇鏃跺埢: [EVT]鍚?鍙戝紡 "I find it!" / 鍙戠幇 猸? "Expressing discovery (A ha! moments)"
- [R3] 鍙?鏀硅繘: [KB]鍙?鏀硅繘鐨勬�濇兂-鎬濇兂鏄?鍙?鏀硅繘鐨?
Act闃舵??:
- [R3] 鏂扮殑缁煎悎: [KB]瓒呰秺鑷?鎴?(Rise Above)-杈惧埌鏂扮殑缁煎悎 猸?
- [R3] 搴旂敤鏂扮煡: [IAM]PhV/B-搴旂敤鏂扮煡璇?
- [R3] 鍏冭?ょ煡鏀瑰彉: [IAM]PhV/C-鍏冭?ょ煡灞傞潰鐨勬敼鍙? 猸? "Ways of thinking have changed"

銆怳nd-Strive 娣辨�?/鍐呭寲銆?
Engage闃舵??:
- [R1] 璁ょ煡鍥版儜: [EVT]鎺㈢储鎬?-璁ょ煡鍥版儜/Curiosity
- [R2] 绮剧?炵敓娲?: [KB]鏅?閬嶇煡璇嗗缓鏋?-璐?绌跨簿绁炵敓娲?
Investigate闃舵??:
- [R2] 涓?浜烘�濊�?: [Co-ref]涓?浜烘�濊�?-Private reflection
- [R2] 妫�鏌ュ疄璺?: [EVT]鍙嶆�濇�?-妫�鏌ヨ繃鍘荤殑瀹炶返/鐞嗚В
- [R2] 璇嗗埆闂?棰?: [KB]宓屽叆寮忚瘎浼?-璇嗗埆闂?棰?
Act闃舵??:
- [R2] 鍊惧惉鍙嶅悜鍙嶉??: [Co-ref]鍙嶆�?-鍊惧惉鎯呭?冪殑"鍙嶅悜鍙嶉??"
- [R2] 璁ょ煡鍥惧紡娴嬭瘯: [IAM]PhIV/B-瀵圭収鐜版湁璁ょ煡鍥惧紡娴嬭瘯
- [R2] 闅愬惈鎬у喅绛?: [EVT]闅愬惈鎬?-鍩轰簬娲炲療鍔涙彁鍑哄喅绛?

=================================================================
鐞嗚?烘潵婧愬浘渚?
=================================================================
[LDF]: Tinkering瀛︿範缁村害  [Hack4CBL]: 鏃堕棿闃舵??
[IAM]: 浜や簰鍒嗘瀽妯″瀷       [DT]: d.school璁捐?℃�濈淮
[EVT]: 鏈変环鍊兼暀鑲插?硅瘽     [KB]: 鐭ヨ瘑寤烘瀯鍘熷垯
[Co-ref]: 鍏卞悓鍙嶆�濆疄璺?    [SSBC]: 绀句細鏀?鎸佽?屼负
R0-R3: Fleck鍜孎itzpatrick(2010)鍙嶆�濆眰绾?

=================================================================

璇峰垎鏋愬苟浠?JSON鏍煎紡杩斿洖:
{{
    "is_key_moment": true/false,
    "importance": 0.0-1.0,
    "reflection_level": "R0|R1|R2|R3",
    "phase": "Engage|Investigate|Act",
    "primary_dimension": "Engagement|Initiative|Social|Understanding",
    "behavior_code": "L1琛屼负浠ｇ爜濡? Eng-Flow/Eng-Emo/Init-Goal/Soc-Help/Und-Aha绛?",
    "specific_behavior": "鍏蜂綋瀛愯?屼负濡? [R2]璁鸿瘉鎺ㄧ悊/[R3]鍙戠幇鏃跺埢/[R1]闂?棰樺懡鍚嶇瓑",
    "theoretical_source": "鐞嗚?烘潵婧愬?? [IAM]PhII/A/[EVT]鍚?鍙戝紡/[KB]瓒呰秺鑷?鎴戠瓑",
    "description": "涓�鍙ヨ瘽鎻忚堪姝ｅ湪鍙戠敓浠�涔堬紙鍋忓?㈣?傘�佸彲澶嶈堪锛?",
    "card_summary": "鐢ㄤ簬鍏抽敭鏃跺埢鍗＄墖鐨勪竴鍙ヨ瘽锛堟洿鍙ｈ??/鏇村菇榛橈紝鍙?甯﹁〃鎯呯?﹀彿锛?",
    "key_quote": "濡傛灉鏈夊叧閿?瀵硅瘽锛屾憳褰曟渶閲嶈?佺殑涓�鍙?",
    "observable_evidence": "鍙?瑙傚療鐨勮?屼负璇佹嵁",
    "meeting_note": "鐢ㄤ簬浼氳??绾?瑕佺殑绠�娲佽?板綍"
}}

鍙?杩斿洖JSON锛屼笉瑕佸叾浠栧唴瀹广�?"""

            result_text = self._run_vision_llm(
                image_base64=image_base64,
                prompt=prompt,
                model_override=self.vision_model,
                temperature=0.4,
                max_tokens=800
            )
            
            # 瑙ｆ瀽 JSON
            if result_text.startswith("```"):
                lines = result_text.split("```")
                result_text = lines[1] if len(lines) > 1 else lines[0]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
            
            result = json.loads(result_text.strip())

            # 杩借釜锛氭墦鍗版ā鍨嬪師濮婮SON锛堟埅鏂?/鍏ㄩ噺鐢? LLM_TRACE_* 鎺у埗锛?
            self._llm_trace_decision("multimodal parsed_json", result if isinstance(result, dict) else {"raw": result})

            # 澶氭ā鎬佸垎鏋愰槇鍊硷紙涓嶢I妫�娴嬮槇鍊间繚鎸佷竴鑷达級
            threshold = float(os.environ.get("MULTIMODAL_KEY_THRESHOLD", "0.35"))
            # 闄嶄綆鍐峰嵈鏃堕棿锛岄伩鍏嶆紡璁伴噸瑕佹椂鍒?
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

            # 濡傛灉鏄?寮哄埗蹇?鐓э紝淇?姝? is_key 浠ヤ究鍚庣画閫昏緫姝ｇ‘澶勭悊
            if force_snapshot and not is_key:
                is_key = True
                result["is_key_moment"] = True
                if importance < 0.1:
                    result["importance"] = 0.5 # 缁欎釜榛樿?ら噸瑕佹�?

            # 鎬绘槸鎵撳嵃娓呮櫚鐨勫垽瀹氱粨鏋滐紙鍛戒腑鎴栨湭鍛戒腑锛夛紝鏂逛究鐢ㄦ埛鐩存帴鍦ㄧ粓绔?鐪嬪埌
            summary_desc = (result.get("description") or result.get("meeting_note") or "")[:40].replace("\n", " ")
            rl = (result.get("reflection_level") or "").strip()
            phase = (result.get("phase") or "").strip()
            dim = (result.get("primary_dimension") or result.get("dimension") or "").strip()
            
            if ok_to_record:
                # 鍛戒腑浼氱敱鍚庣画閫昏緫鎵撳嵃 "鉁? 鍙戠幇鍏抽敭鏃跺埢"
                pass 
            else:
                # 鍒嗘瀽鎷掔粷鍘熷洜
                reasons = []
                if not is_key:
                    reasons.append("AI鍒ゅ畾闈炲叧閿?")
                if importance < threshold:
                    reasons.append(f"閲嶈?佹�т笉瓒?({importance:.2f}<{threshold})")
                if too_close and not allow_bypass_cooldown:
                    reasons.append(f"鍐峰嵈涓?({int(now_ts - last_ts)}s<{int(cooldown_s)}s)")
                
                reason_str = ", ".join(reasons)
                print(f"馃Ь 鏈?鍛戒腑: {reason_str} | 閲嶈?佹�?:{importance:.2f} | 鏍囩??:{dim}/{phase}/{rl} | 鎽樿??:{summary_desc}...")

            # Debug 杈撳嚭锛氶粯璁ゅ彧鎵撳嵃鈥滃垽瀹氬叧閿?瀛楁?碘�濓紝閬垮厤鎶婂叏鏂?/闀胯浆鍐欏埛灞?
            if debug_enabled:
                rl = (result.get("reflection_level") or "").strip()
                phase = (result.get("phase") or "").strip()
                code = (result.get("behavior_code") or "").strip()
                print(
                    f"馃?? MM frame={frame_number} key={is_key} imp={importance:.2f} thr={threshold:.2f} "
                    f"cooldown={too_close}({cooldown_s:.0f}s) ok={ok_to_record} rl={rl} phase={phase} code={code}"
                )

                if debug_mode in {"verbose", "full"}:
                    spec = (result.get("specific_behavior") or "").strip()
                    if spec:
                        print(f"   馃攷 {spec}")
                    preview = (transcript_text or "").replace("\n", " ").strip()
                    if len(preview) > 120:
                        preview = preview[:120] + "鈥?"
                    if preview:
                        print(f"   馃棧锔? {preview}")

            # 杩借釜锛氭墦鍗板垽瀹氫緷鎹?
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
                print(f"   馃Н skip: {reason}")

            return None
                
        except json.JSONDecodeError as e:
            print(f"鈿狅笍 Multimodal Analysis JSON parse error: {e}")
            return None
        except Exception as e:
            print(f"鈿狅笍 Multimodal Analysis failed: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _analyze_frame_only(self, frame, frame_number: int,
                            person_count: int, track_ids: List[int]) -> Optional[Dict]:
        """绾?鍥惧儚鍒嗘瀽锛堟棤璇?闊虫椂鐨勫洖閫�锛?"""
        # 鏀瑰姩锛氶粯璁ゅ厑璁哥函鍥惧儚鐢熸垚鍏抽敭鏃跺埢
        allow = (os.environ.get("ALLOW_IMAGE_ONLY_KEY_MOMENTS", "1") or "1").strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
            "on",
        }
        if not allow:
            return None
        # 璋冪敤鍘熸湁鐨勫浘鍍忓垎鏋愶紙鍙?鑳戒細钀藉簱 AI_DETECTED锛?
        # 娉ㄦ剰锛氳繖閲屾敼涓哄悓姝ヨ皟鐢ㄦ垨鑰呴渶绛夊緟缁撴灉鎵嶈兘杩斿洖缁檌ntegrated_system
        # 鐢变簬 _analyze_frame_with_ai 鍘熸湰璁捐?′负void锛屾垜浠?闇�瑕佺◢寰?鏀归�犲畠鎴栬�呯洿鎺ヨ繖閲岃繑鍥? mock result
        # 浣嗕负浜嗗?嶇敤閫昏緫锛屾垜浠?鍏堣?╁畠璺戯紙寮傛??/鍚屾?ュ彇鍐充簬瀹炵幇锛夛紝瀹冧細鑷?宸? _record_ai_moment
        self._analyze_frame_with_ai(frame, frame_number, person_count, track_ids or [])
        
        # 杩斿洖涓�涓?鍗犱綅绗︼紝鍛婅瘔integrated_system鎴戜滑灏濊瘯浜?
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

        # 淇濆瓨鍏抽敭甯?
        frame_filename = f"{moment_id}.jpg"
        frame_path = self.moments_dir / frame_filename
        cv2.imwrite(str(frame_path), frame)

        # 鏋勫缓鎻忚堪锛堜紭鍏堜娇鐢ㄧ畝鐭?鐨刢ard_summary鏄剧ず鍦ㄥ崱鐗囦笂锛?
        card_summary = (ai_result.get("card_summary") or "").strip()
        full_description = (ai_result.get("description", "") or "").strip()
        description = card_summary or full_description  # 浼樺厛绠�鐭?鎽樿??
        key_quote = (ai_result.get("key_quote") or "").strip()
        if key_quote and key_quote not in description:
            description += f' 馃挰 "{key_quote}"'
        
        # 馃彿锔? 鑷?鍔ㄧ敓鎴恡ags锛堜粠existing text content鎻愬彇鍏抽敭璇嶏級
        tags = ai_result.get("tags", [])
        if not tags or len(tags) == 0:
            # 浠巘agline/description鑷?鍔ㄦ彁鍙栧叧閿?璇嶄綔涓簍ags
            tagline = (ai_result.get("tagline") or "").strip()
            text_for_tags = tagline or description or transcript or ""
            # 鏀硅繘鐨勫垎璇嶏細鎸夋爣鐐圭?﹀彿鍒嗗壊锛屾彁鍙栫煭璇?
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
            
            # 杩囨护锛氬彧淇濈暀2-8瀛楃殑鐭?璇?锛屾帓闄ゅ父瑙佽瘝
            stopwords = {'鐨?', '浜?', '鍜?', '涓?', '鍦?', '鏄?', '鏈?', '杩?', '閭?', '灏?', '涓?', '涔?', '閮?', '杩?', '浠?', '鍒?'}
            filtered = []
            for w in words:
                if 2 <= len(w) <= 8 and w not in stopwords:
                    filtered.append(w)
            
            tags = filtered[:3]  # 鍙?鍙栧墠3涓?
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
            ai_tags=tags,  # 浣跨敤鑷?鍔ㄧ敓鎴愮殑tags
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
        # 绉婚櫎min_required_frames闃堝�煎垽鏂?锛岀‘淇濇墍鏈堿I妫�娴嬬殑鍏抽敭鏃跺埢閮芥槸鍥哄畾鏃堕暱
        video_path, video_duration = self._save_video_clip(
            moment_id=moment_id,
            clip_duration_before=float(before_s),
            clip_duration_after=float(after_s),  # 鍓嶅悗15绉?=30绉?
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
            print(f"   鈿狅笍  瑙嗛?戠敓鎴愬け璐?")
        
        moment_type = ai_result.get("moment_type", "unknown")
        print(f"馃帐馃摲 澶氭ā鎬佸叧閿?鏃跺埢: {time_str} [{moment_type}]")
        print(f"   馃摑 {description}")
        if ai_result.get("meeting_note"):
            print(f"   馃搵 绾?瑕?: {ai_result['meeting_note']}")
        print(f"   馃彿锔? 鏍囩??: {', '.join(ai_result.get('tags', []))}")
        
        return moment
    
    def generate_meeting_notes(self, transcript_segments: List[Dict] = None) -> Dict[str, Any]:
        """
        鐢熸垚鏅鸿兘浼氳??绾?瑕?
        
        Args:
            transcript_segments: 瀹屾暣鐨勮浆鍐欑墖娈靛垪琛? [{"text": "...", "timestamp": ...}, ...]
            
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
                    "type": "鐢ㄦ埛鏍囪??" if m.source == "user_anchor" else "AI璇嗗埆",
                    "description": m.ai_description or m.user_note or "鏈?鎻忚堪",
                    "tags": m.ai_tags,
                    "note": m.user_note if m.source != "user_anchor" else ""
                }
                moments_summary.append(summary)
            
            # 鍑嗗?囪浆鍐欐枃鏈?
            full_transcript = ""
            if transcript_segments:
                full_transcript = " ".join([s.get("text", "") for s in transcript_segments])
            
            zh_note_instr = "All output fields (summary, key_points, action_items, decisions) must be in Simplified Chinese."

            prompt = f"""[{zh_note_instr}] 
            浣犳槸鍒涘?㈤┈鎷夋澗鐜板満瑙ｈ?村憳锛屽儚NFL璧涗簨瑙ｈ?村憳涓�鏍锋挱鎶モ�斺�斾笓涓氥�佸?㈣?傘�佷絾鏈夌敾闈㈡劅銆?

銆愯В璇村師鍒欍�?
- 蹇犲疄闀滃瓙锛氭弿杩扮湅鍒板拰鍚?鍒扮殑鍐呭?癸紝涓嶅じ寮犮�佷笉鐬庣寽
- 鍙ｈ??鍖栬〃杈撅細鐢?"姝ｅ湪...""鍒氬垰...""鐪嬪埌..."绛夎嚜鐒惰??瑷�
- 閫傚害鐑?鎯咃細鏈夎妭濂忔劅锛屼絾涓嶈繃搴︾吔鎯?
- 灏戠敤缃戠粶姊楋細鍋跺皵鍙?浠ワ紝浣嗚?佽嚜鐒讹紙姣忔?垫渶澶?1涓?锛?

銆愯??闊冲唴瀹广�?
{full_transcript[:3000] if full_transcript else "锛堟殏鏃犺??闊宠?板綍锛?"}

銆愭爣璁版椂鍒汇�?
{json.dumps(moments_summary, ensure_ascii=False, indent=2) if moments_summary else "锛堟殏鏃犳爣璁帮級"}

馃帣锔? 鎾?鎶ヨ?佹眰锛?

**summary锛?20-35瀛楋級锛?**
瀹㈣?傛弿杩扮幇鍦虹姸鎬侊紝鏈夌敾闈㈡劅
鉁? 濂斤細"鍥㈤槦姝ｅ湪璋冭瘯纭?浠讹紝浼犳劅鍣ㄥ嚭鐜版暟鎹?涓嶇ǔ瀹氱殑鎯呭喌锛屽ぇ瀹跺湪鎺掓煡鍘熷洜"
鉁? 濂斤細"鐪嬪埌浠栦滑鎵惧埌浜咮ug浣嶇疆锛屾?ｅ湪淇?鏀逛唬鐮侊紝杩涘睍涓嶉敊"
鉂? 宸?锛?"璁ㄨ?轰簡纭?浠堕棶棰?"锛堝お涔﹂潰锛?
鉂? 宸?锛?"鑺?姣擰浜嗭紒浼犳劅鍣ㄧ偢浜嗭紒"锛堝お澶稿紶锛?

**key_points锛?3-5涓?瑕佺偣锛屾瘡鏉?15-25瀛楋級锛?**
瀹㈣?備簨瀹烇紝鍙ｈ??鍖栫煭鍙?
鉁? 濂斤細"鐢佃矾鏉跨??涓変釜鎺ュ彛鎺ヨЕ涓嶈壇锛岀帇宸ユ?ｅ湪閲嶆柊鐒婃帴"
鉁? 濂斤細"娴嬭瘯浜咥銆丅銆丆涓変釜浼犳劅鍣ㄥ瀷鍙凤紝鏈�鍚庡喅瀹氱敤A鍨?"
鉁? 濂斤細"寮犲伐鎻愬嚭鍔犳护娉㈢數璺?鐨勫缓璁?锛屽洟闃熻?ㄨ?哄悗閲囩撼浜?"
鉂? 宸?锛?"纭?浠堕棶棰?"锛堜俊鎭?澶?灏戯級
鉂? 宸?锛?"杩欐尝鎿嶄綔YYDS锛岀粷浜嗭紒"锛堝お濞变箰鍖栵級

**action_items锛堜笅涓�姝ヨ?″垝锛夛細**
瀹㈣?傚叿浣撶殑涓嬩竴姝?
鉁? 濂斤細"闇�瑕侀噰璐瑼鍨嬩紶鎰熷櫒妯″潡锛岄?勮?′粖澶╁畬鎴?"
鉁? 濂斤細"鍑嗗?囦慨澶嶆帴鍙?Bug锛岀劧鍚庨噸鏂版祴璇?"
鉂? 宸?锛?"涔颁紶鎰熷櫒"锛堝お绠�鐣ワ級
鉂? 宸?锛?"璧剁揣淇瓸ug锛屼笉鐒惰姯姣擰锛?"锛堝お澶稿紶锛?

**decisions锛堝凡纭?瀹氱殑鍐崇瓥锛夛細**
璇存竻閫夋嫨鍜屽師鍥?
鉁? 濂斤細"鍐冲畾浣跨敤React妗嗘灦锛屽洜涓哄洟闃熸洿鐔熸倝杩欎釜鎶�鏈?鏍?"
鉁? 濂斤細"閲囩撼鏂规?圔锛岀悊鐢辨槸铏界劧澶嶆潅浣嗙ǔ瀹氭�ф洿濂?"
鉂? 宸?锛?"鐢≧eact"锛堟病璇翠负浠�涔堬級

馃挕 **瑙ｈ?存妧宸э細**
- 鐢ㄧ幇鍦烘劅锛?"姝ｅ湪...""鐪嬪埌...""鍚?鍒?...""鍒氬垰..."
- 鎻忚堪鍔ㄤ綔锛?"寮犲伐璧板悜鐧芥澘""涓や汉姝ｅ湪璁ㄨ??""灏忔潕鍦ㄦ暡浠ｇ爜"
- 杞?杩板?硅瘽锛氱洿鎺ュ紩鐢ㄩ噸瑕佺殑璇?
- 璇存槑杩涘害锛?"宸插畬鎴怷""姝ｅ湪澶勭悊Y""涓嬩竴姝?Z"
- 閫傚害璇勪环锛氬彲浠ヨ??"杩涘睍椤哄埄""閬囧埌鍥伴毦"绛夊?㈣?傝瘎浠?

杩斿洖JSON鏍煎紡:
{{
    "summary": "瀹㈣?傛弿杩扮幇鍦虹姸鎬侊紙20-35瀛楋級",
    "key_points": ["浜嬪疄瑕佺偣1锛?15-25瀛楋級", "浜嬪疄瑕佺偣2", "浜嬪疄瑕佺偣3"],
    "action_items": ["鍏蜂綋鐨勪笅涓�姝ヨ?″垝"],
    "decisions": ["鍐崇瓥鍐呭?癸紙鍚?鐞嗙敱锛?"]
}}

鈿狅笍 绂佸繉锛?
- 鍒?鐢ㄤ功闈㈣??锛?"鏍规嵁""缁间笂""浼氳??璁ㄨ??""鏈?娆?"
- 鍒?澶?濞变箰鍖栵細灏戠敤"YYDS""鑺?姣擰""DNA鍔ㄤ簡"绛夌綉缁滄??
- 鍒?鐬庡じ寮狅細鍩轰簬瀹為檯鍐呭?癸紝涓嶇吔鎯呬笉鍚愭Ы
- 鍐呭?逛笉瓒虫椂锛宻ummary鍐欙細"鐜板満杈冨畨闈欙紝绛夊緟涓嬩竴姝ュ姩浣?"
""" 

            result_text = self._run_text_llm(
                prompt=prompt,
                model_override=self.text_model,
                temperature=0.4,
                max_tokens=2000
            )
            
            # 瑙ｆ瀽 JSON
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
            
            print(f"馃搵 浼氳??绾?瑕佺敓鎴愬畬鎴?")
            return meeting_notes
            
        except Exception as e:
            print(f"鈿狅笍 浼氳??绾?瑕佺敓鎴愬け璐?: {e}")
            return self._generate_simple_meeting_notes(transcript_segments)
    
    def _generate_simple_meeting_notes(self, transcript_segments: List[Dict] = None) -> Dict[str, Any]:
        """鐢熸垚绠�鍗曚細璁?绾?瑕侊紙鏃? AI锛?"""
        full_transcript = ""
        if transcript_segments:
            full_transcript = " ".join([s.get("text", "") for s in transcript_segments])
        
        # 浠庡叧閿?鏃跺埢鎻愬彇瑕佺偣
        key_points = []
        for m in self.moments:
            if m.ai_description:
                key_points.append(m.ai_description)
            elif m.user_note:
                key_points.append(f"[鐢ㄦ埛鏍囪?癩 {m.user_note}")
        
        return {
            "summary": f"鏈?娆′細璁?鍏辫?板綍 {len(self.moments)} 涓?鍏抽敭鏃跺埢锛岃浆鍐欐枃鏈?绾? {len(full_transcript)} 瀛椼�?",
            "discussion_topics": [],
            "decisions": [],
            "action_items": [],
            "key_quotes": key_points[:5],  # 鏈�澶?5涓?
            "participants_count": max([m.person_count for m in self.moments]) if self.moments else 0,
            "generated_at": datetime.now().isoformat(),
            "total_moments": len(self.moments),
            "transcript_length": len(full_transcript)
        }


    def _record_ai_moment(self, frame, frame_number: int,
                          person_count: int, track_ids: List[int],
                          ai_result: Dict[str, Any]):
        """璁板綍 AI 璇嗗埆鐨勫叧閿?鏃跺埢锛堝師濮嬫柟娉曪級"""
        import cv2
        
        timestamp = time.time()
        duration = timestamp - self.start_time
        time_str = self._format_time(duration)
        
        # 鐢熸垚鍞?涓�ID
        moment_id = f"ai_{int(timestamp)}_{frame_number}"
        
        # 淇濆瓨鍏抽敭甯?
        frame_filename = f"{moment_id}.jpg"
        description = ai_result.get("description", "")
        tagline = ai_result.get("tagline", "")
        analysis_text = ai_result.get("analysis", "")
        
        # 鎻愬彇妗嗘灦鏍囩?撅紙浠庡垎鏋愭枃鏈?涓?锛?
        framework_tags = KeyMomentsManager._extract_framework_tags(analysis_text)
        
        # 鍒涘缓鍏抽敭鏃跺埢瀵硅薄
        moment = KeyMoment(
            id=moment_id,
            timestamp=float(timestamp),
            source=MomentSource.MULTIMODAL_AI.value,
            frame_number=frame_number,
            frame_path=frame_path,
            ai_description=description,
            ai_tagline=tagline,
            ai_tags=tags,  # 浣跨敤鑷?鍔ㄧ敓鎴愮殑tags
            ai_framework_tags=framework_tags,  # 娣诲姞妗嗘灦鏍囩??
            ai_importance=float(ai_result.get("importance", 0.5)),
            transcript=transcript_segment,
            person_count=person_count,
            analysis=analysis_text,
            user_note=ai_result.get("observable_evidence", ""),
        )
        
        self.moments.append(moment)
        self.stats["ai_detected"] += 1
        self.stats["total_moments"] += 1
        
        # 淇濆瓨
        self._save_moments()
        
        print(f"馃?? AI 璇嗗埆鍏抽敭鏃跺埢: {time_str} (甯? {frame_number})")
        print(f"   馃摑 {ai_result.get('description', '')}")
        print(f"   馃彿锔? 鏍囩??: {', '.join(ai_result.get('tags', []))}")
    
    # ============================================================
    # 馃摉 鍙欎簨鐢熸垚 (The Narrative)
    # ============================================================
    
    def generate_narrative(self) -> Dict[str, Any]:
        """
        鐢熸垚鍥㈤槦鍙欎簨 (Oeuvre)
        
        鍍忕邯褰曠墖瀵兼紨涓�鏍凤紝灏嗙?庣墖鍖栫殑鐥曡抗鍓?杈戞垚杩炶疮鐨勫洟闃熷彊浜?
        """
        if not self.moments:
            return {"narrative": "鏆傛棤鍏抽敭鏃跺埢璁板綍", "chapters": []}
        
        if not self.qwen_available:
            return self._generate_simple_narrative()
        
        try:
            # 鍑嗗?囨椂鍒绘憳瑕?
            moments_summary = []
            for m in sorted(self.moments, key=lambda x: x.timestamp):
                summary = {
                    "time": m.time_str,
                    "source": "鐢ㄦ埛鏍囪??" if m.source == "user_anchor" else "AI璇嗗埆",
                    "description": m.user_note or m.ai_description or "鏈?鎻忚堪",
                    "person_count": m.person_count,
                    "importance": m.ai_importance if m.source == "ai_detected" else 0.8,
                    "tags": m.ai_tags
                }
                moments_summary.append(summary)
            
            prompt = f"""浣犳槸涓�浣嶇邯褰曠墖瀵兼紨鍜屾暀鑲茬爺绌惰�呫�傝?峰熀浜庝互涓嬪崗浣滃?︿範娲诲姩涓?鐨勫叧閿?鏃跺埢锛屽垱浣滀竴浠藉洟闃熷彊浜嬫姤鍛娿�?

鍏抽敭鏃跺埢璁板綍:
{json.dumps(moments_summary, ensure_ascii=False, indent=2)}

璇风敓鎴?:
1. 鍙欎簨鎬荤粨 (3-5鍙ヨ瘽鐨勬暣浣撴晠浜嬬嚎)
2. 鍏抽敭绔犺妭 (灏嗘椂鍒荤粍缁囨垚鏈夋剰涔夌殑闃舵??)
3. 鍥㈤槦娲炲療 (浠庤繖浜涙椂鍒讳腑瑙傚療鍒扮殑鍗忎綔妯″紡鍜屼寒鐐?)
4. 鍙嶆�濋棶棰? (2-3涓?寮曞?煎?︾敓鍙嶆�濈殑闂?棰?)

浠?JSON鏍煎紡杩斿洖:
{{
    "narrative_summary": "鏁翠綋鍙欎簨...",
    "chapters": [
        {{
            "title": "绔犺妭鏍囬??",
            "time_range": "00:00-05:00",
            "description": "杩欎釜闃舵?靛彂鐢熶簡浠�涔?",
            "moment_ids": ["鐩稿叧moment鐨刬d"]
        }}
    ],
    "team_insights": ["娲炲療1", "娲炲療2"],
    "reflection_questions": ["闂?棰?1", "闂?棰?2"]
}}"""

            result_text = self._run_text_llm(
                prompt=prompt,
                model_override=self.text_model,
                temperature=0.4,
                max_tokens=1500
            )
            
            # 瑙ｆ瀽 JSON
            if result_text.startswith("```"):
                result_text = result_text.split("```")[1]
                if result_text.startswith("json"):
                    result_text = result_text[4:]
            
            narrative = json.loads(result_text)
            narrative["generated_at"] = datetime.now().isoformat()
            narrative["total_moments"] = len(self.moments)
            
            # 淇濆瓨鍙欎簨
            narrative_file = self.moments_dir / "narrative.json"
            with open(narrative_file, 'w', encoding='utf-8') as f:
                json.dump(narrative, f, ensure_ascii=False, indent=2)
            
            print(f"馃摉 鍙欎簨鐢熸垚瀹屾垚")
            return narrative
            
        except Exception as e:
            print(f"鈿狅笍 鍙欎簨鐢熸垚澶辫触: {e}")
            return self._generate_simple_narrative()
    
    def _generate_simple_narrative(self) -> Dict[str, Any]:
        """鐢熸垚绠�鍗曞彊浜? (鏃? AI)"""
        sorted_moments = sorted(self.moments, key=lambda x: x.timestamp)
        
        chapters = []
        current_chapter_moments = []
        chapter_start_time = 0
        
        # 鎸夋椂闂撮棿闅斿垎绔犺妭 (5鍒嗛挓涓�绔?)
        for m in sorted_moments:
            if m.duration_seconds - chapter_start_time > 300 and current_chapter_moments:
                chapters.append({
                    "title": f"闃舵?? {len(chapters) + 1}",
                    "time_range": f"{self._format_time(chapter_start_time)}-{self._format_time(current_chapter_moments[-1].duration_seconds)}",
                    "description": f"璁板綍浜? {len(current_chapter_moments)} 涓?鍏抽敭鏃跺埢",
                    "moment_ids": [cm.id for cm in current_chapter_moments]
                })
                current_chapter_moments = []
                chapter_start_time = m.duration_seconds
            
            current_chapter_moments.append(m)
        
        # 娣诲姞鏈�鍚庝竴涓?绔犺妭
        if current_chapter_moments:
            chapters.append({
                "title": f"闃舵?? {len(chapters) + 1}",
                "time_range": f"{self._format_time(chapter_start_time)}-{self._format_time(current_chapter_moments[-1].duration_seconds)}",
                "description": f"璁板綍浜? {len(current_chapter_moments)} 涓?鍏抽敭鏃跺埢",
                "moment_ids": [cm.id for cm in current_chapter_moments]
            })
        
        user_count = sum(1 for m in self.moments if m.source == "user_anchor")
        ai_count = sum(1 for m in self.moments if m.source == "ai_detected")
        
        return {
            "narrative_summary": f"鏈?娆℃椿鍔ㄥ叡璁板綍浜? {len(self.moments)} 涓?鍏抽敭鏃跺埢锛屽叾涓?鐢ㄦ埛涓诲姩鏍囪?? {user_count} 涓?锛孉I 鑷?鍔ㄨ瘑鍒? {ai_count} 涓?銆?",
            "chapters": chapters,
            "team_insights": [
                f"鐢ㄦ埛涓诲姩鏍囪?颁簡 {user_count} 涓?璁や负閲嶈?佺殑鏃跺埢",
                f"AI 绯荤粺璇嗗埆浜? {ai_count} 涓?娼滃湪鐨勫崗浣滀寒鐐?"
            ],
            "reflection_questions": [
                "鍥為【杩欎簺鍏抽敭鏃跺埢锛屽摢涓?鏈�璁╀綘鍗拌薄娣卞埢锛熶负浠�涔堬紵",
                "鍦ㄦ爣璁扮殑鏃跺埢涓?锛屽洟闃熺殑鍗忎綔妯″紡鏈変粈涔堢壒鐐癸紵"
            ],
            "generated_at": datetime.now().isoformat(),
            "total_moments": len(self.moments)
        }
    
    # ============================================================
    # 馃敡 宸ュ叿鏂规硶
    # ============================================================
    
    def _format_time(self, seconds: float) -> str:
        """鏍煎紡鍖栨椂闂翠负 HH:MM:SS"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    
    def get_moments(self, source: str = None) -> List[Dict]:
        """
        鑾峰彇鍏抽敭鏃跺埢鍒楄〃
        
        Args:
            source: 鍙?閫夎繃婊? - 'user_anchor' 鎴? 'ai_detected'
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
        """鑾峰彇鍏抽敭鏃跺埢鍥剧墖璺?寰?"""
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
        """鐢熸垚 Linkography 鍥撅細nodes + edges锛堜娇鐢? LLM 浠庡崱鐗囧唴瀹规帹鏂?璺ㄦ椂鍒诲叧鑱旓級銆?

        璇存槑锛?
        - 浠呭厑璁稿紩鐢ㄨ緭鍏? moments 鐨勪俊鎭?锛屼笉瓒冲垯杩斿洖绌? edges銆?
        - 杈撳嚭缁撴瀯鐢ㄤ簬鍓嶇??鍙?瑙嗗寲锛歿"status":"ok", "nodes":[], "edges":[]}銆?
        """

        # 鍏滃簳
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

        # LLM 涓嶅彲鐢ㄦ椂锛屼粛杩斿洖 nodes锛宔dges 涓虹┖
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

        # 缁勭粐 prompt锛氬敖閲忕煭銆佷絾淇℃伅瓒冲??
        def _short(s: str, n: int) -> str:
            s = (s or "").strip().replace("\n", " ")
            return s if len(s) <= n else (s[:n] + "鈥?")

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
            "边类型建议：same_topic, follow_up, cause_effect, supports, contradicts, decision_related。"
        )

        prompt = (
            "给你一组 moments（按时间排序）。请输出一个 JSON 对象：\n"
            "{\n"
            "  \"nodes\": [{\"id\":\"...\",\"t\":1700000000.0,\"label\":\"...\"}],\n"
            "  \"edges\": [{\"source\":\"id1\",\"target\":\"id2\",\"type\":\"same_topic\",\"reason\":\"<=20字\"}]\n"
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
            # 鏈�鍧忓厹搴曪細浠呰妭鐐?
            print(f"鉂? JSON PARSE FAILED. Raw Output:\n{txt}")
            result["status"] = "parse_failed"
            result["nodes"] = [{"id": it["id"], "t": it["timestamp"], "label": _short(it.get("tagline") or it.get("note") or "", 12)} for it in items]
            result["edges"] = []

        # 瑙勮寖鍖? nodes锛氱‘淇濇瘡涓?杈撳叆 id 閮藉湪
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

        # 瑙勮寖鍖? edges锛氳繃婊ゆ棤鏁? id
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

        # 鎸夋椂闂存帓搴? nodes锛屽墠绔?鏇村ソ鐢?
        norm_nodes.sort(key=lambda x: float(x.get("t") or 0.0))
        result["nodes"] = norm_nodes
        result["edges"] = norm_edges

        self._linkography_cache = {"sig": sig, "ts": time.time(), "result": result}
        return result


# ============================================================
# 馃И 娴嬭瘯
# ============================================================

if __name__ == "__main__":
    import numpy as np
    
    print("=" * 60)
    print("馃幆 鍙岃建鍏抽敭鏃跺埢璇嗗埆绯荤粺 - 娴嬭瘯")
    print("=" * 60)
    
    # 鍒涘缓绠＄悊鍣?
    manager = KeyMomentsManager()
    
    # 妯℃嫙鐢ㄦ埛鏍囪??
    fake_frame = np.zeros((480, 640, 3), dtype=np.uint8)
    
    print("\n馃搷 娴嬭瘯鐢ㄦ埛鏍囪??...")
    moment1 = manager.mark_user_anchor(
        frame=fake_frame,
        frame_number=100,
        person_count=3,
        track_ids=[1, 2, 3],
        user_note="鍥㈤槦璁ㄨ?烘縺鐑?"
    )
    
    time.sleep(1)
    
    moment2 = manager.mark_user_anchor(
        frame=fake_frame,
        frame_number=250,
        person_count=2,
        track_ids=[1, 2],
        user_note="鍙戠幇鍏抽敭闂?棰?"
    )
    
    # 鑾峰彇缁熻??
    print("\n馃搳 缁熻?′俊鎭?:")
    stats = manager.get_stats()
    for k, v in stats.items():
        print(f"   {k}: {v}")
    
    # 鑾峰彇鎵�鏈夋椂鍒?
    print("\n馃搵 鎵�鏈夊叧閿?鏃跺埢:")
    moments = manager.get_moments()
    for m in moments:
        print(f"   [{m['source']}] {m['time_str']} - {m.get('user_note') or m.get('ai_description', 'N/A')}")
    
    # 鐢熸垚鍙欎簨
    print("\n馃摉 鐢熸垚鍙欎簨...")
    narrative = manager.generate_narrative()
    print(f"   鎽樿??: {narrative.get('narrative_summary', '')}")
    
    print("\n鉁? 娴嬭瘯瀹屾垚!")