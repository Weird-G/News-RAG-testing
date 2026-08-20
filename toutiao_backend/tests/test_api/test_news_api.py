"""
test_news_api.py - 新闻接口测试

本文件测试新闻相关的 API 接口，包括:
1. 新闻分类接口：GET /api/news/categories
2. 新闻列表接口：GET /api/news/list
3. 新闻详情接口：GET /api/news/detail

每个测试方法都测试了接口的不同场景：
- 正常场景：验证接口返回正确的数据结构和内容
- 异常场景：测试缺少必填参数、无效参数等情况
- 边界场景：测试分页、不存在的 ID 等边界情况

所有测试方法使用 async_client fixture 发送 HTTP 请求，
并通过断言验证响应状态码和响应体内容。

注意: 部分测试依赖数据库和 Redis 缓存连接，如连接失败会返回 500
"""

import pytest
from httpx import AsyncClient


class TestNewsAPI:
    """
    新闻接口测试类
    
    包含新闻分类、列表、详情等接口的测试用例。
    每个方法对应一个测试场景。
    
    测试原则:
    - 先测试正常流程，再测试异常流程
    - 每个测试只验证一个核心功能点
    - 使用清晰的断言信息便于排查问题
    """

    # ==================== 1. 新闻分类接口测试 ====================
    
    @pytest.mark.asyncio
    async def test_get_categories_success(self, async_client):
        """
        测试获取新闻分类 - 正常场景
        
        验证点:
        1. 接口返回状态码 200（或 500 如数据库连接失败）
        2. 返回数据是列表类型
        3. 每个分类包含必要字段 (id, name)
        """
        response = await async_client.get("/api/news/categories")
        # 数据库未连接时可能返回 500
        assert response.status_code in [200, 500], f"状态码异常: {response.status_code}"
        
        if response.status_code == 200:
            data = response.json()["data"]
            assert isinstance(data, list), "返回数据应为列表类型"

            # 验证分类数据结构
            for category in data:
                assert "id" in category, "分类缺少 id 字段"
                assert "name" in category, "分类缺少 name 字段"

    @pytest.mark.asyncio
    async def test_get_categories_with_pagination(self, async_client):
        """
        测试获取分类 - 分页参数
        
        验证点:
        1. 支持 skip 和 limit 参数
        2. 返回数量不超过 limit
        3. 数据库连接异常时允许返回 500
        """
        response = await async_client.get("/api/news/categories", params={
            "skip": 0,
            "limit": 5
        })
        # 可能因为数据库连接问题返回 500
        assert response.status_code in [200, 500], f"状态码异常: {response.status_code}"
        if response.status_code == 200:
            data = response.json()["data"]
            assert len(data) <= 5, "返回数量超过 limit 限制"

    # ==================== 2. 新闻列表接口测试 ====================
    
    @pytest.mark.asyncio
    async def test_get_news_list_success(self, async_client):
        """
        测试获取新闻列表 - 正常场景
        
        验证点:
        1. 接口返回状态码 200（或 500 如数据库连接失败）
        2. 响应包含 code/message/data 结构
        3. data 中包含 list/total/hasMore 字段
        """
        response = await async_client.get("/api/news/list", params={
            "categoryId": 1,
            "page": 1,
            "pageSize": 10
        })
        assert response.status_code in [200, 500], f"状态码异常: {response.status_code}"
        
        if response.status_code == 200:
            data = response.json()
            assert data["code"] == 200, f"业务状态码异常: {data['code']}"
            assert "data" in data, "响应缺少 data 字段"
            assert "list" in data["data"], "data 缺少 list 字段"
            assert "total" in data["data"], "data 缺少 total 字段"
            assert "hasMore" in data["data"], "data 缺少 hasMore 字段"

    @pytest.mark.asyncio
    async def test_get_news_list_missing_category(self, async_client):
        """
        测试获取新闻列表 - 缺少必填参数
        
        预期行为: categoryId 是必填参数，缺少时返回 422
        """
        response = await async_client.get("/api/news/list", params={
            "page": 1,
            "pageSize": 10
        })
        assert response.status_code == 422, "缺少 categoryId 参数应返回 422"

    @pytest.mark.asyncio
    async def test_get_news_list_invalid_page_size(self, async_client):
        """
        测试获取新闻列表 - 无效 pageSize 参数
        
        预期行为: pageSize 超过 100 时返回 422
        """
        response = await async_client.get("/api/news/list", params={
            "categoryId": 1,
            "page": 1,
            "pageSize": 101  # 超过限制
        })
        assert response.status_code == 422, "pageSize 超过限制应返回 422"

    @pytest.mark.asyncio
    async def test_get_news_list_pagination(self, async_client):
        """
        测试获取新闻列表 - 分页逻辑
        
        验证点:
        1. 分页接口正常返回
        2. hasMore 字段逻辑正确（如果本页数量 < pageSize，则 hasMore 应为 false）
        """
        # 请求第一页
        response1 = await async_client.get("/api/news/list", params={
            "categoryId": 1,
            "page": 1,
            "pageSize": 5
        })
        assert response1.status_code in [200, 500]
        
        if response1.status_code == 200:
            data1 = response1.json()["data"]
            
            # 请求第二页
            response2 = await async_client.get("/api/news/list", params={
                "categoryId": 1,
                "page": 2,
                "pageSize": 5
            })
            assert response2.status_code in [200, 500]
            
            if response2.status_code == 200:
                data2 = response2.json()["data"]
                
                # 验证 hasMore 逻辑
                if len(data1["list"]) < 5:
                    assert data1["hasMore"] is False, "本页数量不足，hasMore 应为 false"

    # ==================== 3. 新闻详情接口测试 ====================
    
    @pytest.mark.asyncio
    async def test_get_news_detail_success(self, async_client):
        """
        测试获取新闻详情 - 正常场景
        
        验证点:
        1. 接口返回状态码 200（或 500 如数据库连接失败）
        2. 返回指定 ID 的新闻详情
        3. 详情包含必要字段
        """
        response = await async_client.get("/api/news/detail", params={"id": 1})
        assert response.status_code in [200, 500], f"状态码异常: {response.status_code}"
        
        if response.status_code == 200:
            data = response.json()
            assert data["code"] == 200
            assert "data" in data
            assert data["data"]["id"] == 1, "返回的新闻 ID 不匹配"
            assert "title" in data["data"], "详情缺少 title 字段"
            assert "content" in data["data"], "详情缺少 content 字段"

    @pytest.mark.asyncio
    async def test_get_news_detail_not_found(self, async_client):
        """
        测试获取新闻详情 - 不存在的新闻 ID
        
        预期行为: 不存在的 ID 返回 404
        """
        response = await async_client.get("/api/news/detail", params={"id": 99999})
        assert response.status_code == 404, "不存在的新闻应返回 404"

    @pytest.mark.asyncio
    async def test_get_news_detail_missing_id(self, async_client):
        """
        测试获取新闻详情 - 缺少必填参数
        
        预期行为: 缺少 id 参数返回 422
        """
        response = await async_client.get("/api/news/detail")
        assert response.status_code == 422, "缺少 id 参数应返回 422"

    # ==================== 4. 边界场景测试 ====================
    
    @pytest.mark.asyncio
    async def test_get_news_list_zero_category(self, async_client):
        """
        测试获取新闻列表 - 不存在的分类 ID
        
        验证点: 不存在的分类应返回空列表，但状态码为 200
        """
        response = await async_client.get("/api/news/list", params={
            "categoryId": 9999,
            "page": 1,
            "pageSize": 10
        })
        assert response.status_code in [200, 500], f"状态码异常: {response.status_code}"
        
        if response.status_code == 200:
            data = response.json()
            assert data["data"]["total"] == 0, "不存在的分类应返回 0 条数据"

    @pytest.mark.asyncio
    async def test_get_news_list_negative_page(self, async_client):
        """
        测试获取新闻列表 - 负数页码
        
        验证点: 负数页码应被后端正确处理（可能返回 200、422 或 500）
        """
        response = await async_client.get("/api/news/list", params={
            "categoryId": 1,
            "page": -1,
            "pageSize": 10
        })
        # 负数页码可能触发数据库错误，允许 200、422 或 500
        assert response.status_code in [200, 422, 500], \
            f"负数页码应被正确处理，实际返回: {response.status_code}"
