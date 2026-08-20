import asyncio
import logging
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from models.news import News, Category
from models.users import User
from models.favorite import Favorite
from models.history import History
from vector_store.chroma_store import get_collection_count, get_collection
from config.cache_conf import redis_client, check_redis_connection, get_json_cache
from rag.rag_service import sync_news_to_vector_db
from config.db_conf import AsyncSessionLocal

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

CHROMA_COLLECTION = "news_embeddings"
# 对账抽样规模：MySQL×Chroma 抽样新闻数 / MySQL×Redis 抽样用户数
CONTENT_SAMPLE_SIZE = 5
FAV_USER_SAMPLE_SIZE = 5


async def check_mysql_data(db: AsyncSession):
    """查询MySQL四表数据"""
    result = await db.execute(select(func.count(News.id)))
    news_count = result.scalar_one()

    result = await db.execute(select(func.count(Category.id)))
    category_count = result.scalar_one()

    result = await db.execute(select(func.count(User.id)))
    user_count = result.scalar_one()

    result = await db.execute(select(func.count(Favorite.id)))
    favorite_count = result.scalar_one()

    result = await db.execute(select(func.count(History.id)))
    history_count = result.scalar_one()

    return {
        "news": news_count,
        "category": category_count,
        "user": user_count,
        "favorite": favorite_count,
        "history": history_count
    }


async def check_chroma_data(collection_name: str = CHROMA_COLLECTION):
    """查询Chroma向量库数据"""
    try:
        count = get_collection_count(collection_name)
        collection = get_collection(collection_name)
        if collection:
            all_items = collection.get(include=["metadatas"])
            metadatas = all_items.get("metadatas", [])
            unique_news_ids = len(set(m.get("news_id") for m in metadatas if m))
        else:
            unique_news_ids = 0
        return {"total_chunks": count, "unique_news_ids": unique_news_ids}
    except Exception as e:
        logger.error(f"查询Chroma失败: {e}")
        return {"total_chunks": 0, "unique_news_ids": 0}


async def check_redis_status():
    """查询Redis连接状态与收藏列表缓存键数量"""
    info = {"available": False, "fav_cache_keys": 0}
    if not await check_redis_connection():
        info["error"] = "Redis 不可用，跳过 MySQL×Redis 对账"
        return info
    info["available"] = True
    try:
        cnt = 0
        async for _ in redis_client.scan_iter(match="favorite:list:*", count=200):
            cnt += 1
        info["fav_cache_keys"] = cnt
    except Exception as e:
        info["error"] = f"扫描收藏缓存键失败: {e}"
    return info


async def check_mysql_chroma_content_sample(db: AsyncSession, sample_size: int = CONTENT_SAMPLE_SIZE):
    """MySQL×Chroma 内容抽样对账：随机抽取 N 条新闻，逐条核对向量库是否存在其切片。

    数量级对账只能发现「整体缺失」，内容抽样能定位「单条新闻漏同步」——
    例如某条新闻内容为空导致切片数为 0、或同步中途失败漏掉个别新闻。
    """
    # 随机抽样（RAND() 适合中小数据量）
    stmt = select(News.id, News.title).order_by(func.rand()).limit(sample_size)
    result = await db.execute(stmt)
    sampled = result.all()

    collection = get_collection(CHROMA_COLLECTION)
    sample_result = []
    missing_ids = []
    for news_id, title in sampled:
        if collection is None:
            chunk_count = 0
        else:
            try:
                items = collection.get(where={"news_id": news_id}, include=["metadatas"])
                chunk_count = len(items.get("ids", []))
            except Exception:
                chunk_count = 0
        sample_result.append({"news_id": news_id, "title": title, "chunk_count": chunk_count})
        if chunk_count == 0:
            missing_ids.append(news_id)
    return {"sampled": len(sampled), "missing": missing_ids, "details": sample_result}


async def check_mysql_redis_favorites_consistency(db: AsyncSession, sample_size: int = FAV_USER_SAMPLE_SIZE):
    """MySQL×Redis 收藏列表缓存时效对账：抽样有收藏记录的用户，
    比对其 Redis 缓存的 total 与 MySQL 实际收藏数。

    缓存冷启动（key 不存在）不算异常；命中但 total 不一致 = 缓存过期/写入即失效失败。
    这正是「双存储一致性」里缓存层数据漂移的探测点。
    """
    # 抽样有收藏记录的用户ID
    stmt = (select(Favorite.user_id)
            .group_by(Favorite.user_id)
            .order_by(func.rand())
            .limit(sample_size))
    result = await db.execute(stmt)
    sampled_users = result.scalars().all()

    if not sampled_users:
        return {"sampled": 0, "stale": [], "note": "暂无收藏用户，跳过对账"}

    stale = []
    details = []
    for uid in sampled_users:
        # MySQL 真值
        cnt_stmt = select(func.count()).select_from(Favorite).where(Favorite.user_id == uid)
        mysql_total = (await db.execute(cnt_stmt)).scalar_one()
        # Redis 缓存值（取首页缓存）
        cached = await get_json_cache(f"favorite:list:{uid}:1:10")
        if cached is None:
            details.append({"user_id": uid, "mysql_total": mysql_total, "cache": "COLD", "consistent": True})
            continue
        cached_total = cached.get("total")
        consistent = (cached_total == mysql_total)
        details.append({"user_id": uid, "mysql_total": mysql_total,
                        "cached_total": cached_total, "cache": "HIT", "consistent": consistent})
        if not consistent:
            stale.append({"user_id": uid, "mysql_total": mysql_total, "cached_total": cached_total})
    return {"sampled": len(sampled_users), "stale": stale, "details": details}


async def find_data_inconsistencies(db: AsyncSession):
    """定位数据同步隐患"""
    issues = []

    mysql_data = await check_mysql_data(db)
    chroma_data = await check_chroma_data()
    redis_status = await check_redis_status()
    content_sample = await check_mysql_chroma_content_sample(db)
    fav_consistency = await check_mysql_redis_favorites_consistency(db)

    logger.info("\n" + "=" * 60)
    logger.info("MySQL四表数据统计:")
    logger.info(f"  新闻表(news): {mysql_data['news']} 条")
    logger.info(f"  分类表(category): {mysql_data['category']} 条")
    logger.info(f"  用户表(user): {mysql_data['user']} 条")
    logger.info(f"  收藏表(favorite): {mysql_data['favorite']} 条")
    logger.info(f"  历史表(history): {mysql_data['history']} 条")

    logger.info("\nChroma向量库数据统计:")
    logger.info(f"  向量片段总数: {chroma_data['total_chunks']}")
    logger.info(f"  关联新闻ID数: {chroma_data['unique_news_ids']}")

    logger.info("\nMySQL×Chroma 内容抽样对账:")
    logger.info(f"  抽样新闻数: {content_sample['sampled']}")
    if content_sample['missing']:
        logger.info(f"  漏同步新闻ID: {content_sample['missing']}")
    else:
        logger.info("  抽样新闻均在向量库中存在切片 ✓")
    for d in content_sample['details']:
        logger.info(f"  - news_id={d['news_id']} chunks={d['chunk_count']} ({d['title'][:20]}...)")

    logger.info("\nRedis 状态与收藏缓存:")
    if redis_status["available"]:
        logger.info(f"  Redis 连接: 正常")
        logger.info(f"  收藏列表缓存键数: {redis_status['fav_cache_keys']}")
    else:
        logger.warning(f"  Redis 不可用: {redis_status.get('error')}")

    logger.info("\nMySQL×Redis 收藏缓存时效对账:")
    logger.info(f"  抽样收藏用户数: {fav_consistency['sampled']}")
    if fav_consistency.get("stale"):
        logger.warning(f"  缓存与MySQL不一致用户: {fav_consistency['stale']}")
    else:
        logger.info("  命中的缓存与MySQL一致 ✓")
    for d in fav_consistency.get("details", []):
        logger.info(f"  - user_id={d['user_id']} mysql={d['mysql_total']} cache={d['cache']} "
                    f"cached={d.get('cached_total', '-')} consistent={d['consistent']}")

    # ---- 规则判定 ----
    if chroma_data["total_chunks"] == 0:
        issues.append({
            "level": "CRITICAL",
            "issue": "Chroma向量库为空",
            "reason": "向量库中没有任何数据，可能是同步脚本未执行或执行失败",
            "solution": "执行 POST /api/ai/sync_news_to_vector 接口同步数据"
        })

    if mysql_data["news"] != chroma_data["unique_news_ids"]:
        issues.append({
            "level": "HIGH",
            "issue": "新闻数量不一致",
            "reason": f"MySQL中有{mysql_data['news']}条新闻，但Chroma只关联了{chroma_data['unique_news_ids']}条新闻ID",
            "solution": "检查sync_news_to_vector_db函数，确认新闻切片逻辑和向量写入是否完整"
        })

    if content_sample["missing"]:
        issues.append({
            "level": "HIGH",
            "issue": "抽样新闻在向量库缺失切片",
            "reason": f"抽样新闻ID {content_sample['missing']} 在Chroma中无对应切片，存在单条漏同步",
            "solution": "对缺失新闻重新执行同步，检查其content是否为空"
        })

    stmt = select(News).where(News.content.is_(None) | (News.content == ""))
    result = await db.execute(stmt)
    empty_content_count = len(result.scalars().all())
    if empty_content_count > 0:
        issues.append({
            "level": "MEDIUM",
            "issue": "存在空内容新闻",
            "reason": f"MySQL中有{empty_content_count}条新闻的content字段为空，这些新闻无法被有效向量化",
            "solution": "补充新闻内容或在同步时过滤空内容新闻"
        })

    stmt = select(Category.id).distinct()
    result = await db.execute(stmt)
    category_ids = set(result.scalars().all())

    stmt = select(News.category_id).distinct()
    result = await db.execute(stmt)
    news_category_ids = set(result.scalars().all())

    orphan_categories = category_ids - news_category_ids
    if orphan_categories:
        issues.append({
            "level": "LOW",
            "issue": "存在无新闻分类",
            "reason": f"分类ID{orphan_categories}下没有任何新闻，可能是数据未填充或分类配置问题",
            "solution": "检查分类配置或补充对应分类的新闻数据"
        })

    if redis_status["available"] and fav_consistency.get("stale"):
        issues.append({
            "level": "HIGH",
            "issue": "收藏缓存与MySQL不一致（写入即失效失败）",
            "reason": f"用户 {fav_consistency['stale']} 的Redis缓存total与MySQL实际数不符，缓存已过期",
            "solution": "检查收藏写入路径是否触发 _invalidate_user_favorites_cache；必要时手动 DEL 对应 key"
        })

    return issues


async def fix_data_inconsistencies(db: AsyncSession):
    """修复数据同步隐患"""
    logger.info("\n" + "=" * 60)
    logger.info("开始修复数据同步隐患...")

    chroma_data = await check_chroma_data()
    if chroma_data["total_chunks"] == 0:
        logger.info("修复1: Chroma为空，执行全量同步")
        count = await sync_news_to_vector_db(db)
        logger.info(f"  成功同步 {count} 个新闻片段")

    logger.info("修复完成！")


async def main():
    async with AsyncSessionLocal() as db:
        logger.info("=" * 60)
        logger.info("数据一致性验证脚本启动（MySQL × Chroma × Redis 三链路对账）")
        logger.info("=" * 60)

        issues = await find_data_inconsistencies(db)

        if issues:
            logger.info("\n" + "=" * 60)
            logger.info("发现的数据同步隐患:")
            logger.info("=" * 60)
            for i, issue in enumerate(issues, 1):
                logger.info(f"\n{i}. [{issue['level']}] {issue['issue']}")
                logger.info(f"   原因: {issue['reason']}")
                logger.info(f"   解决方案: {issue['solution']}")

            fix_choice = input("\n是否自动修复这些问题？(y/n): ")
            if fix_choice.lower() == "y":
                await fix_data_inconsistencies(db)
        else:
            logger.info("\n✅ 数据一致性验证通过，未发现同步隐患")

        logger.info("\n" + "=" * 60)
        logger.info("数据一致性验证完成")
        logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
