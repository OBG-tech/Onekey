#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regenerate history key-moment card taglines via LLM.

Purpose
- Generate/repair `ai_tagline` for historical moments so cards are scannable.
- Uses: transcript + existing ai_description + per-moment _context.txt + global context.txt

Notes
- This script does NOT modify application code.
- It edits `integrated_data/key_moments/moments.json` (with a timestamped backup).

Usage examples
  # dry run only (no writes)
  KEY_MOMENTS_REGEN_TAGLINES_DRYRUN=1 python3 regen_history_taglines.py

  # write back, process at most 50
  python3 regen_history_taglines.py --limit 50

  # use a different camera/project root
  python3 regen_history_taglines.py --moments-dir integrated_data/key_moments

Environment
- LLM_PROVIDER (qwen|claude)
- DASHSCOPE_API_KEY / ANTHROPIC_API_KEY
- LLM_MODEL (optional)
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple


def _read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def _needs_fix(tagline: str) -> bool:
    tg = (tagline or "").strip()
    if not tg:
        return True
    if len(tg) > 80:
        return True
    if "\n" in tg:
        return True
    if any(x in tg for x in ("详细描述", "证据摘录", "上下文定位")):
        return True
    # previously-generated generic fallback should be regenerated
    if any(x in tg for x in ("进行某项活动", "屏幕/设备", "有人在屏前活动")):
        return True
    return False


def _build_prompt(old_desc: str, transcript: str, per_ctx: str, global_kb: str) -> str:
    return f"""你是一个严格的“卡片一句话描述生成器”。

目标：基于【卡片点击后显示的描述（ai_description）】为一条“历史关键时刻”生成一条适合卡片扫读的中文短描述（ai_tagline）。

硬性要求（必须全部满足）：
1) 输出必须是【单行中文】（不要换行）
2) 长度：25–30个中文字符（尽量接近28字；不含空格）
3) 必须包含2个emoji（放在句首/句中均可，但不要堆叠超过2个）
4) 必须包含：主体/人数 + 具体动作/事件 + 关键对象（电脑/代码/屏幕/白板/相机/调试等）
5) 禁止主观评价/煽情词（不要“精彩/热烈/深度/氛围/震撼/太强了”）
6) 不要编造事实；信息不足用“有人/多人/画面未明确”表达
7) 句末必须追加标签区：
   - 置信度：🏷️conf=高|中|低
   - 反思匹配：🏷️reflect=是|否

重要：优先使用【ai_description】里的信息，其次才参考转写/上下文。

【卡片点击描述 ai_description】
{old_desc or "(无)"}

【转写 transcript】
{transcript or "(无语音)"}

【该时刻上下文 per_context】
{per_ctx.strip() or "(无)"}

【全局背景信息/知识库】
{(global_kb or "").strip()[:1500] if global_kb else "(无)"}

请只输出一行 ai_tagline："""


def _clean_tagline(s: str) -> str:
    t = (s or "").strip().replace("\n", " ")
    for prefix in ("标签：", "卡片摘要：", "摘要：", "ai_tagline："):
        if t.startswith(prefix):
            t = t[len(prefix):].strip()
    # normalize spaces: keep single spaces (useful to separate tags)
    t = " ".join(t.split())
    return t.strip()


def _ensure_tags_and_length(tagline: str) -> str:
    """Ensure required tags exist and basic emoji presence.

    Note: we avoid strict length enforcement here; the prompt should produce 25–30 chars.
    This function only patches missing tags / emojis for consistency.
    """
    t = (tagline or "").strip()
    if not t:
        return t

    if "🏷️conf=" not in t:
        t = t + " 🏷️conf=中"
    if "🏷️reflect=" not in t:
        t = t + " 🏷️reflect=否"

    # Ensure there are (at least) two emojis. Best-effort: detect common emoji unicode ranges.
    import re

    emoji_re = re.compile(
        r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF]"
    )
    emojis = emoji_re.findall(t)

    if len(emojis) == 0:
        t = "🔎🎬" + t
    elif len(emojis) == 1:
        t = "🎬" + t
    elif len(emojis) > 2:
        # keep only first two emojis by removing extras after the first two occurrences
        kept = 0
        out_chars: list[str] = []
        for ch in t:
            if emoji_re.match(ch):
                kept += 1
                if kept > 2:
                    continue
            out_chars.append(ch)
        t = "".join(out_chars)

    return t


def _load_moments(moments_json: Path) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    data = json.loads(_read_text(moments_json) or "{}")
    moments = data.get("moments") or []
    if not isinstance(moments, list):
        moments = []
    return data, moments


def _backup_file(src: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = src.parent / f"{src.stem}.backup_{ts}{src.suffix}"
    shutil.copy2(src, dst)
    return dst


# Optional: provide key via env (recommended). Do NOT hardcode secrets in source control.
_DEFAULT_DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "").strip()


def _run_llm(prompt: str, temperature: float = 0.2, max_tokens: int = 80) -> str:
    """Run an LLM.

    Preference order:
    1) Use the project's own LLM plumbing from `key_moments_manager.py` (handles Qwen/Claude/etc).
    2) Use OpenAI-compatible SDK if available.
    3) Heuristic fallback (offline).
    """

    provider = (os.environ.get("LLM_PROVIDER") or "").strip().lower()

    # 0) Try project-native LLM helper first, but skip it for qwen/dashscope to avoid side effects.
    if provider not in {"qwen", "dashscope"}:
        try:
            from key_moments_manager import KeyMomentsManager  # type: ignore

            km = KeyMomentsManager(data_dir=Path(__file__).parent / "integrated_data")

            for fn_name in ("_run_text_llm", "run_text_llm", "_call_text_llm", "call_text_llm"):
                fn = getattr(km, fn_name, None)
                if callable(fn):
                    out = fn(prompt, temperature=temperature, max_tokens=max_tokens)
                    if isinstance(out, str) and out.strip():
                        return out.strip()

            build = getattr(km, "_build_llm_client", None)
            if callable(build):
                client = build()
                model = getattr(km, "text_model", None) or os.environ.get("LLM_MODEL")
                if hasattr(client, "chat") and hasattr(client.chat, "completions") and hasattr(client.chat.completions, "create"):
                    resp = client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": prompt}],
                        temperature=temperature,
                        max_tokens=max_tokens,
                    )
                    if hasattr(resp, "choices") and resp.choices:
                        msg = getattr(resp.choices[0], "message", None)
                        if msg is not None:
                            content = getattr(msg, "content", None)
                            if isinstance(content, str) and content.strip():
                                return content.strip()
        except Exception:
            pass

    # 1) try openai-compatible client (Qwen via DashScope is OpenAI-compatible)
    try:
        # Prefer env, then optional default read above.
        api_key = (os.environ.get("DASHSCOPE_API_KEY") or _DEFAULT_DASHSCOPE_API_KEY).strip()
        provider = (os.environ.get("LLM_PROVIDER") or "").strip().lower()
        model = os.environ.get("LLM_MODEL")

        if api_key:
            # If user intends qwen via dashscope, set base URL if supported by client
            # DashScope OpenAI-compatible endpoint:
            # https://dashscope.aliyuncs.com/compatible-mode/v1
            base_url = os.environ.get("OPENAI_BASE_URL")
            if provider in {"qwen", "dashscope"} and not base_url:
                os.environ["OPENAI_BASE_URL"] = "https://dashscope.aliyuncs.com/compatible-mode/v1"

            import openai  # type: ignore

            # old openai SDK supports openai.api_base/openai.base_url depending on version
            if provider in {"qwen", "dashscope"}:
                if hasattr(openai, "api_base"):
                    openai.api_base = os.environ.get("OPENAI_BASE_URL")
                elif hasattr(openai, "base_url"):
                    openai.base_url = os.environ.get("OPENAI_BASE_URL")

            openai.api_key = api_key
            use_model = model or ("qwen-plus" if provider in {"qwen", "dashscope"} else "gpt-4o-mini")

            try:
                resp = openai.ChatCompletion.create(
                    model=use_model,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return resp["choices"][0]["message"]["content"].strip()
            except Exception:
                resp = openai.Completion.create(
                    model=use_model,
                    prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                return resp["choices"][0]["text"].strip()
    except Exception:
        pass

    # 2) Fallback heuristic generator (avoid external calls) — produce a concise Chinese tagline
    try:
        text = prompt

        def pick_after(label: str) -> str:
            idx = text.find(label)
            if idx < 0:
                return ""
            part = text[idx + len(label) :]
            for marker in ["【转写", "【该时刻上下文", "【全局背景信息", "\n\n"]:
                j = part.find(marker)
                if j >= 0:
                    part = part[:j]
            return part.strip().replace("\n", " ").strip()

        old_desc = pick_after("【旧AI描述")
        transcript = pick_after("【转写")
        per_ctx = pick_after("【该时刻上下文")

        src = (transcript + " " + old_desc + " " + per_ctx).strip()
        s = src

        import re

        m = re.search(r"(\d+)人", s)
        if m:
            people = f"{m.group(1)}人"
        else:
            if re.search(r"(大家|团队|多人|几人|几位)", s):
                people = "多人"
            else:
                people = "有人"

        actions: list[str] = []
        objs: list[str] = []
        kw_actions = [
            (r"敲|键盘|打字|coding|code", "敲键盘"),
            (r"调试|debug|修复|修复代码|修bug", "调试代码"),
            (r"讲|讲解|解说|说明|演示", "讲解"),
            (r"讨论|商讨", "讨论"),
            (r"看屏幕|看着屏幕|指着屏幕", "指着屏幕"),
            (r"测试|跑测试", "测试"),
        ]
        kw_objs = [
            (r"电脑|笔记本|laptop", "电脑"),
            (r"屏幕|显示器", "屏幕"),
            (r"代码|repo|代码库", "代码"),
            (r"白板", "白板"),
            (r"相机|摄像头", "相机"),
        ]
        s_lower = s.lower()
        for pat, act in kw_actions:
            if re.search(pat, s_lower):
                actions.append(act)
        for pat, o in kw_objs:
            if re.search(pat, s_lower):
                objs.append(o)

        action = actions[0] if actions else "进行某项活动"
        obj = objs[0] if objs else "屏幕/设备"

        tagline = f"{people}在{action}，聚焦{obj}"
        if len(tagline) > 45:
            tagline = tagline[:44].rstrip() + "…"
        return tagline
    except Exception:
        return "有人在屏前活动"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--moments-dir", default="integrated_data/key_moments", help="Directory containing moments.json")
    ap.add_argument("--limit", type=int, default=50, help="Max moments to process")
    ap.add_argument("--dry-run", action="store_true", help="Print changes, do not write moments.json")
    ap.add_argument("--only-missing", action="store_true", help="Only fill empty ai_tagline (skip other fixes)")
    ap.add_argument("--force", action="store_true", help="Force regenerate taglines even if they look OK")
    ap.add_argument("--skip-no-desc", dest="skip_no_desc", action="store_true", default=True, help="Skip moments without ai_description (default: on)")
    ap.add_argument("--no-skip-no-desc", dest="skip_no_desc", action="store_false", help="Do not skip moments without ai_description")
    args = ap.parse_args()

    # env override
    dry_run = args.dry_run or (os.environ.get("KEY_MOMENTS_REGEN_TAGLINES_DRYRUN", "0").strip().lower() in {"1", "true", "yes"})

    moments_dir = Path(args.moments_dir).expanduser().resolve()
    moments_json = moments_dir / "moments.json"
    if not moments_json.exists():
        print(f"❌ moments.json not found: {moments_json}")
        return 2

    # global KB
    global_kb = _read_text(moments_dir.parent.parent / "context.txt")

    data, moments = _load_moments(moments_json)

    to_process: List[Dict[str, Any]] = []
    skipped_no_desc = 0
    for m in moments:
        old_desc = (m.get("ai_description") or "")
        if args.skip_no_desc and not str(old_desc).strip():
            skipped_no_desc += 1
            continue

        tg = (m.get("ai_tagline") or "").strip()
        if args.force:
            to_process.append(m)
            continue
        if args.only_missing:
            if not tg:
                to_process.append(m)
        else:
            if _needs_fix(tg):
                to_process.append(m)

    to_process = to_process[: max(0, int(args.limit))]

    print(f"📦 moments.json: {moments_json}")
    print(f"🧠 global context.txt: {bool(global_kb)} ({len(global_kb)} chars)")
    print(f"🧾 candidates: {len(to_process)} (limit={args.limit}, dry_run={dry_run}, force={args.force})")
    if args.skip_no_desc:
        print(f"⏭️ skipped (no ai_description): {skipped_no_desc}")

    changed = 0
    for i, m in enumerate(to_process, 1):
        mid = str(m.get("id") or "")
        old_tg = (m.get("ai_tagline") or "").strip()
        old_desc = (m.get("ai_description") or "").strip()
        transcript = (m.get("transcript") or "").strip()

        per_ctx = _read_text(moments_dir / f"{mid}_context.txt") if mid else ""
        prompt = _build_prompt(old_desc, transcript, per_ctx, global_kb)

        print(f"\n[{i}/{len(to_process)}] id={mid}")
        if old_tg:
            print(f"  old_tagline: {old_tg}")

        # If using qwen/dashscope, avoid importing KeyMomentsManager (it has side effects/log noise).
        provider = (os.environ.get("LLM_PROVIDER") or "").strip().lower()
        if provider in {"qwen", "dashscope"}:
            out = _run_llm(prompt, temperature=0.2, max_tokens=120)
        else:
            out = _run_llm(prompt, temperature=0.2, max_tokens=120)

        new_tg = _ensure_tags_and_length(_clean_tagline(out))
        print(f"  new_tagline: {new_tg}")

        if new_tg and new_tg != old_tg:
            if not dry_run:
                m["ai_tagline"] = new_tg
            changed += 1

    if dry_run:
        print(f"\n🧪 DRYRUN done. Would change: {changed}")
        return 0

    if changed:
        backup = _backup_file(moments_json)
        print(f"\n🗄️ backup created: {backup}")
        data["moments"] = moments
        with open(moments_json, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"✅ write complete. changed={changed}")
    else:
        print("\nℹ️ no changes")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
