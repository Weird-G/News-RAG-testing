from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from config.db_conf import get_db
from crud import news
from crud import news_cache


# 创建 APIRouter 实例
# prefix 路由前缀（API 接口规范文档）
# tags 分组 标签
router = APIRouter(prefix="/api/news", tags=["news"])

# 接口实现流程
# 1. 模块化路由 → API 接口规范文档
# 2. 定义模型类 → 数据库表（数据库设计文档）
# 3. 在 crud 文件夹里面创建文件，封装操作数据库的方法
# 4. 在路由处理函数里面调用 crud 封装好的方法，响应结果


# @router.get("/categories")
# async def get_categories(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
#     # 先获取数据库里面新闻分类数据 → 先定义模型类 → 封装查询数据的方法
#     categories = await news_cache.get_categories(db, skip, limit)
#     return  categories

@router.get("/categories")
async def get_categories(skip: int = 0, limit: int = 100, db: AsyncSession = Depends(get_db)):
    categories = await news_cache.get_categories(db, skip, limit)
    return {
        "code": 200,
        "message": "获取分类成功",
        "data": categories
    }


# @router.get("/list")
# async def get_news_list(
#         category_id: int = Query(..., alias="categoryId"),
#         page: int = 1,
#         page_size: int = Query(10, alias="pageSize", le=100),
#         db: AsyncSession = Depends(get_db)
# ):
#     # 思路：处理分页规则 → 查询新闻列表 → 计算总量 → 计算是否还有更多
#     offset = (page - 1) * page_size
#     news_list = await news_cache.get_news_list(db, category_id, offset, page_size)
#     total = await news.get_news_count(db, category_id)
#     # (跳过的 + 当前列表里面的数量) < 总量
#     has_more = (offset + len(news_list)) < total
#     return {
#         "code": 200,
#         "message": "获取新闻列表成功",
#         "data": {
#             "list": news_list,
#             "total": total,
#             "hasMore": has_more
#         }
#     }
@router.get("/list")
async def get_news_list(
        category_id: int = Query(..., alias="categoryId"),
        page: int = Query(1, ge=1),
        page_size: int = Query(10, alias="pageSize", ge=1, le=100),
        db: AsyncSession = Depends(get_db)
):
    offset = (page - 1) * page_size
    news_list = await news_cache.get_news_list(db, category_id, page=page, page_size=page_size, offset=offset)

    total = await news_cache.get_cache_news_count(category_id)
    if total is None:
        total = await news.get_news_count(db, category_id)
        await news_cache.set_cache_news_count(category_id, total)

    has_more = (offset + len(news_list)) < total

    # 用 Schema 序列化，把 snake_case 转成前端需要的 camelCase
    from schemas.base import NewsItemBase
    formatted_list = []
    for item in news_list:
        obj = NewsItemBase.model_validate(item)
        d = obj.model_dump(mode="json", by_alias=False)
        # 手动转成前端需要的字段名
        formatted_list.append({
            "id": d["id"],
            "title": d["title"],
            "description": d.get("description", ""),
            "image": d.get("image", ""),
            "author": d.get("author", ""),
            "views": d["views"],
            "publishTime": d.get("publish_time", ""),
            "categoryId": d.get("category_id", 0)
        })

    return {
        "code": 200,
        "message": "获取新闻列表成功",
        "data": {
            "list": formatted_list,
            "total": total,
            "hasMore": has_more
        }
    }
# @router.get("/list")
# async def get_news_list(
#         category_id: int = Query(..., alias="categoryId"),
#         page: int = 1,
#         page_size: int = Query(10, alias="pageSize", le=100),
#         db: AsyncSession = Depends(get_db)
# ):
#     offset = (page - 1) * page_size
#     news_list = await news_cache.get_news_list(db, category_id, offset, page_size)
#
#     # 新增兜底判断：缓存为空则查询数据库并写入缓存
#     if news_list is None:
#         news_list = await news.get_news_page(db, category_id, offset, page_size)
#         await news_cache.set_cache_news_list(category_id, offset, page_size, news_list)
#
#     total = await news.get_news_count(db, category_id)
#     has_more = (offset + len(news_list)) < total
#     return {
#         "code": 200,
#         "message": "获取新闻列表成功",
#         "data": {
#             "list": news_list,
#             "total": total,
#             "hasMore": has_more
#         }
#     }
# @router.get("/list")
# async def get_news_list(
#         category_id: int = Query(..., alias="categoryId"),
#         page: int = 1,
#         page_size: int = Query(10, alias="pageSize", le=100),
#         db: AsyncSession = Depends(get_db)
# ):
#     offset = (page - 1) * page_size
#     # ======================修复这一行======================
#     # 1. 删除多余的 db
#     # 2. 传参顺序匹配函数：category_id, page, page_size
#     news_list = await news_cache.get_cache_news_list(category_id, page, page_size)
#     # ======================================================
#
#     # 读取分类总数缓存（这部分无错误，保留）
#     total = await news_cache.get_cache_news_count(category_id)
#     if total is None:
#         total = await news.get_news_count(db, category_id)
#         await news_cache.set_cache_news_count(category_id, total)
#
#     has_more = (offset + len(news_list)) < total
#     return {
#         "code": 200,
#         "message": "获取新闻列表成功",
#         "data": {
#             "list": news_list,
#             "total": total,
#             "hasMore": has_more
#         }
#     }


@router.get("/detail")
async def get_news_detail(news_id: int = Query(..., alias="id"), db: AsyncSession = Depends(get_db)):
    # 延迟导入，避免循环引用
    from config.cache_conf import delete_cache
    from cache.news_cache import NEWS_DETAIL_PREFIX

    # 获取新闻详情 + 浏览量+1 + 相关新闻
    news_detail = await news_cache.get_news_detail(db, news_id)
    if not news_detail:
        raise HTTPException(status_code=404, detail="新闻不存在")

    views_res = await news.increase_news_views(db, news_detail.id)
    if not views_res:
        raise HTTPException(status_code=404, detail="新闻不存在")

    # 修复4: 浏览量+1之后，主动让详情缓存失效（否则下次读到的还是旧的 views）
    await delete_cache(f"{NEWS_DETAIL_PREFIX}{news_id}")

    # 修复5: 返回给前端的 views 应该是更新后的值（对象还没刷新，手动 +1）
    updated_views = news_detail.views + 1

    related_news = await news_cache.get_related_news(db, news_detail.id, news_detail.category_id)

    return {
      "code": 200,
      "message": "success",
      "data": {
        "id": news_detail.id,
        "title": news_detail.title,
        "content": news_detail.content,
        "image": news_detail.image,
        "author": news_detail.author,
        "publishTime": news_detail.publish_time,
        "categoryId": news_detail.category_id,
        "views": updated_views,
        "relatedNews": related_news
      }
    }
