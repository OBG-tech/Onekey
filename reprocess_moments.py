#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
关键瞬间AI重处理脚本

用法: python3 reprocess_moments.py [--dry-run]

步骤:
1. 读取 moments.json
2. 查找缺失 AI 描述的 moments
3. 对每个 moment 生成 AI 描述
4. 保存 moments.json
"""

import os
import sys
import json
import base64
import time
from pathlib import Path
from datetime import datetime

# 加载环境变量
try:
    from dotenv import load_dotenv
    load_dotenv('.env.local')
except ImportError:
    # 手动加载 .env.local
    env_file = Path('.env.local')
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()


# 数据目录
DATA_DIR = Path("integrated_data/key_moments")
MOMENTS_FILE = DATA_DIR / "moments.json"

# API相关
API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")

def load_moments():
    """加载 moments.json"""
    if not MOMENTS_FILE.exists():
        print(f"错误: 找不到 {MOMENTS_FILE}")
        return None
    
    with open(MOMENTS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_moments(data):
    """保存 moments.json"""
    data['last_updated'] = datetime.now().isoformat()
    with open(MOMENTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"成功保存 {MOMENTS_FILE}")

def find_missing_ai_moments(data):
    """查找缺失AI描述的moments"""
    missing = []
    for m in data.get('moments', []):
        frame_path = m.get('frame_path', '')
        ai_description = m.get('ai_description', '')
        
        # 图片存在但没有AI描述或正在处理中
        if frame_path and Path(frame_path).exists():
            if not ai_description or ai_description in ['', 'AI生成中...', '分析中...']:
                missing.append(m)
    
    return missing

def analyze_moment_with_ai(moment):
    """使用AI分析单个moment"""
    import cv2
    
    frame_path = moment.get('frame_path', '')
    if not frame_path or not Path(frame_path).exists():
        print(f"  错误: 图片不存在: {frame_path}")
        return None
    
    # 读取图片并编码为base64
    frame = cv2.imread(frame_path)
    if frame is None:
        print(f"  错误: 无法读取图片: {frame_path}")
        return None
    
    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    image_base64 = base64.b64encode(buffer).decode('utf-8')
    
    # 获取用户标注和语音转写
    user_note = moment.get('user_note', '') or ''
    transcript = moment.get('transcript', '') or ''
    
    # 构建prompt
    prompt = f"""你是一个"关键瞬间"观察记录员，正在分析设计工作坊/Hackathon现场的录制瞬间。

请根据以下图像和上下文信息，生成一个观察记录。

场景说明：这是一个创客马拉松/Hackathon现场（制作原型、写代码、调试、讨论方案）。

用户标注: {user_note or "(无)"}

相关语音转写:
{transcript or "(无语音)"}

请按以下格式输出:
标题：<10~14字，概括动作+具体活动/事件，包括人数和关键物体>
详细描述：<2~3句，描述画面内容和上下文，优先结合语音内容，限120字以内>
分析框架标签：<如"[R2]用户验证"等，如果无法推断则标"无框架标签">

请直接输出上述内容，不要包含其他解释。使用中文。
"""
    
    try:
        import dashscope
        from dashscope import MultiModalConversation
        
        dashscope.api_key = API_KEY
        
        messages = [{
            'role': 'user',
            'content': [
                {'image': f'data:image/jpeg;base64,{image_base64}'},
                {'text': prompt}
            ]
        }]
        
        response = MultiModalConversation.call(
            model=os.environ.get("VISION_MODEL", "qwen-vl-max-latest"),
            messages=messages,
            max_tokens=500
        )
        
        if response.status_code == 200:
            result_text = response.output.choices[0].message.content[0]['text']
            return parse_ai_response(result_text)
        else:
            print(f"  错误: AI分析失败: {response.code} - {response.message}")
            return None
            
    except Exception as e:
        print(f"  错误: AI分析异常: {e}")
        return None

def parse_ai_response(text):
    """解析AI响应"""
    result = {
        'ai_description': '',
        'ai_tagline': '',
        'ai_framework_tags': '',
        'analysis': text
    }
    
    lines = text.strip().split('\n')
    for line in lines:
        line = line.strip()
        if line.startswith('标题：') or line.startswith('标题:'):
            result['ai_tagline'] = line.split('：', 1)[-1].strip()
        elif line.startswith('详细描述：') or line.startswith('详细描述:'):
            result['ai_description'] = line.split('：', 1)[-1].strip()
        elif line.startswith('分析框架标签：') or line.startswith('分析框架标签:'):
            result['ai_framework_tags'] = line.split('：', 1)[-1].strip()
    
    # 如果没有提取到描述，则使用前100个字符
    if not result['ai_description']:
        result['ai_description'] = text[:100]
    
    return result

def main():
    dry_run = '--dry-run' in sys.argv
    
    print("=" * 60)
    print("关键瞬间AI重处理脚本")
    print("=" * 60)
    
    if not API_KEY:
        print("错误: DASHSCOPE_API_KEY 未设置")
        print("   请在 .env.local 文件中配置")
        sys.exit(1)
    
    # 读取 moments 数据
    data = load_moments()
    if not data:
        sys.exit(1)
    
    # 查找缺失AI描述的moments
    missing = find_missing_ai_moments(data)
    
    print(f"\n统计信息:")
    print(f"   - 总moments数: {len(data.get('moments', []))}")
    print(f"   - 缺失AI描述的moments: {len(missing)}")
    
    if not missing:
        print("\n成功: 所有moments均已包含AI描述")
        return
    
    if dry_run:
        print("\n干运行模式 - 将显示将被处理的moments:")
        for m in missing:
            print(f"   - {m['id']}: {m.get('user_note', '')[:30]}")
        return
    
    print(f"\n开始处理 {len(missing)} 个moments...\n")
    
    processed = 0
    failed = 0
    
    for i, moment in enumerate(missing, 1):
        moment_id = moment['id']
        print(f"[{i}/{len(missing)}] 处理: {moment_id}")
        
        result = analyze_moment_with_ai(moment)
        
        if result:
            # 更新moment信息
            for m in data['moments']:
                if m['id'] == moment_id:
                    m['ai_description'] = result['ai_description']
                    m['ai_tagline'] = result['ai_tagline']
                    m['ai_framework_tags'] = result['ai_framework_tags']
                    m['analysis'] = result['analysis']
                    m['llm_provider'] = os.environ.get("LLM_PROVIDER", "qwen")
                    m['llm_model'] = os.environ.get("VISION_MODEL", "qwen-vl-max-latest")
                    break
            
            processed += 1
            print(f"  成功: {result['ai_tagline'][:30]}...")
        else:
            failed += 1
            print(f"  失败")
        
        # 限制API请求频率
        if i < len(missing):
            time.sleep(1)
    
    # 保存结果
    print(f"\n正在保存结果...")
    save_moments(data)
    
    print(f"\n{'=' * 60}")
    print(f"完成!")
    print(f"   - 成功处理: {processed}")
    print(f"   - 失败: {failed}")
    print(f"{'=' * 60}")

if __name__ == "__main__":
    main()
