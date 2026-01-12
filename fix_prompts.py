
import os

file_path = "/home/artinx/onekey/key_moments_manager.py"
with open(file_path, "rb") as f:
    content = f.read().decode("utf-8")

# Replacement 1: _analyze_frame_with_ai prompt
start_marker_1 = 'image_base64 = base64.b64encode(buffer).decode(\'utf-8\')'
end_marker_1 = 'result_text = self._run_vision_llm('

new_prompt_1 = """
            prompt = \"\"\"你是协作学习研究专家。分析这张协作学习场景的图片。

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
    "behavior_code": "如 Eng-Flow",
    "specific_behavior": "如 [R2]论证推理",
    "description": "简短描述正在发生什么",
    "observable_behaviors": ["可观察行为1"],
    "emotions": ["情绪状态"],
    "tags": ["标签1"]
}

只返回JSON，不要其他内容。\"\"\"

            """

# Replacement 2: analyze_with_multimodal prompt
start_marker_2 = 'track_ids = track_ids or []'
end_marker_2 = 'result_text = self._run_vision_llm('

new_prompt_2 = """
            prompt = f\"\"\"你是协作学习研究专家，使用专业的行为编码框架分析协作场景。

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

只返回JSON，不要其他内容。\"\"\"
            """

# Replacement 3: generate_meeting_notes prompt
start_marker_3 = 'zh_note_instr = "All output fields (summary, key_points, action_items, decisions) must be in Simplified Chinese."'
end_marker_3 = 'result_text = self._run_text_llm('

new_prompt_3 = """
            prompt = f\"\"\"[{zh_note_instr}] 
            你是创客马拉松现场解说员，像NFL赛事解说员一样播报——专业、客观、但有画面感。

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

**key_points（3-5个要点，每条15-25字）：**
客观事实，口语化短句
✅ 好："电路板的三个接口接触不良，王工正在重新焊接"
✅ 好："测试了A、B、C三个传感器型号，最后决定用A型"
✅ 好："张工提出加滤波电路的建议，团队讨论后采纳了"

**action_items（下一步计划）：**
客观具体的下一步
✅ 好："需要采购A型传感器模块，预计今天完成"
✅ 好："准备修复接口Bug，然后重新测试"

**decisions（已确定的决策）：**
说清选择和原因
✅ 好："决定使用React框架，因为团队更熟悉这个技术栈"
✅ 好："采纳方案B，理由虽然复杂但稳定性更好"

🔧 **解说技巧：**
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
- 别太娱乐化：少用"YYDS""芭比Q""DNA动了"等网络语
- 别瞎夸张：基于实际内容，不煽情不吐槽
- 内容不足时，summary写："现场较安静，等待下一步动作"
\"\"\" 
            """

# Replacement 4: generate_narrative prompt
start_marker_4 = 'prompt = f"""浣犳槸涓浣嶇邯褰曠墖瀵兼紨'
if start_marker_4 not in content:
    # Try looking for surrounding code
    start_marker_4 = 'prompt = f"""'
    end_marker_4 = 'result_text = self._run_text_llm('
    # We must find the specific one for generate_narrative
    # Look for:
    # moments_summary.append(summary)
    # prompt = f"""...
    
    idx_start = content.find('moments_summary.append(summary)')
    if idx_start != -1:
        # Move forward to prompt = ...
        idx_prompt = content.find('prompt = f"""', idx_start)
        if idx_prompt != -1:
            start_marker_pos = idx_prompt
            # Find end marker
            end_marker_pos = content.find(end_marker_4, start_marker_pos)
            
            # Construct new content 4
            new_prompt_4 = """prompt = f\"\"\"你是纪录片导演和教育研究者。请基于以下协作学习活动中的关键时刻，创作一份团队叙事报告。

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
\"\"\"
            """

def replace_block(text, start_pattern, end_pattern, replacement):
    start_idx = text.find(start_pattern)
    if start_idx == -1:
        print(f"Start pattern not found: {start_pattern[:50]}...")
        return text
    
    # Start replacing FROM the start_pattern (if replacement includes prompt variable name) lines
    # My replacement strings create `prompt = ...` so I should replace `from start_pattern`.
    # Wait, my replacements above START with `prompt = ...`.
    # But start_pattern 1 is `image_base64 = ...` which is BEFORE prompt.
    # So I should keep start_pattern and append my replacement.
    
    # Correct logic:
    # 1. Find start_marker.
    # 2. Find end_marker AFTER start_marker.
    # 3. Content between start_marker (inclusive? no) and end_marker is what I want to replace?
    # No.
    
    # Strategy A:
    # Replacements include `prompt = ...`.
    # I want to replace everything between `start_marker` (exclusive) and `end_marker` (exclusive) with `new_prompt`.
    # But start_marker 1 does NOT include `prompt =`. It is the line BEFORE.
    # So I insert after start_marker.
    
    # But `prompt =` line IS in the file.
    # So I replace `[start_marker + len(start_marker) : end_marker]` with `new_prompt`.
    
    end_idx = text.find(end_pattern, start_idx)
    if end_idx == -1:
         print(f"End pattern not found after start: {end_pattern[:50]}...")
         return text
    
    prefix = text[:start_idx + len(start_pattern)]
    suffix = text[end_idx:]
    return prefix + replacement + suffix

# Fix 1
new_content = replace_block(content, start_marker_1, end_marker_1, new_prompt_1)

# Fix 2
new_content = replace_block(new_content, start_marker_2, end_marker_2, new_prompt_2)

# Fix 3
new_content = replace_block(new_content, start_marker_3, end_marker_3, new_prompt_3)

# Fix 4 (Special logic)
# Find the prompt in generate_narrative
idx_narrative_summary = new_content.find('moments_summary.append(summary)')
if idx_narrative_summary != -1:
    idx_prompt = new_content.find('prompt = f"""', idx_narrative_summary)
    idx_end = new_content.find('result_text = self._run_text_llm(', idx_prompt)
    if idx_prompt != -1 and idx_end != -1:
        # Replacement
        prefix = new_content[:idx_prompt]
        suffix = new_content[idx_end:]
        new_content = prefix + new_prompt_4 + suffix
    else:
        print("Could not find prompt marker for Narrative")
else:
    print("Could not find narrative summary append")

# Save
with open(file_path, "w", encoding="utf-8") as f:
    f.write(new_content)

print(f"File updated: {file_path}")
