import os
import httpx
from datetime import datetime, timedelta
from typing import List, Dict, Any
from sqlalchemy import select, func, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession
from models.news import News, Category

DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
DASHSCOPE_ENDPOINT = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"


async def fetch_top_news_by_category(db: AsyncSession, category_name: str, limit: int = 5) -> List[Dict[str, Any]]:
    stmt = select(Category.id).where(Category.name == category_name)
    result = await db.execute(stmt)
    category = result.scalar_one_or_none()

    if not category:
        return []

    # category 已经是 int（select(Category.id) 返回标量），直接用
    stmt = select(News.id, News.title, News.content, News.author, News.views, News.publish_time).where(
        News.category_id == category
    ).order_by(News.views.desc()).limit(limit)
    result = await db.execute(stmt)
    news_list = result.fetchall()
    
    return [{
        "news_id": news.id,
        "title": news.title,
        "content": news.content,
        "author": news.author,
        "views": news.views,
        "publish_time": news.publish_time.strftime("%Y-%m-%d %H:%M:%S")
    } for news in news_list]


async def extract_keywords(news_list: List[Dict[str, Any]]) -> List[str]:
    if not news_list:
        return []
    
    if not DASHSCOPE_API_KEY:
        return []
    
    news_text = "\n".join([f"标题：{n['title']}\n内容：{n['content'][:300]}" for n in news_list])
    
    prompt = f"""请从以下新闻内容中提取5-10个最具代表性的关键词，用中文逗号分隔。

新闻内容：
{news_text}

关键词："""
    
    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "qwen3-max-preview",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False
    }
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(DASHSCOPE_ENDPOINT, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            keywords = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
            return [k.strip() for k in keywords.split("，") if k.strip()]
    except Exception:
        return []


async def generate_summary_brief(category_name: str, news_list: List[Dict[str, Any]], 
                                  keywords: List[str], total_views: int) -> str:
    if not news_list:
        return f"分类 '{category_name}' 暂无新闻数据。"
    
    if not DASHSCOPE_API_KEY:
        news_titles = "\n".join([f"- {n['title']} (浏览量: {n['views']})" for n in news_list])
        return f"{category_name}分类资讯简报\n\n热点新闻：\n{news_titles}\n\n总浏览量：{total_views}\n关键词：{', '.join(keywords)}"
    
    news_summary = "\n".join([
        f"【{news['title']}】\n作者：{news['author']}\n浏览量：{news['views']}\n发布时间：{news['publish_time']}"
        for news in news_list
    ])
    
    prompt = f"""请根据以下新闻数据生成一份专业的分类资讯汇总简报。

分类名称：{category_name}
总浏览量：{total_views}
热点关键词：{', '.join(keywords)}

新闻详情：
{news_summary}

请生成一份结构清晰、内容精炼的资讯简报，包含：
1. 分类概述
2. 热点新闻摘要
3. 数据统计
4. 关键信息总结"""
    
    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "qwen3-max-preview",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False
    }
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(DASHSCOPE_ENDPOINT, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()


async def category_summary_workflow(db: AsyncSession, category_name: str) -> Dict[str, Any]:
    workflow_steps = []
    
    step1_result = await fetch_top_news_by_category(db, category_name, limit=5)
    workflow_steps.append({
        "step": "1. 拉取分类Top5新闻",
        "status": "success" if step1_result else "failed",
        "data": step1_result
    })
    
    if not step1_result:
        return {
            "type": "workflow",
            "workflow": "category_summary",
            "category": category_name,
            "answer": f"分类 '{category_name}' 不存在或暂无新闻数据",
            "workflow_steps": workflow_steps,
            "summary": {
                "total_news": 0,
                "total_views": 0,
                "keywords": []
            }
        }
    
    total_views = sum(news["views"] for news in step1_result)
    workflow_steps.append({
        "step": "2. 统计总浏览量",
        "status": "success",
        "data": {"total_views": total_views}
    })
    
    keywords = await extract_keywords(step1_result)
    workflow_steps.append({
        "step": "3. 提取关键词",
        "status": "success" if keywords else "partial",
        "data": keywords
    })
    
    summary_brief = await generate_summary_brief(category_name, step1_result, keywords, total_views)
    workflow_steps.append({
        "step": "4. 生成汇总简报",
        "status": "success",
        "data": summary_brief
    })
    
    return {
        "type": "workflow",
        "workflow": "category_summary",
        "category": category_name,
        "answer": summary_brief,
        "workflow_steps": workflow_steps,
        "summary": {
            "total_news": len(step1_result),
            "total_views": total_views,
            "keywords": keywords,
            "news_titles": [news["title"] for news in step1_result]
        }
    }


# ====================================================================
# Workflow 2：每日新闻简报（按日期拉取 → 分类聚合 → 统计 → LLM简报）
# 触发：「今日新闻」「每天简报」「今天有什么新闻」
# AI 测试价值：多工具串联 + 时间过滤（与 get_news_by_date 呼应）
# ====================================================================

async def fetch_news_by_date(db: AsyncSession, target_date_str: str, limit: int = 20) -> List[Dict[str, Any]]:
    """按日期拉取新闻（按浏览量倒序）"""
    try:
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return []

    stmt = select(News.id, News.title, News.content, News.author, News.views, News.publish_time, News.category_id).where(
        cast(News.publish_time, Date) == target_date
    ).order_by(News.views.desc()).limit(limit)
    result = await db.execute(stmt)
    news_list = result.fetchall()

    return [{
        "news_id": news.id,
        "title": news.title,
        "content": news.content,
        "author": news.author,
        "views": news.views,
        "category_id": news.category_id,
        "publish_time": news.publish_time.strftime("%Y-%m-%d %H:%M:%S")
    } for news in news_list]


async def group_news_by_category(news_list: List[Dict[str, Any]], db: AsyncSession) -> Dict[str, Any]:
    """按分类聚合新闻，返回每类新闻数与Top3标题"""
    # 查所有分类名映射
    stmt = select(Category.id, Category.name)
    result = await db.execute(stmt)
    category_map = {row.id: row.name for row in result.fetchall()}

    grouped = {}
    for news in news_list:
        cat_id = news.get("category_id")
        cat_name = category_map.get(cat_id, f"分类{cat_id}")
        if cat_name not in grouped:
            grouped[cat_name] = {"count": 0, "news": [], "total_views": 0}
        grouped[cat_name]["count"] += 1
        grouped[cat_name]["total_views"] += news.get("views", 0)
        grouped[cat_name]["news"].append({
            "title": news["title"],
            "views": news["views"]
        })

    # 每类只取Top3标题
    for cat_name in grouped:
        grouped[cat_name]["news"] = sorted(
            grouped[cat_name]["news"], key=lambda x: x["views"], reverse=True
        )[:3]

    return grouped


async def generate_daily_brief(date_str: str, grouped_news: Dict[str, Any], total_count: int) -> str:
    if not grouped_news:
        return f"{date_str} 暂无新闻数据。"

    if not DASHSCOPE_API_KEY:
        # 兜底：纯文本格式化
        lines = [f"📅 {date_str} 每日新闻简报", f"共 {total_count} 条新闻，{len(grouped_news)} 个分类\n"]
        for cat, info in grouped_news.items():
            lines.append(f"【{cat}】{info['count']}条，总浏览量{info['total_views']}")
            for n in info["news"]:
                lines.append(f"  - {n['title']}（浏览{n['views']}）")
        return "\n".join(lines)

    summary_text = "\n".join([
        f"【{cat}】{info['count']}条，总浏览量{info['total_views']}，Top3：{', '.join(n['title'] for n in info['news'])}"
        for cat, info in grouped_news.items()
    ])

    prompt = f"""请根据以下新闻数据生成一份{date_str}的每日新闻简报。

日期：{date_str}
新闻总数：{total_count}
分类聚合：
{summary_text}

要求：
1. 一句话概述今日新闻整体情况
2. 按分类列出热点（每类1-2句话点评）
3. 数据必须严格基于上述统计，禁止编造
4. 简洁有力，总字数控制在300字以内"""

    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "qwen3-max-preview",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(DASHSCOPE_ENDPOINT, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    except Exception:
        # LLM 异常降级到纯文本
        lines = [f"📅 {date_str} 每日新闻简报", f"共 {total_count} 条新闻，{len(grouped_news)} 个分类\n"]
        for cat, info in grouped_news.items():
            lines.append(f"【{cat}】{info['count']}条，总浏览量{info['total_views']}")
        return "\n".join(lines)


async def daily_news_brief_workflow(db: AsyncSession, date_str: str = None) -> Dict[str, Any]:
    """每日新闻简报工作流：拉取日期新闻→分类聚合→统计→生成简报"""
    if not date_str:
        date_str = datetime.now().strftime("%Y-%m-%d")

    workflow_steps = []

    # 步骤1：拉取该日期新闻
    step1_result = await fetch_news_by_date(db, date_str, limit=20)
    workflow_steps.append({
        "step": "1. 按日期拉取新闻",
        "status": "success" if step1_result else "partial",
        "data": {"date": date_str, "count": len(step1_result)}
    })

    if not step1_result:
        return {
            "type": "workflow",
            "workflow": "daily_news_brief",
            "date": date_str,
            "answer": f"{date_str} 暂无新闻数据",
            "workflow_steps": workflow_steps,
            "summary": {"total_news": 0, "category_count": 0}
        }

    # 步骤2：按分类聚合
    grouped = await group_news_by_category(step1_result, db)
    workflow_steps.append({
        "step": "2. 按分类聚合",
        "status": "success",
        "data": {cat: {"count": info["count"], "total_views": info["total_views"]} for cat, info in grouped.items()}
    })

    # 步骤3：统计总量
    total_views = sum(n["views"] for n in step1_result)
    workflow_steps.append({
        "step": "3. 统计总浏览量",
        "status": "success",
        "data": {"total_views": total_views, "total_news": len(step1_result)}
    })

    # 步骤4：生成简报
    brief = await generate_daily_brief(date_str, grouped, len(step1_result))
    workflow_steps.append({
        "step": "4. 生成每日简报",
        "status": "success",
        "data": brief
    })

    return {
        "type": "workflow",
        "workflow": "daily_news_brief",
        "date": date_str,
        "answer": brief,
        "workflow_steps": workflow_steps,
        "summary": {
            "total_news": len(step1_result),
            "total_views": total_views,
            "category_count": len(grouped),
            "categories": list(grouped.keys())
        }
    }


# ====================================================================
# Workflow 3：热点新闻排行（拉取热门 → 排序 → 关键词 → LLM点评）
# 触发：「热点新闻」「热门排行」「今天什么最火」
# AI 测试价值：聚合查询 + LLM分析
# ====================================================================

async def fetch_hot_news(db: AsyncSession, limit: int = 10) -> List[Dict[str, Any]]:
    """按浏览量倒序拉取热门新闻"""
    stmt = select(News.id, News.title, News.content, News.author, News.views, News.publish_time).order_by(
        News.views.desc()
    ).limit(limit)
    result = await db.execute(stmt)
    news_list = result.fetchall()

    return [{
        "news_id": news.id,
        "title": news.title,
        "content": news.content,
        "author": news.author,
        "views": news.views,
        "publish_time": news.publish_time.strftime("%Y-%m-%d %H:%M:%S")
    } for news in news_list]


async def generate_hot_ranking_brief(news_list: List[Dict[str, Any]], keywords: List[str]) -> str:
    if not news_list:
        return "暂无热门新闻数据。"

    if not DASHSCOPE_API_KEY:
        lines = ["🔥 热点新闻排行榜"]
        for i, n in enumerate(news_list, 1):
            lines.append(f"{i}. {n['title']}（浏览{n['views']}）")
        if keywords:
            lines.append(f"\n关键词：{', '.join(keywords)}")
        return "\n".join(lines)

    ranking_text = "\n".join([
        f"{i+1}. 《{n['title']}》浏览量{n['views']} - {n['content'][:100]}"
        for i, n in enumerate(news_list)
    ])

    prompt = f"""请根据以下热门新闻排行数据生成一份热点点评。

热点排行：
{ranking_text}

热点关键词：{', '.join(keywords) if keywords else '无'}

要求：
1. 总结今日热点趋势（1-2句）
2. 点评Top3热点新闻（每条1句）
3. 数据严格基于上述，禁止编造浏览量数字
4. 总字数控制在300字以内"""

    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "qwen3-max-preview",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(DASHSCOPE_ENDPOINT, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    except Exception:
        lines = ["🔥 热点新闻排行榜"]
        for i, n in enumerate(news_list, 1):
            lines.append(f"{i}. {n['title']}（浏览{n['views']}）")
        return "\n".join(lines)


async def hot_news_ranking_workflow(db: AsyncSession, limit: int = 10) -> Dict[str, Any]:
    """热点新闻排行工作流：拉取热门→排序→关键词→生成点评"""
    workflow_steps = []

    # 步骤1：拉取热门Top10
    step1_result = await fetch_hot_news(db, limit=limit)
    workflow_steps.append({
        "step": "1. 拉取热门新闻Top10",
        "status": "success" if step1_result else "failed",
        "data": {"count": len(step1_result), "limit": limit}
    })

    if not step1_result:
        return {
            "type": "workflow",
            "workflow": "hot_news_ranking",
            "answer": "暂无热门新闻数据",
            "workflow_steps": workflow_steps,
            "summary": {"total_news": 0}
        }

    # 步骤2：统计总浏览量
    total_views = sum(n["views"] for n in step1_result)
    avg_views = total_views // len(step1_result) if step1_result else 0
    workflow_steps.append({
        "step": "2. 统计浏览量",
        "status": "success",
        "data": {"total_views": total_views, "avg_views": avg_views}
    })

    # 步骤3：提取关键词（复用现有 extract_keywords）
    keywords = await extract_keywords(step1_result)
    workflow_steps.append({
        "step": "3. 提取关键词",
        "status": "success" if keywords else "partial",
        "data": keywords
    })

    # 步骤4：生成热点点评
    brief = await generate_hot_ranking_brief(step1_result, keywords)
    workflow_steps.append({
        "step": "4. 生成热点点评",
        "status": "success",
        "data": brief
    })

    return {
        "type": "workflow",
        "workflow": "hot_news_ranking",
        "answer": brief,
        "workflow_steps": workflow_steps,
        "summary": {
            "total_news": len(step1_result),
            "total_views": total_views,
            "avg_views": avg_views,
            "keywords": keywords,
            "top_news_titles": [n["title"] for n in step1_result[:3]]
        }
    }


WORKFLOW_CONFIG = [
    {
        "name": "category_summary",
        "description": "分类资讯汇总工作流：拉取分类Top5新闻、提取关键词、统计总浏览量、生成汇总简报",
        "trigger_patterns": [
            "汇总.*分类",
            "资讯简报",
            "分类.*新闻",
            "总结.*新闻"
        ],
        "required_params": ["category_name"]
    },
    {
        "name": "daily_news_brief",
        "description": "每日新闻简报工作流：按日期拉取新闻、分类聚合、统计浏览量、生成每日简报",
        "trigger_patterns": [
            "今日.*新闻",
            "今天.*新闻",
            "每天.*简报",
            "每日.*简报",
            "今天.*有什么.*新闻"
        ],
        "required_params": []
    },
    {
        "name": "hot_news_ranking",
        "description": "热点新闻排行工作流：拉取热门Top10、统计浏览量、提取关键词、生成热点点评",
        "trigger_patterns": [
            "热点.*新闻",
            "热门.*排行",
            "今天.*什么.*最火",
            "人气.*新闻",
            "最火.*新闻"
        ],
        "required_params": []
    }
]

WORKFLOW_FUNCTIONS = {
    "category_summary": category_summary_workflow,
    "daily_news_brief": daily_news_brief_workflow,
    "hot_news_ranking": hot_news_ranking_workflow
}