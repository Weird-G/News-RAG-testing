import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy.ext.asyncio import AsyncSession
from config.db_conf import AsyncSessionLocal
from agent.workflows import (
    fetch_top_news_by_category,
    extract_keywords,
    generate_summary_brief,
    category_summary_workflow,
    WORKFLOW_CONFIG,
    WORKFLOW_FUNCTIONS
)


async def test_fetch_top_news_by_category():
    async with AsyncSessionLocal() as session:
        print("=" * 60)
        print("测试: fetch_top_news_by_category")
        print("=" * 60)
        
        print("\n[测试1] 拉取科技分类Top5新闻")
        result = await fetch_top_news_by_category(session, "科技", limit=5)
        print(f"获取到 {len(result)} 条新闻")
        for news in result:
            print(f"  - {news['title']} (浏览量: {news['views']})")
        
        print("\n[测试2] 拉取不存在的分类")
        result = await fetch_top_news_by_category(session, "不存在的分类")
        print(f"结果: {result}")
        assert len(result) == 0
        
        print("\n[测试3] 拉取空分类")
        result = await fetch_top_news_by_category(session, "")
        print(f"结果: {result}")
        assert len(result) == 0


async def test_extract_keywords():
    print("\n" + "=" * 60)
    print("测试: extract_keywords")
    print("=" * 60)
    
    test_news = [
        {
            "title": "人工智能技术突破：GPT-5发布",
            "content": "GPT-5是最新一代的人工智能语言模型，具有更强的理解能力和生成能力。"
        },
        {
            "title": "新能源汽车销量创新高",
            "content": "今年新能源汽车销量同比增长超过50%，市场占有率持续提升。"
        }
    ]
    
    print("\n[测试1] 提取关键词")
    keywords = await extract_keywords(test_news)
    print(f"提取的关键词: {keywords}")
    
    print("\n[测试2] 空新闻列表")
    keywords = await extract_keywords([])
    print(f"结果: {keywords}")
    assert len(keywords) == 0


async def test_generate_summary_brief():
    print("\n" + "=" * 60)
    print("测试: generate_summary_brief")
    print("=" * 60)
    
    test_news = [
        {
            "title": "人工智能技术突破",
            "content": "最新AI技术取得重大进展。",
            "author": "科技日报",
            "views": 12345,
            "publish_time": "2024-01-15 10:30:00"
        },
        {
            "title": "5G商用加速推进",
            "content": "5G网络覆盖范围不断扩大。",
            "author": "通信世界",
            "views": 8765,
            "publish_time": "2024-01-14 14:20:00"
        }
    ]
    
    print("\n[测试1] 生成汇总简报")
    brief = await generate_summary_brief("科技", test_news, ["AI", "5G", "人工智能"], 21110)
    print(f"简报内容:\n{brief}")
    
    print("\n[测试2] 空新闻列表")
    brief = await generate_summary_brief("科技", [], [], 0)
    print(f"结果: {brief}")


async def test_category_summary_workflow():
    async with AsyncSessionLocal() as session:
        print("\n" + "=" * 60)
        print("测试: category_summary_workflow")
        print("=" * 60)
        
        print("\n[测试1] 完整工作流 - 科技分类")
        result = await category_summary_workflow(session, "科技")
        print(f"\n工作流类型: {result.get('type')}")
        print(f"分类: {result.get('category')}")
        print(f"步骤数: {len(result.get('workflow_steps', []))}")
        
        print("\n工作流执行步骤:")
        for step in result.get("workflow_steps", []):
            print(f"  [{step['status']}] {step['step']}")
        
        print(f"\n总结数据:")
        summary = result.get("summary", {})
        print(f"  新闻总数: {summary.get('total_news')}")
        print(f"  总浏览量: {summary.get('total_views')}")
        print(f"  关键词: {summary.get('keywords', [])}")
        print(f"  新闻标题: {summary.get('news_titles', [])}")
        
        print("\n[测试2] 工作流 - 不存在的分类")
        result = await category_summary_workflow(session, "不存在的分类")
        print(f"\n结果: {result}")
        assert result["answer"] is not None


async def test_workflow_config():
    print("\n" + "=" * 60)
    print("测试: 工作流配置完整性")
    print("=" * 60)
    
    print("\n[测试1] 工作流配置与函数映射一致性")
    config_names = {wf["name"] for wf in WORKFLOW_CONFIG}
    function_names = set(WORKFLOW_FUNCTIONS.keys())
    
    print(f"配置中的工作流: {config_names}")
    print(f"函数映射中的工作流: {function_names}")
    
    missing_in_function = config_names - function_names
    missing_in_config = function_names - config_names
    
    if missing_in_function:
        print(f"警告: 配置中存在但函数映射中缺失的工作流: {missing_in_function}")
    else:
        print("✓ 配置与函数映射完全一致")
    
    print("\n[测试2] 工作流触发模式")
    for wf in WORKFLOW_CONFIG:
        print(f"\n工作流: {wf['name']}")
        print(f"  描述: {wf['description']}")
        print(f"  触发模式: {wf.get('trigger_patterns', [])}")
        print(f"  必填参数: {wf.get('required_params', [])}")


async def test_workflow_step_order():
    async with AsyncSessionLocal() as session:
        print("\n" + "=" * 60)
        print("测试: 工作流步骤顺序验证")
        print("=" * 60)
        
        result = await category_summary_workflow(session, "科技")
        steps = result.get("workflow_steps", [])
        
        expected_order = [
            "1. 拉取分类Top5新闻",
            "2. 统计总浏览量",
            "3. 提取关键词",
            "4. 生成汇总简报"
        ]
        
        actual_order = [step["step"] for step in steps]
        
        print(f"\n期望步骤顺序: {expected_order}")
        print(f"实际步骤顺序: {actual_order}")
        
        if actual_order == expected_order:
            print("✓ 步骤顺序正确")
        else:
            print("✗ 步骤顺序不一致")


async def test_data_flow():
    async with AsyncSessionLocal() as session:
        print("\n" + "=" * 60)
        print("测试: 数据流转验证")
        print("=" * 60)
        
        result = await category_summary_workflow(session, "科技")
        
        print("\n[验证] 新闻数据流转")
        news_list = None
        for step in result.get("workflow_steps", []):
            if "拉取分类Top5新闻" in step["step"]:
                news_list = step.get("data", [])
                print(f"  步骤1获取新闻数: {len(news_list)}")
        
        if news_list:
            total_views = sum(n["views"] for n in news_list)
            summary_views = result.get("summary", {}).get("total_views", 0)
            print(f"  计算总浏览量: {total_views}")
            print(f"  汇总总浏览量: {summary_views}")
            
            if total_views == summary_views:
                print("  ✓ 浏览量数据流转正确")
            else:
                print("  ✗ 浏览量数据流转不一致")


if __name__ == "__main__":
    print("\n" + "#" * 60)
    print("# 工作流编排测试脚本")
    print("#" * 60)
    
    asyncio.run(test_fetch_top_news_by_category())
    asyncio.run(test_extract_keywords())
    asyncio.run(test_generate_summary_brief())
    asyncio.run(test_category_summary_workflow())
    asyncio.run(test_workflow_config())
    asyncio.run(test_workflow_step_order())
    asyncio.run(test_data_flow())
    
    print("\n" + "#" * 60)
    print("# 测试完成")
    print("#" * 60)