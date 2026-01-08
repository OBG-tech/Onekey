# -*- coding: utf-8 -*-
"""
AI会议纪要生成模块
实时监听语音识别结果并生成结构化会议纪要
"""

import threading
import time
import os
from pathlib import Path
from datetime import datetime
from collections import deque
import json

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class MeetingNotesGenerator:
    """AI会议纪要生成器"""
    
    def __init__(self, output_dir=None, asr_engine=None):
        """
        初始化会议纪要生成器
        
        Args:
            output_dir: 纪要保存目录
            asr_engine: 实时语音识别引擎实例
        """
        self.output_dir = Path(output_dir) if output_dir else Path("integrated_data/meeting_notes")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.asr_engine = asr_engine
        self.is_generating = False
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        
        # 会议内容缓冲
        self.meeting_segments = deque(maxlen=500)
        self.current_summary = ""
        self.key_points = []
        self.action_items = []
        
        # AI配置 (LLM provider: qwen | claude)
        self.dashscope_api_key = os.environ.get("DASHSCOPE_API_KEY", "")
        self.claude_api_key = os.environ.get("ANTHROPIC_API_KEY", "") or os.environ.get("CLAUDE_API_KEY", "")
        self.llm_provider = os.environ.get("LLM_PROVIDER", "qwen").lower()
        self.model = os.environ.get("LLM_MODEL") or ("claude-3-5-haiku-20241022" if self.llm_provider.startswith("claude") else "qwen3-max")
        self.api_key = self.claude_api_key if self.llm_provider.startswith("claude") else self.dashscope_api_key
        if not self.api_key:
            provider_name = "Claude" if self.llm_provider.startswith("claude") else "DashScope"
            print(f"⚠️  未设置 {provider_name} API Key, AI会议纪要不可用")
            return
        
        self.client = None  # 延迟初始化
        
        # 生成线程
        self.generation_thread = None
        self.last_generation_time = 0
        self.generation_interval = 30  # 每30秒生成一次
        
        provider_label = "Claude Haiku 4.5" if self.llm_provider.startswith("claude") else "Qwen"
        print(f"✅ AI会议纪要生成器已就绪 ({provider_label}, model={self.model})")
    
    def _build_client(self):
        """根据提供者创建客户端"""
        if not self.api_key:
            raise RuntimeError("API Key 未配置")
        if self.llm_provider.startswith("claude"):
            try:
                from anthropic import Anthropic
            except ImportError as e:
                raise ImportError("请先安装 anthropic 库: pip install anthropic") from e
            return Anthropic(api_key=self.api_key)
        try:
            from openai import OpenAI
        except ImportError as e:
            raise ImportError("请先安装 openai 库: pip install openai>=1.0.0") from e
        # 禁用httpx的代理自动检测（trust_env=False），避免GNOME系统socks代理导致错误
        try:
            import httpx
            http_client = httpx.Client(trust_env=False)
        except Exception:
            http_client = None
        return OpenAI(api_key=self.api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", http_client=http_client)
    
    @staticmethod
    def _extract_anthropic_text(message):
        """提取 Anthropic 消息中的文本"""
        return "".join([block.text for block in getattr(message, "content", []) if getattr(block, "type", None) == "text"]).strip()
    
    def start(self):
        """开始生成会议纪要"""
        if not self.api_key:
            print("⚠️  AI会议纪要依赖不完整")
            return False

        # 预检：确保所选 provider 的客户端库可用
        try:
            _ = self._build_client()
        except ImportError as e:
            print(f"⚠️  AI会议纪要依赖不完整: {e}")
            return False
        
        if self.is_generating:
            print("⚠️  已在生成中")
            return False
        
        self.is_generating = True
        self.stop_event.clear()
        self.generation_thread = threading.Thread(target=self._generation_worker, daemon=True)
        self.generation_thread.start()
        print("🤖 AI会议纪要生成已启动")
        return True
    
    def stop(self):
        """停止生成会议纪要"""
        if not self.is_generating:
            return
        
        self.is_generating = False
        self.stop_event.set()
        
        if self.generation_thread:
            # 既然有事件通知，线程应该很快退出，缩短join超时
            self.generation_thread.join(timeout=2)
        
        # 保存最终纪要
        self._save_meeting_notes()
        
        print("✅ AI会议纪要生成已停止")
    
    def _generation_worker(self):
        """生成工作线程"""
        while self.is_generating:
            try:
                current_time = time.time()
                
                # 检查是否需要生成
                if current_time - self.last_generation_time >= self.generation_interval:
                    self._collect_transcript()
                    
                    if len(self.meeting_segments) >= 3:  # 至少有3个片段才生成
                        self._generate_notes()
                        self.last_generation_time = current_time
                
                # 等待5秒或直到收到停止信号
                if self.stop_event.wait(timeout=5):
                    break
                
            except Exception as e:
                print(f"❌ 生成线程错误: {e}")
                if self.stop_event.wait(timeout=10):
                    break
    
    def _collect_transcript(self):
        """从ASR引擎收集转录内容"""
        if not self.asr_engine:
            return
        
        # 获取所有片段
        segments = self.asr_engine.get_all_segments()
        
        with self.lock:
            # 只添加新片段
            existing_count = len(self.meeting_segments)
            new_segments = segments[existing_count:]
            
            for seg in new_segments:
                if seg.is_final:
                    self.meeting_segments.append({
                        "text": seg.text,
                        "timestamp": seg.timestamp
                    })
    
    def _generate_notes(self):
        """生成会议纪要"""
        with self.lock:
            if not self.meeting_segments:
                return
            
            # 构建对话历史
            transcript_text = "\n".join([
                f"[{datetime.fromtimestamp(seg['timestamp']).strftime('%H:%M:%S')}] {seg['text']}"
                for seg in self.meeting_segments
            ])
        
        if not transcript_text.strip():
            return
        
        try:
            print("🤖 正在生成会议纪要...")
            
            # 调用AI生成纪要
            system_prompt = "你是一个专业的会议纪要助手,擅长从对话中提取关键信息。"
            prompt = f"""请分析以下会议对话内容,生成结构化会议纪要。

会议对话:
{transcript_text}

请按以下格式输出JSON:
{{
    "summary": "会议整体概要(2-3句话)",
    "key_points": ["关键要点1", "关键要点2", "关键要点3"],
    "action_items": ["待办事项1", "待办事项2"],
    "participants_mentioned": ["提到的参与者姓名"],
    "topics": ["讨论的主题"]
}}

只返回JSON,不要其他说明。"""
            
            client = self._build_client()
            
            if self.llm_provider.startswith("claude"):
                response = client.messages.create(
                    model=self.model,
                    system=system_prompt,
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=1500,
                    temperature=0.3
                )
                result_text = self._extract_anthropic_text(response)
            else:
                response = client.chat.completions.create(
                    model=self.model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    temperature=0.3,
                    max_tokens=1500
                )
                result_text = response.choices[0].message.content.strip()
            
            # 解析JSON结果
            if result_text.startswith("```json"):
                result_text = result_text.replace("```json", "").replace("```", "").strip()
            
            result = json.loads(result_text)
            
            with self.lock:
                self.current_summary = result.get("summary", "")
                self.key_points = result.get("key_points", [])
                self.action_items = result.get("action_items", [])
            
            print(f"✅ 会议纪要已更新 (要点: {len(self.key_points)}, 待办: {len(self.action_items)})")
            
        except Exception as e:
            print(f"❌ 生成纪要失败: {e}")
    
    def _save_meeting_notes(self):
        """保存会议纪要到文件"""
        if not self.current_summary and not self.key_points:
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = self.output_dir / f"meeting_notes_{timestamp}.json"
        
        with self.lock:
            notes = {
                "timestamp": timestamp,
                "summary": self.current_summary,
                "key_points": self.key_points,
                "action_items": self.action_items,
                "segment_count": len(self.meeting_segments)
            }
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(notes, f, ensure_ascii=False, indent=2)
        
        # 也保存可读的文本版本
        txt_filepath = self.output_dir / f"meeting_notes_{timestamp}.txt"
        with open(txt_filepath, 'w', encoding='utf-8') as f:
            f.write("=" * 60 + "\n")
            f.write(f"会议纪要 - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 60 + "\n\n")
            
            f.write("📝 会议概要:\n")
            f.write(f"{notes['summary']}\n\n")
            
            if notes['key_points']:
                f.write("🔑 关键要点:\n")
                for i, point in enumerate(notes['key_points'], 1):
                    f.write(f"{i}. {point}\n")
                f.write("\n")
            
            if notes['action_items']:
                f.write("✅ 待办事项:\n")
                for i, item in enumerate(notes['action_items'], 1):
                    f.write(f"{i}. {item}\n")
                f.write("\n")
        
        print(f"💾 会议纪要已保存: {filepath}")
    
    def get_current_notes(self):
        """获取当前会议纪要"""
        with self.lock:
            return {
                "summary": self.current_summary,
                "key_points": self.key_points,
                "action_items": self.action_items,
                "segment_count": len(self.meeting_segments),
                "is_generating": self.is_generating
            }
    
    def get_status(self):
        """获取生成器状态"""
        with self.lock:
            return {
                "is_generating": self.is_generating,
                "available": bool(self.api_key and OPENAI_AVAILABLE),
                "segment_count": len(self.meeting_segments),
                "has_notes": bool(self.current_summary or self.key_points),
                "message": "运行中" if self.is_generating else "就绪"
            }


# 全局实例
_global_generator = None


def get_meeting_notes_generator(output_dir=None, asr_engine=None):
    """获取全局会议纪要生成器实例"""
    global _global_generator
    if _global_generator is None:
        _global_generator = MeetingNotesGenerator(output_dir=output_dir, asr_engine=asr_engine)
    return _global_generator


if __name__ == "__main__":
    # 测试代码
    generator = MeetingNotesGenerator()
    print("状态:", generator.get_status())
