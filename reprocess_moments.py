#!/usr/bin/env python3
"""
重新处理缺失AI分析的关键时刻

用法: python3 reprocess_moments.py [--dry-run]

功能:
1. 读取 moments.json
2. 找出有图片但缺少 AI 分析的 moments
3. 对每个 moment 调用 AI 分析
4. 更新 moments.json
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

# API配置
API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")

def load_moments():
    """加载 moments.json"""
    if not MOMENTS_FILE.exists():
        print(f"❌ 未找到 {MOMENTS_FILE}")
        return None
    
    with open(MOMENTS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def save_moments(data):
    """保存 moments.json"""
    data['last_updated'] = datetime.now().isoformat()
    with open(MOMENTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ 已保存 {MOMENTS_FILE}")

def find_missing_ai_moments(data):
    """找出缺少AI分析的moments"""
    missing = []
    for m in data.get('moments', []):
        frame_path = m.get('frame_path', '')
        ai_description = m.get('ai_description', '')
        
        # 有图片但没有AI描述，或者AI描述是占位符
        if frame_path and Path(frame_path).exists():
            if not ai_description or ai_description in ['', 'AI处理中…', '处理中...']:
                missing.append(m)
    
    return missing

def analyze_moment_with_ai(moment):
    """使用AI分析单个moment"""
    import cv2
    
    frame_path = moment.get('frame_path', '')
    if not frame_path or not Path(frame_path).exists():
        print(f"  ⚠️ 图片不存在: {frame_path}")
        return None
    
    # 读取图片并编码为base64
    frame = cv2.imread(frame_path)
    if frame is None:
        print(f"  ⚠️ 无法读取图片: {frame_path}")
        return None
    
    _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    image_base64 = base64.b64encode(buffer).decode('utf-8')
    
    # 获取已有信息
    user_note = moment.get('user_note', '') or ''
    transcript = moment.get('transcript', '') or ''
    
    # 构建prompt
    prompt = f"""你是一面"智能镜子"，客观记录创客马拉松/Hackathon现场发生的事情。

场景说明：这是创客马拉松 / Hackathon 现场（做原型、写代码、调试、讨论方案）。

核心原则 - 镜子观察法：
1) 忠实反映：像镜子一样客观描述画面中看到的内容
2) 具体可见：描述具体的动作、人物、物品
3) 无法确定就明说

【按键原因/备注】{user_note or "(无)"}

【ASR文本】
{transcript or "(无语音)"}

输出格式：
标签：<10~14字，包含人数+具体动作/事件+0-1个表情符号>
详细描述：<2~3句，描述画面内容和语音内容，总字数≤120>
分析框架标签：<如"[R2]论证推理"等，若无明显框架行为写"无框架标签">
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
            print(f"  ⚠️ AI调用失败: {response.code} - {response.message}")
            return None
            
    except Exception as e:
        print(f"  ⚠️ AI分析异常: {e}")
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
        if line.startswith('标签：') or line.startswith('标签:'):
            result['ai_tagline'] = line.split('：', 1)[-1].split(':', 1)[-1].strip()
        elif line.startswith('详细描述：') or line.startswith('详细描述:'):
            result['ai_description'] = line.split('：', 1)[-1].split(':', 1)[-1].strip()
        elif line.startswith('分析框架标签：') or line.startswith('分析框架标签:'):
            result['ai_framework_tags'] = line.split('：', 1)[-1].split(':', 1)[-1].strip()
    
    # 如果没有提取到详细描述，使用完整文本
    if not result['ai_description']:
        result['ai_description'] = text[:100]
    
    return result

def main():
    dry_run = '--dry-run' in sys.argv
    
    print("=" * 60)
    print("🔄 重新处理缺失AI分析的关键时刻")
    print("=" * 60)
    
    if not API_KEY:
        print("❌ DASHSCOPE_API_KEY 未设置")
        print("   请在 .env.local 中配置")
        sys.exit(1)
    
    # 加载数据
    data = load_moments()
    if not data:
        sys.exit(1)
    
    # 找出缺少AI分析的moments
    missing = find_missing_ai_moments(data)
    
    print(f"\n📊 统计:")
    print(f"   - 总moments数: {len(data.get('moments', []))}")
    print(f"   - 缺少AI分析: {len(missing)}")
    
    if not missing:
        print("\n✅ 没有需要重新处理的moments")
        return
    
    if dry_run:
        print("\n🔍 Dry-run 模式 - 只显示需要处理的moments:")
        for m in missing:
            print(f"   - {m['id']}: {m.get('user_note', '')[:30]}")
        return
    
    print(f"\n🚀 开始处理 {len(missing)} 个moments...\n")
    
    processed = 0
    failed = 0
    
    for i, moment in enumerate(missing, 1):
        moment_id = moment['id']
        print(f"[{i}/{len(missing)}] 处理: {moment_id}")
        
        result = analyze_moment_with_ai(moment)
        
        if result:
            # 更新moment
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
            print(f"  ✅ 成功: {result['ai_tagline'][:30]}...")
        else:
            failed += 1
            print(f"  ❌ 失败")
        
        # 避免API限流
        if i < len(missing):
            time.sleep(1)
    
    # 保存结果
    print(f"\n📦 保存结果...")
    save_moments(data)
    
    print(f"\n{'=' * 60}")
    print(f"✅ 完成!")
    print(f"   - 成功处理: {processed}")
    print(f"   - 失败: {failed}")
    print(f"{'=' * 60}")

if __name__ == "__main__":
    main()
