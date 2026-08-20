import json
import os
import logging
from typing import Any

import redis.asyncio as redis

logger = logging.getLogger(__name__)

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_DB = int(os.environ.get("REDIS_DB", "0"))
REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", None) or None

redis_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    db=REDIS_DB,
    password=REDIS_PASSWORD,
    decode_responses=True
)

redis_available = None


async def check_redis_connection():
    global redis_available
    if redis_available is None:
        try:
            await redis_client.ping()
            redis_available = True
            logger.info(f"Redis 连接成功: {REDIS_HOST}:{REDIS_PORT}")
        except Exception as e:
            redis_available = False
            logger.warning(f"Redis 连接失败: {e}，将使用数据库查询")
    return redis_available


async def get_cache(key: str):
    if not await check_redis_connection():
        return None
    try:
        return await redis_client.get(key)
    except Exception as e:
        logger.debug(f"获取缓存失败: {key}, {e}")
        return None


async def get_json_cache(key: str):
    if not await check_redis_connection():
        return None
    try:
        data = await redis_client.get(key)
        if data:
            return json.loads(data)
        return None
    except Exception as e:
        logger.debug(f"获取 JSON 缓存失败: {key}, {e}")
        return None


async def set_cache(key: str, value: Any, expire: int = 3600):
    if not await check_redis_connection():
        return False
    try:
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        await redis_client.setex(key, expire, value)
        return True
    except Exception as e:
        logger.debug(f"设置缓存失败: {key}, {e}")
        return False


async def delete_cache(key: str):
    """
    删除指定缓存 key。
    在「浏览量 +1」「新闻更新」「新闻删除」等需要主动让缓存失效的场景使用。
    """
    if not await check_redis_connection():
        return False
    try:
        deleted = await redis_client.delete(key)
        return deleted > 0
    except Exception as e:
        logger.debug(f"删除缓存失败: {key}, {e}")
        return False