from datetime import datetime
from sqlalchemy import select, delete, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.favorite import Favorite
from models.news import News
from config.cache_conf import get_json_cache, set_cache, redis_client, check_redis_connection

# 收藏列表缓存 key 前缀与 TTL
_FAV_CACHE_PREFIX = "favorite:list"
_FAV_CACHE_TTL = 300  # 5 分钟，兼顾新鲜度与命中率


def _fav_cache_key(user_id: int, page: int, page_size: int) -> str:
    return f"{_FAV_CACHE_PREFIX}:{user_id}:{page}:{page_size}"


async def _invalidate_user_favorites_cache(user_id: int):
    """写入即失效：用户收藏发生变更时，清除该用户所有分页缓存。

    用 SCAN（而非 KEYS）匹配前缀，避免在大库上阻塞 Redis。
    Redis 不可用时静默跳过，不影响主流程。
    """
    if not await check_redis_connection():
        return 0
    pattern = f"{_FAV_CACHE_PREFIX}:{user_id}:*"
    deleted = 0
    try:
        async for key in redis_client.scan_iter(match=pattern, count=100):
            await redis_client.delete(key)
            deleted += 1
    except Exception:
        pass
    return deleted


def _serialize_favorite_row(news, favorite_time, favorite_id) -> dict:
    """把联表查询结果行转为 JSON 安全的 dict（datetime → isoformat）。

    保持与原 `news.__dict__` 输出的字段一致（去掉 _sa_instance_state），
    便于路由层直接透传给 pydantic 响应模型。
    """
    return {
        "id": news.id,
        "title": news.title,
        "description": news.description,
        "content": news.content,
        "image": news.image,
        "author": news.author,
        "category_id": news.category_id,
        "views": news.views,
        "publish_time": news.publish_time.isoformat() if news.publish_time else None,
        "created_at": news.created_at.isoformat() if news.created_at else None,
        "updated_at": news.updated_at.isoformat() if news.updated_at else None,
        "favorite_time": favorite_time.isoformat() if isinstance(favorite_time, datetime) else favorite_time,
        "favorite_id": favorite_id,
    }


# 检查收藏状态：当前用户 是否 收藏了这一条新闻
async def is_news_favorite(
        db: AsyncSession,
        user_id: int,
        news_id: int
):
    query = select(Favorite).where(Favorite.user_id == user_id, Favorite.news_id == news_id)
    result = await db.execute(query)
    # 是否有收藏记录
    return result.scalar_one_or_none() is not None


async def add_news_favorite(
        db: AsyncSession,
        user_id: int,
        news_id: int
):
    # 先检查是否已收藏，避免唯一约束冲突
    existing = await is_news_favorite(db, user_id, news_id)
    if existing:
        # 已收藏，直接返回，不报错
        return {"id": 0, "message": "已收藏"}

    favorite = Favorite(user_id=user_id, news_id=news_id)
    db.add(favorite)
    await db.commit()
    await db.refresh(favorite)
    # 写入即失效：新增收藏后，旧分页缓存已过期
    await _invalidate_user_favorites_cache(user_id)
    return favorite


async def remove_news_favorite(
        db: AsyncSession,
        user_id: int,
        news_id: int
):
    stmt = delete(Favorite).where(Favorite.user_id == user_id, Favorite.news_id == news_id)
    result = await db.execute(stmt)
    await db.commit()
    if result.rowcount > 0:
        # 写入即失效：取消收藏后，旧分页缓存已过期
        await _invalidate_user_favorites_cache(user_id)
    return result.rowcount > 0


# 获取收藏列表：获取的是某个用户的收藏列表 + 分页功能
async def get_favorite_list(
        db: AsyncSession,
        user_id: int,
        page: int = 1,
        page_size: int = 10
):
    cache_key = _fav_cache_key(user_id, page, page_size)

    # 先查 Redis 缓存，命中则直接返回（穿透到 DB 之前）
    cached = await get_json_cache(cache_key)
    if cached is not None:
        return cached["list"], cached["total"]

    # 缓存未命中：查询 MySQL
    count_query = select(func.count()).where(Favorite.user_id == user_id)
    count_result = await db.execute(count_query)
    total = count_result.scalar_one()

    # 获取收藏列表 - 联表查询 join() + 收藏时间排序 + 分页
    # select(查询主体模型类, 字段别名).join(联合查询的模型类, 联合查询的条件).where().order_by().offset().limit()
    # 别名： Favorite.created_at.label("favorite_time")
    offset = (page - 1) * page_size
    # [
    #   (新闻对象, 收藏时间, 收藏id)
    # ]
    query = (select(News, Favorite.created_at.label("favorite_time"), Favorite.id.label("favorite_id"))
             .join(Favorite, Favorite.news_id == News.id)
             .where(Favorite.user_id == user_id)
             .order_by(Favorite.created_at.desc())
             .offset(offset).limit(page_size)
             )
    result = await db.execute(query)
    rows = result.all()

    favorite_list = [_serialize_favorite_row(news, ft, fid) for news, ft, fid in rows]

    # 回填缓存（即使为空也缓存，避免空列表反复查库；TTL 较短保证新鲜度）
    await set_cache(cache_key, {"list": favorite_list, "total": total}, expire=_FAV_CACHE_TTL)

    return favorite_list, total


# 清空收藏列表：当前用户的收藏列表
async def remove_all_favorites(
        db: AsyncSession,
        user_id: int
):
    stmt = delete(Favorite).where(Favorite.user_id == user_id)
    result = await db.execute(stmt)
    await db.commit()
    # 写入即失效：清空收藏后，所有分页缓存已过期
    await _invalidate_user_favorites_cache(user_id)

    # 返回一个删除的数量
    return result.rowcount or 0
