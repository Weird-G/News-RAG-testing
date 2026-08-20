from typing import Optional

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from cache.news_cache import get_cached_categories, set_cache_categories, get_cache_news_list, set_cache_news_list, \
    get_cached_news_detail, cache_news_detail, get_cached_related_news, cache_related_news, get_cache_news_count, set_cache_news_count
from models.news import Category, News
from schemas.base import NewsItemBase
from schemas.news import NewsDetailResponse, RelatedNewsResponse


async def get_categories(db: AsyncSession, skip: int = 0, limit: int = 100):
    # 先尝试从缓存中获取数据
    cached_categories = await get_cached_categories()
    if cached_categories:
        return cached_categories

    stmt = select(Category).offset(skip).limit(limit)
    result = await db.execute(stmt)
    categories = result.scalars().all()  # ORM

    # 写入缓存
    if categories:
        categories = jsonable_encoder(categories)
        await set_cache_categories(categories)

    # 返回数据
    return categories


async def get_news_list(db: AsyncSession, category_id: int, page: int = 1, page_size: int = 10, offset: Optional[int] = None):
    """
    获取新闻列表（带缓存）

    关键修复: 不再通过 skip//limit+1 推导 page，而是直接接收调用方传过来的 page 参数，
    避免 offset/page 换算错位导致缓存键不一致、命中率为 0 的问题。
    """
    # 1. 直接基于真实的 page 与 page_size 命中缓存
    cached_list = await get_cache_news_list(category_id, page, page_size)
    if cached_list:
        print(f"[缓存命中] 分类ID:{category_id}, 页码:{page}, 每页:{page_size}, 缓存数据条数:{len(cached_list)}")
        return [News(**item) for item in cached_list]

    # 2. 缓存未命中时计算 offset（调用方传了就直接用，没传自己算）
    if offset is None:
        offset = (page - 1) * page_size

    print(f"[缓存未命中] 分类ID:{category_id}, 页码:{page}, 每页:{page_size}, 正在查询数据库...")
    stmt = select(News).where(News.category_id == category_id).offset(offset).limit(page_size)
    result = await db.execute(stmt)
    news_list = result.scalars().all()

    if news_list:
        news_data = [NewsItemBase.model_validate(item).model_dump(mode="json", by_alias=False) for item in news_list]
        cache_result = await set_cache_news_list(category_id, page, page_size, news_data)
        print(f"[缓存写入] 分类ID:{category_id}, 页码:{page}, 每页:{page_size}, 写入结果:{cache_result}, 数据条数:{len(news_data)}")

    return news_list


async def get_news_count(db: AsyncSession, category_id: int):
    # 查询的是指定分类下的新闻数量
    stmt = select(func.count(News.id)).where(News.category_id == category_id)
    result = await db.execute(stmt)
    return result.scalar_one()  # 只能有一个结果，否则报错


async def get_news_detail(db: AsyncSession, news_id: int):
    # 先尝试从缓存获取
    cached_news = await get_cached_news_detail(news_id)
    if cached_news:
        # 缓存数据可能包含 related_news，需要过滤掉（News 模型没有这个字段）
        # filtered_data = {k: v for k, v in cached_news.items() if k != 'related_news'}
        # return News(**filtered_data)
        return News(**cached_news)

    stmt = select(News).where(News.id == news_id)
    result = await db.execute(stmt)
    news = result.scalar_one_or_none()

    # 如果查询到数据，存入缓存（不使用别名，保持数据库字段名）
    if news:
        # 构造新闻详情数据用于缓存（包含 content 字段）
        # news_dict = {k: v for k, v in news.__dict__.items() if not k.startswith('_')}
        news_dict = NewsDetailResponse.model_validate(news).model_dump(
            by_alias=False, mode="json", exclude={'related_news'}
        )
        await cache_news_detail(news_id, news_dict)

    return news


async def increase_news_views(db: AsyncSession, news_id: int):
    stmt = update(News).where(News.id == news_id).values(views=News.views + 1)
    result = await db.execute(stmt)
    await db.commit()

    # 更新 → 检查数据库是否真的命中了数据 → 命中了返回True
    return result.rowcount > 0


async def get_related_news(db: AsyncSession, news_id: int, category_id: int, limit: int = 5):
    cached_related = await get_cached_related_news(news_id, category_id)
    if cached_related:
        # 缓存数据是字典列表，直接返回
        return cached_related
    # order_by 排序 → 浏览量和发布时间
    stmt = select(News).where(
        News.category_id == category_id,
        News.id != news_id
    ).order_by(
        News.views.desc(),  # 默认是升序，desc 表示降序
        News.publish_time.desc()
    ).limit(limit)
    result = await db.execute(stmt)
    # return result.scalars().all()
    related_news = result.scalars().all()

    # 转换为字典格式用于缓存和返回（不使用别名，保持数据库字段名）
    if related_news:
        related_data = [
            RelatedNewsResponse.model_validate(news).model_dump(by_alias=False, mode="json")
            for news in related_news
        ]
        await cache_related_news(news_id, category_id, related_data)
        return related_data

    # 没有相关新闻，返回空列表
    return []
    # 列表推导式 推导出新闻的核心数据，然后再 return
    # return [{
    #     "id": news_detail.id,
    #     "title": news_detail.title,
    #     "content": news_detail.content,
    #     "image": news_detail.image,
    #     "author": news_detail.author,
    #     "publishTime": news_detail.publish_time,
    #     "categoryId": news_detail.category_id,
    #     "views": news_detail.views
    # } for news_detail in related_news]
