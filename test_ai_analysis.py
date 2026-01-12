#!/usr/bin/env python3
"""
AI分析调试工具 - 测试关键时刻的AI分析功能
"""

import os
import sys
import json

# 设置环境变量（如果未设置）
if not os.environ.get('DASHSCOPE_API_KEY'):
    print("⚠️ 警告: DASHSCOPE_API_KEY 未设置")
    print("请设置: export DASHSCOPE_API_KEY=your_api_key")

# 添加当前目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_llm_connection():
    """测试LLM连接"""
    print("\n" + "="*60)
    print("🔍 测试 LLM 连接")
    print("="*60)
    
    # 检查环境变量
    api_key = os.environ.get('DASHSCOPE_API_KEY')
    if not api_key:
        print("❌ DASHSCOPE_API_KEY 未设置")
        return False
    
    print(f"✅ API Key: {api_key[:10]}...{api_key[-4:]}")
    
    # 尝试简单的文本LLM调用
    try:
        from openai import OpenAI
        
        client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        
        print("   测试简单的文本生成...")
        response = client.chat.completions.create(
            model="qwen-max",
            messages=[{"role": "user", "content": "你好，请用一句话介绍自己"}],
            max_tokens=50
        )
        
        result = response.choices[0].message.content
        print(f"   ✅ LLM 响应: {result[:100]}")
        return True
        
    except Exception as e:
        print(f"   ❌ LLM 连接失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_vision_llm():
    """测试视觉LLM"""
    print("\n" + "="*60)
    print("🔍 测试视觉 LLM")
    print("="*60)
    
    api_key = os.environ.get('DASHSCOPE_API_KEY')
    if not api_key:
        print("❌ DASHSCOPE_API_KEY 未设置")
        return False
    
    try:
        from openai import OpenAI
        import base64
        import numpy as np
        import cv2
        
        # 创建一个测试图像
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(img, "Test Image", (50, 240), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 3)
        
        # 编码为base64
        _, buffer = cv2.imencode('.jpg', img)
        image_base64 = base64.b64encode(buffer).decode('utf-8')
        
        print(f"   测试图像大小: {len(image_base64)} 字符")
        
        client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
        
        print("   测试视觉模型...")
        response = client.chat.completions.create(
            model="qwen-vl-max-latest",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
                    {"type": "text", "text": "请用中文简单描述这个图像"}
                ]
            }],
            max_tokens=100
        )
        
        result = response.choices[0].message.content
        print(f"   ✅ 视觉LLM 响应: {result[:100]}")
        return True
        
    except Exception as e:
        print(f"   ❌ 视觉LLM 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_ai_summary_extraction():
    """测试摘要提取逻辑"""
    print("\n" + "="*60)
    print("🔍 测试摘要提取逻辑")
    print("="*60)
    
    # 测试用例
    test_cases = [
        # 标准格式
        """标签: 团队讨论技术方案
卡片摘要: 机器狗终于跑起来了！凌晨4:30的突破时刻🤖⚡️
详细描述: 团队成员围绕机器人调试问题进行激烈讨论。""",
        
        # 英文格式
        """Label: Technical Discussion
Card Summary: Robot dog finally running! 4:30 AM breakthrough moment🤖⚡️
Detailed Description: Team members intensely discussing robot debugging.""",
        
        # 混合格式
        """标签: 代码调试
Card Summary: 找到bug了！经过3小时的排查终于定位问题🐛🎯
详细描述: 开发人员在屏幕前仔细检查代码。""",
        
        # 无明确标记但包含表情符号
        """这是一个关键时刻
团队成员正在激烈讨论方案，桌上摆满了原型🎯🔥
画面中有3个人围在一起""",
    ]
    
    from key_moments_manager import KeyMomentsManager
    
    for i, test_text in enumerate(test_cases, 1):
        print(f"\n   测试用例 {i}:")
        print(f"   输入: {test_text[:80]}...")
        
        card_summary = KeyMomentsManager._extract_card_summary(test_text)
        tagline, body = KeyMomentsManager._extract_tagline(test_text)
        detail_desc = KeyMomentsManager._extract_detail_description(body)
        
        print(f"   卡片摘要: {card_summary if card_summary else '(未提取到)'}")
        print(f"   标签: {tagline if tagline else '(未提取到)'}")
        print(f"   详细描述: {detail_desc[:50] if detail_desc else '(未提取到)'}...")

def test_moment_analysis():
    """测试完整的关键时刻分析流程"""
    print("\n" + "="*60)
    print("🔍 测试完整分析流程")
    print("="*60)
    
    try:
        import cv2
        import numpy as np
        from key_moments_manager import KeyMomentsManager
        
        # 创建管理器实例
        manager = KeyMomentsManager(
            moments_dir="integrated_data/key_moments",
            audio_manager=None
        )
        
        if not manager.qwen_available:
            print("❌ Qwen 不可用，无法测试完整流程")
            return False
        
        print(f"✅ KeyMomentsManager 初始化成功")
        print(f"   LLM 提供商: {manager.llm_provider}")
        print(f"   视觉模型: {manager.vision_model}")
        print(f"   文本模型: {manager.text_model}")
        
        # 创建测试图像
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(frame, "Test Moment", (50, 240), cv2.FONT_HERSHEY_SIMPLEX, 2, (255, 255, 255), 3)
        
        # 测试分析
        print("\n   开始AI分析测试...")
        print("   (这可能需要10-30秒...)")
        
        # 注意：这需要实际调用API，可能产生费用
        # result = manager.analyze_with_multimodal(
        #     frame=frame,
        #     frame_number=100,
        #     transcript_text="测试转写文本：团队正在讨论技术方案",
        #     person_count=3
        # )
        
        print("   ⚠️ 实际API调用已跳过（避免产生费用）")
        print("   如需完整测试，请取消上面代码的注释")
        
        return True
        
    except Exception as e:
        print(f"   ❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("\n" + "="*60)
    print("🔧 AI分析调试工具")
    print("="*60)
    
    results = {}
    
    # 测试1: LLM连接
    results['llm_connection'] = test_llm_connection()
    
    # 测试2: 视觉LLM
    results['vision_llm'] = test_vision_llm()
    
    # 测试3: 摘要提取
    test_ai_summary_extraction()
    
    # 测试4: 完整流程（可选）
    if '--full' in sys.argv:
        results['full_analysis'] = test_moment_analysis()
    
    # 总结
    print("\n" + "="*60)
    print("📊 测试总结")
    print("="*60)
    
    for test_name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        print(f"   {test_name}: {status}")
    
    print("\n💡 提示:")
    print("   - 如果LLM连接失败，请检查 DASHSCOPE_API_KEY")
    print("   - 如果视觉LLM失败，可能是网络问题或API配额")
    print("   - 使用 --full 参数运行完整测试（会产生API费用）")
    print("\n✅ 诊断完成\n")

if __name__ == '__main__':
    main()
