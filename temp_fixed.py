# -*- coding: utf-8 -*-
"""
? 双轨关键时刻识别系统 (Dual-Track Key Moments Manager)

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
    
    # 场景信息
    person_count: int = 0            # 当前画面人数
    track_ids: List[int] = field(default_factory=list)  # 活跃的追踪ID
    
    # 叙事元素 (由 LLM 生成)
    narrative_role: str = ""         # 在叙事中的角色: opening/rising/climax/falling/resolution
    narrative_text: str = ""         # 叙事文本
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        d = asdict(self)
        # 鍓嶇??鐢? `||` 鍋氬厹搴曟椂锛岀┖瀛楃?︿覆/None 鎵嶄細姝ｇ‘鍥為