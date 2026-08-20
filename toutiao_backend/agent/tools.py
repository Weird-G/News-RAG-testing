from datetime import datetime, date
from typing import List, Dict, Any
from sqlalchemy import select, func, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession
from models.news import News, Category


# ====================================================================
# 一、精确查询类：按新闻ID查询特定字段（浏览量、字数等结构化数字）
# RAG 向量化时未将 views 写入向量库（metadata 仅含 news_id/title/author/category_id），
# LLM 生成回答时上下文中看不到精确数字 → 必须走工具走 SQL 精确查询
# ====================================================================

async def get_news_views(db: AsyncSession, news_id: int) -> Dict[str, Any]:
    """查询指定新闻的浏览量（精确数字，RAG 拿不到）"""
    stmt = select(News.id, News.title, News.views).where(News.id == news_id)
    result = await db.execute(stmt)
    news = result.first()

    if news:
        return {
            "success": True,
            "data": {
                "news_id": news.id,
                "title": news.title,
                "views": news.views
            }
        }
    return {
        "success": False,
        "error": f"新闻ID {news_id} 不存在"
    }


async def count_news_words(db: AsyncSession, news_id: int) -> Dict[str, Any]:
    """统计新闻正文字数（精确数字，RAG 拿不到）"""
    stmt = select(News.id, News.title, News.content).where(News.id == news_id)
    result = await db.execute(stmt)
    news = result.first()

    if news:
        content_length = len(news.content) if news.content else 0
        return {
            "success": True,
            "data": {
                "news_id": news.id,
                "title": news.title,
                "word_count": content_length,
                "char_count": len(news.content) if news.content else 0
            }
        }
    return {
        "success": False,
        "error": f"新闻ID {news_id} 不存在"
    }


# ====================================================================
# 二、列表检索类：按条件返回新闻列表
# 这类查询基于结构化过滤条件（分类、日期、排序），RAG 向量检索基于语义相似度，
# 不擅长精确条件过滤（例如「今天的新闻」RAG 可能返回语义相似但发布时间老的新闻）
# ====================================================================

async def list_news_by_category(db: AsyncSession, category_name: str) -> Dict[str, Any]:
    """按分类名称返回新闻列表（按浏览量倒序，Top10）"""
    stmt = select(Category.id).where(Category.name == category_name)
    result = await db.execute(stmt)
    category = result.scalar_one_or_none()

    if not category:
        return {
            "success": False,
            "error": f"分类 '{category_name}' 不存在"
        }

    stmt = select(News.id, News.title, News.author, News.views, News.publish_time).where(
        News.category_id == category
    ).order_by(News.views.desc()).limit(10)
    result = await db.execute(stmt)
    news_list = result.fetchall()

    return {
        "success": True,
        "data": [{
            "news_id": news.id,
            "title": news.title,
            "author": news.author,
            "views": news.views,
            "publish_time": news.publish_time.strftime("%Y-%m-%d %H:%M:%S")
        } for news in news_list]
    }


async def get_news_by_date(db: AsyncSession, date_str: str, limit: int = 10) -> Dict[str, Any]:
    """
    按发布日期查询新闻（按浏览量倒序）
    date_str 格式：YYYY-MM-DD
    AI 测试价值：RAG 向量检索不擅长时间过滤，本工具体现「工具 vs RAG」边界差异
    """
    # 参数校验：日期格式合法性
    try:
        target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return {
            "success": False,
            "error": f"日期格式非法：'{date_str}'，正确格式为 YYYY-MM-DD（如 2026-07-01）"
        }

    # limit 范围约束
    if not isinstance(limit, int) or limit <= 0:
        limit = 10
    limit = min(limit, 100)

    # 使用 cast(News.publish_time, Date) 按日期过滤（忽略时分秒）
    stmt = select(News.id, News.title, News.author, News.views, News.publish_time).where(
        cast(News.publish_time, Date) == target_date
    ).order_by(News.views.desc()).limit(limit)
    result = await db.execute(stmt)
    news_list = result.fetchall()

    return {
        "success": True,
        "data": [{
            "news_id": news.id,
            "title": news.title,
            "author": news.author,
            "views": news.views,
            "publish_time": news.publish_time.strftime("%Y-%m-%d %H:%M:%S")
        } for news in news_list],
        "meta": {
            "date": date_str,
            "count": len(news_list),
            "limit": limit
        }
    }


async def get_latest_news(db: AsyncSession, limit: int = 10) -> Dict[str, Any]:
    """按发布时间倒序返回最新新闻"""
    if not isinstance(limit, int) or limit <= 0:
        limit = 10
    limit = min(limit, 100)

    stmt = select(News.id, News.title, News.author, News.views, News.publish_time, News.category_id).order_by(
        News.publish_time.desc()
    ).limit(limit)
    result = await db.execute(stmt)
    news_list = result.fetchall()

    return {
        "success": True,
        "data": [{
            "news_id": news.id,
            "title": news.title,
            "author": news.author,
            "views": news.views,
            "category_id": news.category_id,
            "publish_time": news.publish_time.strftime("%Y-%m-%d %H:%M:%S")
        } for news in news_list],
        "meta": {"count": len(news_list), "limit": limit}
    }


async def get_hot_news(db: AsyncSession, limit: int = 10) -> Dict[str, Any]:
    """按浏览量倒序返回热门新闻（聚合排序，RAG 做不了）"""
    if not isinstance(limit, int) or limit <= 0:
        limit = 10
    limit = min(limit, 100)

    stmt = select(News.id, News.title, News.author, News.views, News.publish_time).order_by(
        News.views.desc()
    ).limit(limit)
    result = await db.execute(stmt)
    news_list = result.fetchall()

    return {
        "success": True,
        "data": [{
            "news_id": news.id,
            "title": news.title,
            "author": news.author,
            "views": news.views,
            "publish_time": news.publish_time.strftime("%Y-%m-%d %H:%M:%S")
        } for news in news_list],
        "meta": {"count": len(news_list), "limit": limit}
    }


# ====================================================================
# 三、统计聚合类：聚合计算（分类计数、总量求和），RAG 完全做不了
# ====================================================================

async def get_news_statistics(db: AsyncSession) -> Dict[str, Any]:
    """按分类统计新闻数量与总浏览量（聚合查询，RAG 做不了）"""
    # 按分类聚合：news_count + total_views
    stmt = select(
        Category.id,
        Category.name,
        func.count(News.id).label("news_count"),
        func.coalesce(func.sum(News.views), 0).label("total_views")
    ).outerjoin(News, News.category_id == Category.id).group_by(Category.id, Category.name).order_by(
        func.count(News.id).desc()
    )
    result = await db.execute(stmt)
    rows = result.fetchall()

    # 全局总量
    total_stmt = select(
        func.count(News.id).label("total_news"),
        func.coalesce(func.sum(News.views), 0).label("total_views_all")
    )
    total_result = await db.execute(total_stmt)
    total_row = total_result.first()

    return {
        "success": True,
        "data": {
            "by_category": [{
                "category_id": row.id,
                "category_name": row.name,
                "news_count": row.news_count,
                "total_views": int(row.total_views)
            } for row in rows],
            "global": {
                "total_news": total_row.total_news,
                "total_views": int(total_row.total_views_all),
                "category_count": len(rows)
            }
        }
    }


# ====================================================================
# 工具配置与函数映射
# ====================================================================

TOOLS_CONFIG = [
    # 一、精确查询类
    {
        "name": "get_news_views",
        "description": "查询指定新闻的浏览量（精确数字）",
        "parameters": [
            {
                "name": "news_id",
                "type": "integer",
                "description": "新闻ID",
                "required": True
            }
        ]
    },
    {
        "name": "count_news_words",
        "description": "统计新闻正文字数（精确数字）",
        "parameters": [
            {
                "name": "news_id",
                "type": "integer",
                "description": "新闻ID",
                "required": True
            }
        ]
    },
    # 二、列表检索类
    {
        "name": "list_news_by_category",
        "description": "按分类名称返回新闻列表（按浏览量倒序Top10）",
        "parameters": [
            {
                "name": "category_name",
                "type": "string",
                "description": "分类名称（如：科技/财经/体育/娱乐）",
                "required": True
            }
        ]
    },
    {
        "name": "get_news_by_date",
        "description": "按发布日期查询新闻（按浏览量倒序）。用于「今天/某天有什么新闻」类问题",
        "parameters": [
            {
                "name": "date_str",
                "type": "string",
                "description": "日期字符串，格式 YYYY-MM-DD（如 2026-07-01）",
                "required": True
            },
            {
                "name": "limit",
                "type": "integer",
                "description": "返回条数上限，默认10，最大100",
                "required": False
            }
        ]
    },
    {
        "name": "get_latest_news",
        "description": "按发布时间倒序返回最新新闻",
        "parameters": [
            {
                "name": "limit",
                "type": "integer",
                "description": "返回条数上限，默认10，最大100",
                "required": False
            }
        ]
    },
    {
        "name": "get_hot_news",
        "description": "按浏览量倒序返回热门新闻排行",
        "parameters": [
            {
                "name": "limit",
                "type": "integer",
                "description": "返回条数上限，默认10，最大100",
                "required": False
            }
        ]
    },
    # 三、统计聚合类
    {
        "name": "get_news_statistics",
        "description": "按分类统计新闻数量与总浏览量（聚合查询，无需参数）",
        "parameters": []
    }
]

TOOL_FUNCTIONS = {
    # 精确查询类
    "get_news_views": get_news_views,
    "count_news_words": count_news_words,
    # 列表检索类
    "list_news_by_category": list_news_by_category,
    "get_news_by_date": get_news_by_date,
    "get_latest_news": get_latest_news,
    "get_hot_news": get_hot_news,
    # 统计聚合类
    "get_news_statistics": get_news_statistics
}
