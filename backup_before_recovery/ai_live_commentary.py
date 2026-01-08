#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🎬 AI直播间评论系统
为创客马拉松生成激情评论和观众互动
"""

import os
import random
import time
import json
from typing import Dict, List, Optional
from dataclasses import dataclass, field


@dataclass
class CommentaryMessage:
    """评论消息"""
    content: str
    author: str
    role: str  # 'commentator' | 'audience' | 'user'
    emoji: str
    timestamp: float = field(default_factory=time.time)


class CommentatorAgent:
    """激情解说员AI"""
    
    def __init__(self, name: str = "解说员", api_key: str = ""):
        self.name = name
        self.api_key = api_key
        self.emoji = "🎙️"
        
        # 解说员人格 - 客观专业风格（像NFL解说员）
        self.persona = """你是创客马拉松的现场解说员，风格像NFL赛事解说员——专业、客观、有画面感。

【解说原则】
- 忠实镜子：描述看到和听到的内容，不夸张、不瞎猜
- 口语化表达：用自然的口语，不用书面语
- 适度热情：有节奏感，但保持专业性
- 少用网络梗：偶尔可以，但要自然（每句最多1个）

【语言风格】
- 现场感：用"正在...""看到...""听到...""刚刚..."
- 描述动作："XX走向白板""两人正在讨论""XX在敲代码"
- 转述对话：直接引用重要的话
- 说明进度："已完成X""正在处理Y""下一步计划Z"
- 适度评价：可以说"进展顺利""遇到困难"等客观评价

禁忌：
- 别太娱乐化（少用YYDS、芭比Q等）
- 别瞎夸张（基于实际内容）
- 别用书面语（根据、综上等）

示例风格：
✅ "看到团队正在调试传感器，数据出现了异常，大家在排查原因"
✅ "听到张工说'这个接口有问题'，王工正在检查电路板"
✅ "刚刚完成了第一版原型，现在开始测试，进展不错"
✅ "两人围在白板前讨论架构，看起来遇到了设计上的分歧"
❌ "哎呦！芭比Q了！Bug又来了！YYDS！"（太娱乐化）
❌ "根据现场情况分析，团队正在进行技术攻关"（太书面）
"""
    
    def react(self, context: Dict) -> Optional[str]:
        """根据上下文生成评论"""
        try:
            from openai import OpenAI
            
            # 构建prompt
            recent_transcript = context.get('recent_transcript', '')
            key_moment = context.get('key_moment_detected', False)
            
            if not recent_transcript and not key_moment:
                # 无内容时的闲聊
                idle_comments = [
                    "观众朋友们，选手们正在紧张coding中！💻",
                    "这个专注度！这就是Hackathon的魅力！🔥",
                    "让我们看看接下来会发生什么...👀",
                    "氛围已经紧张起来了！谁能笑到最后？🎯"
                ]
                return random.choice(idle_comments)
            
            prompt = f"""基于以下上下文，生成一句客观的解说评论（20-50字）：

最近转写：
{recent_transcript[:500] if recent_transcript else '(安静状态)'}

{'🔥 检测到关键时刻！' if key_moment else ''}

要求：
1. 一句话，客观描述现场情况
2. 用口语化表达，但不要太娱乐化
3. 基于实际内容，不夸张不瞎猜
4. 可带1个emoji（可选）
5. 少用网络梗（偶尔可以，但要自然）
"""
            
            client = OpenAI(
                api_key=self.api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
            )
            
            response = client.chat.completions.create(
                model=os.environ.get("LLM_MODEL", "qwen-max"),
                messages=[
                    {"role": "system", "content": self.persona},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.6,
                max_tokens=100
            )
            
            comment = response.choices[0].message.content.strip()
            return comment if comment else None
            
        except Exception as e:
            print(f"⚠️ 评论员生成失败: {e}")
            return None


class AudienceAgent:
    """虚拟观众AI"""
    
    # 预定义观众人格（16个角色，覆盖创客马拉松各类观众）
    PERSONAS = {
        "代码狂人老王": {
            "emoji": "👨‍💻", 
            "trait": "资深程序员，经常吐槽技术选型，喜欢说'我早说了''这不就是XXX模式吗'，爱用专业术语"
        },
        "萌新小美": {
            "emoji": "👩‍🎨", 
            "trait": "初学者，容易被震撼到，经常说'学到了''原来如此''卧槽nb'，很激动"
        },
        "产品经理张三": {
            "emoji": "🕴️", 
            "trait": "产品经理视角，关注用户体验和需求，会问'这个有什么用''需求明确吗''用户会买单吗'"
        },
        "设计师Lisa": {
            "emoji": "🎨", 
            "trait": "设计师，对UI/UX极其敏感，会点评配色和布局，说话文艺，经常用'质感''留白''呼吸感'"
        },
        "乐天派小明": {
            "emoji": "😎", 
            "trait": "乐观派，总是鼓励选手，喜欢发666、加油、冲冲冲，永远充满正能量"
        },
        "吃瓜群众阿强": {
            "emoji": "🍿", 
            "trait": "围观群众，爱看热闹，经常说'坐等翻车''这波稳了''要出大事'，喜欢开玩笑"
        },
        "技术大佬陈工": {
            "emoji": "🧙‍♂️", 
            "trait": "技术专家，一眼看出问题所在，说话简洁有力，经常一针见血指出bug或优化点"
        },
        "夜猫子程序员": {
            "emoji": "🦉", 
            "trait": "深夜还在看直播的程序员，精神不太好，会吐槽coffee不够，偶尔梦游发言"
        },
        "创业导师老李": {
            "emoji": "💼", 
            "trait": "创业导师，关注商业模式和市场价值，经常问'盈利模式是啥''用户规模有多大'"
        },
        "投资人王总": {
            "emoji": "💰", 
            "trait": "投资人视角，评估项目可行性和潜力，说话直接，'这个赛道如何''团队背景怎样'"
        },
        "学生观众小芳": {
            "emoji": "📚", 
            "trait": "大学生，学习心态，经常问'这个怎么实现的''能分享代码吗'，求知欲强"
        },
        "资深创客老赵": {
            "emoji": "🔧", 
            "trait": "Maker文化代表，强调动手实践，'Talk is cheap, show me the demo'，注重实操"
        },
        "行业专家张老师": {
            "emoji": "🎓", 
            "trait": "垂直领域专家，提供专业见解，说话严谨，'从行业角度看...''根据数据显示...'"
        },
        "UX研究员小雨": {
            "emoji": "🔍", 
            "trait": "用户研究专家，关注用户需求挖掘，'用户真的需要吗''痛点在哪''有做用户访谈吗'"
        },
        "全栈工程师Alex": {
            "emoji": "⚡", 
            "trait": "全栈开发，技术全面，经常点评架构和技术栈，'前后端分离''微服务''高并发'"
        },
        "AI爱好者小林": {
            "emoji": "🤖", 
            "trait": "AI/机器学习爱好者，关注算法和模型，'这个可以用神经网络''训练数据够吗'，很geek"
        },
    }
    
    def __init__(self, name: str = "代码狂人老王", api_key: str = ""):
        self.name = name
        self.api_key = api_key
        
        persona_info = self.PERSONAS.get(name, list(self.PERSONAS.values())[0])
        self.emoji = persona_info["emoji"]
        self.trait = persona_info["trait"]
    
    def react(self, context: Dict) -> Optional[str]:
        """生成观众评论（更简短）"""
        try:
            # 观众有50%概率不发言
            if random.random() < 0.5:
                return None
            
            recent_transcript = context.get('recent_transcript', '')
            key_moment = context.get('key_moment_detected', False)
            
            # 快速反应模式：使用模板
            if not self.api_key or len(recent_transcript) < 20:
                return self._template_comment(key_moment)
            
            # LLM生成模式（简化版）
            from openai import OpenAI
            
            prompt = f"""你是{self.name}，性格：{self.trait}

最近发生：{recent_transcript[:300]}
{'🔥 关键时刻！' if key_moment else ''}

生成一句简短评论（5-15字），符合你的性格。"""
            
            client = OpenAI(
                api_key=self.api_key,
                base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
            )
            
            response = client.chat.completions.create(
                model="qwen-max",
                messages=[{"role": "user", "content": prompt}],
                temperature=1.0,
                max_tokens=50
            )
            
            comment = response.choices[0].message.content.strip()
            return comment if len(comment) <= 30 else self._template_comment(key_moment)
            
        except Exception:
            return self._template_comment(context.get('key_moment_detected', False))
    
    def _template_comment(self, key_moment: bool) -> str:
        """模板评论（快速生成，适度使用最新热梗）"""
        if key_moment:
            templates = {
                "代码狂人老王": ["稳了！", "YYDS！💪", "人马了！", "这波操作可以", "6到飞起！"],
                "萌新小美": ["哇！🤩", "绝绝子！", "DNA动了！", "太厉害了！", "多巴胺拉满！"],
                "产品经理张三": ["有意思🤔", "这波不亏！", "拿捕了！", "用户会买单"],
                "设计师Lisa": ["界面City了✨", "配色YYDS", "UI很舒服", "这个DNA动了"],
                "乐天派小明": ["666", "冲冲冲！💪", "爆火！🎉", "牛逼！"],
                "吃瓜群众阿强": ["这波稳了🍿", "坂上走了！", "显眼包啊！", "火钳刘明"],
                "技术大佬陈工": ["思路对了", "可以的", "稳", "没毛病"],
                "夜猫子程序员": ["呼...还行🦉", "爷青回！", "可以睡了"],
                "创业导师老李": ["商业模式清晰！", "MVP绝了", "市场遥遥领先"],
                "投资人王总": ["赛道YYDS💰", "可以谈谈", "团队靠谱"],
                "学生观众小芳": ["学到了！📚", "绝绝子！", "太酷了"],
                "资深创客老赵": ["整活！🔧", "Demo不错", "实践出真知"],
                "行业专家张老师": ["从行业角度看可行🎓", "专业", "有深度"],
                "UX研究员小雨": ["需求拿捕了🔍", "痛点明确", "研究做得深"],
                "全栈工程师Alex": ["架构绝了⚡", "技术栈YYDS", "buff叠满了"],
                "AI爱好者小林": ["这个AI绝了🤖", "算法思路清晰", "模型YYDS"],
            }
        else:
            templates = {
                "代码狂人老王": ["嗯...", "看看", "这波能行吗", "别芭比Q了", "哈基米了？"],
                "萌新小美": ["好紧张😰", "会怎么做呢", "有点破防", "学习学习"],
                "产品经理张三": ["需求明确吗🤔", "做的是啥", "有点无语", "痛点在哪"],
                "设计师Lisa": ["色彩可以", "排版还行", "字体选择...", "看看呈现"],
                "乐天派小明": ["冲！💪", "相信你们！", "稳住", "加油"],
                "吃瓜群众阿强": ["坐等翻车🍿", "栉Q", "紧张刺激", "下注"],
                "技术大佬陈工": ["...", "观察", "看细节", "等等"],
                "夜猫子程序员": ["困了🦉", "coffee呢", "撑住", "整不会了"],
                "创业导师老李": ["模式清晰吗💼", "盈利点在哪", "竞品分析了吗"],
                "投资人王总": ["赛道如何💰", "看看团队", "数据呢"],
                "学生观众小芳": ["这个怎么做的📚", "求教", "好好学习"],
                "资深创客老赵": ["Show me the code🔧", "开始做了吗", "动手动手"],
                "行业专家张老师": ["观察🎓", "等数据", "看趋势"],
                "UX研究员小雨": ["访谈了吗🔍", "痛点在哪", "需求验证"],
                "全栈工程师Alex": ["看架构⚡", "技术选型", "性能如何"],
                "AI爱好者小林": ["能用深度学习吗🤖", "模型选择", "数据呢"],
            }
        
        options = templates.get(self.name, templates["乐天派小明"])
        return random.choice(options)


class AILiveCommentary:
    """AI直播间管理器"""
    
    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.environ.get("DASHSCOPE_API_KEY", "")
        self.running = False
        
        # 只保留解说员（去掉虚拟观众）
        self.commentator = CommentatorAgent("解说员", self.api_key)
        
        print("🎬 AI解说员已初始化")
    
    def start(self):
        """启动解说"""
        self.running = True
        print("🔴 AI解说已启动")
    
    def stop(self):
        """停止解说"""
        self.running = False
        print("⏸️ AI解说已停止")
    
    def generate_commentary(self, context: Dict) -> Dict[str, any]:
        """
        生成评论
        
        Args:
            context: {
                'recent_transcript': str,  # 最近转写
                'key_moment_detected': bool,  # 是否检测到关键时刻
                'video_context': str,  # 视频描述（可选）
            }
        
        Returns:
            {
                'commentator': CommentaryMessage or None,
                'audience': []  # 已移除虚拟观众
            }
        """
        if not self.running:
            return {'commentator': None, 'audience': []}
        
        try:
            # 只保留解说员发言
            commentator_text = self.commentator.react(context)
            commentator_msg = None
            if commentator_text:
                commentator_msg = CommentaryMessage(
                    content=commentator_text,
                    author=self.commentator.name,
                    role='commentator',
                    emoji=self.commentator.emoji
                )
            
            return {
                'commentator': commentator_msg,
                'audience': []  # 不再生成虚拟观众评论
            }
            
        except Exception as e:
            print(f"⚠️ 生成评论失败: {e}")
            return {'commentator': None, 'audience': []}
    
    def get_status(self) -> Dict:
        """获取状态"""
        return {
            'running': self.running,
            'commentator': self.commentator.name,
            'audience_count': len(self.audience)
        }


# 测试代码
if __name__ == "__main__":
    # 测试评论生成
    ai_live = AILiveCommentary()
    ai_live.start()
    
    test_context = {
        'recent_transcript': '正在调试代码...发现了一个bug...尝试修复...',
        'key_moment_detected': True
    }
    
    result = ai_live.generate_commentary(test_context)
    
    print("\n🎙️ 评论员：")
    if result['commentator']:
        print(f"  {result['commentator'].emoji} {result['commentator'].content}")
    
    print("\n👥 观众反应：")
    for msg in result['audience']:
        print(f"  {msg.emoji} {msg.author}: {msg.content}")
