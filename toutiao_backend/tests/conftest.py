"""
conftest.py - pytest 公共配置和 Fixtures

本文件定义了所有测试共用的 fixtures（测试前置条件），
包括 HTTP 客户端、数据库会话、测试数据等。

Fixtures 说明:
- event_loop: 事件循环，用于异步测试
- async_client: 异步 HTTP 客户端，用于接口测试
- db_session: 数据库会话，用于数据测试
- test_news_data: 新闻测试数据
- test_rag_cases: RAG 质量测试用例
- test_multiturn_cases: 多轮对话测试用例
- test_invalid_inputs: 无效输入测试用例
"""

import os
import sys
import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# 确保项目根目录在 sys.path 中
# 这样测试文件可以直接 import 项目模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 导入 FastAPI 应用和数据库配置
from main import app
from config.db_conf import get_db, AsyncSessionLocal, async_engine

# 测试配置常量
BASE_URL = "http://testserver"  # ASGI 内部测试用的基础 URL
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", "mysql+aiomysql://root:root@localhost:3306/news_app?charset=utf8mb4")


@pytest.fixture(scope="function", autouse=True)
async def cleanup_db_pool():
    """
    每个测试后自动清理数据库连接池

    pytest-asyncio 为每个测试函数创建独立的事件循环，
    但 SQLAlchemy 的 async_engine 连接池是全局的，连接绑定在旧循环上。
    如果不清理，下一个测试复用旧连接时会报 'NoneType' object has no attribute 'send'。
    每个测试结束后 dispose 引擎，强制释放所有连接。
    """
    yield
    await async_engine.dispose()


@pytest.fixture(scope="function")
async def async_client():
    """
    异步 HTTP 测试客户端 fixture
    
    使用 httpx 的 AsyncClient + ASGITransport 直接测试 FastAPI 应用，
    不需要真正启动 HTTP 服务器，速度更快。
    每个测试函数都会创建新的客户端实例，确保测试隔离。
    
    Yields:
        httpx.AsyncClient: 可直接调用 FastAPI 路由的测试客户端
        
    使用方法:
        response = await async_client.get("/api/news/list")
        response = await async_client.post("/api/ai/rag_chat", json={...})
    """
    # ASGITransport 让 httpx 直接与 FastAPI 应用通信
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url=BASE_URL) as client:
        yield client


@pytest.fixture(scope="function")
async def db_session():
    """
    异步数据库会话 fixture
    
    为数据一致性测试提供独立的数据库会话。
    每个测试函数都会创建新的会话，确保测试数据隔离。
    
    Yields:
        AsyncSession: SQLAlchemy 异步会话对象
        
    使用方法:
        result = await db_session.execute(select(News))
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


@pytest.fixture
def test_news_data():
    """
    新闻测试数据 fixture
    
    提供新闻分类和单条新闻的测试数据。
    适用于新闻接口测试和数据一致性测试。
    
    Returns:
        dict: 包含 categories（分类列表）和 sample_news（示例新闻）
    """
    return {
        "categories": [
            {"id": 1, "name": "推荐"},
            {"id": 2, "name": "热榜"},
            {"id": 3, "name": "科技"},
            {"id": 4, "name": "体育"},
            {"id": 5, "name": "财经"}
        ],
        "sample_news": {
            "id": 1,
            "title": "社区时间银行养老模式受关注",
            "content": "社区时间银行是一种新型的养老模式，通过志愿者服务时间兑换养老服务...",
            "category_id": 1,
            "author": "测试作者",
            "image": "https://example.com/image.jpg",
            "publish_time": "2026-07-01 10:00:00",
            "views": 1000
        }
    }


@pytest.fixture
def test_rag_cases():
    """
    RAG 质量测试用例 fixture
    
    定义了 3 个 RAG 检索精度测试用例，
    每个用例包含问题和期望命中的关键词。
    适用于 test_rag/test_rag_quality.py 中的参数化测试。
    
    Returns:
        list[dict]: RAG 测试用例列表
            - id: 用例编号
            - question: 测试问题（必须是新闻库中存在的话题）
            - expected_keywords: 期望回答中包含的关键词
    """
    return [
        {
            "id": "RAG001",
            "question": "社区时间银行养老是什么？",
            "expected_keywords": ["养老", "社区", "银行", "模式"]
        },
        {
            "id": "RAG002",
            "question": "中国乒乓球队在世乒赛上取得了什么成绩？",
            "expected_keywords": ["乒乓", "世乒赛", "冠军", "中国"]
        },
        {
            "id": "RAG003",
            "question": "中国消费复苏的情况怎么样？",
            "expected_keywords": ["消费", "复苏", "经济", "增长"]
        }
    ]


@pytest.fixture
def test_multiturn_cases():
    """
    多轮对话测试用例 fixture
    
    定义了多轮对话的测试场景，
    用于验证 RAG 系统的上下文保持能力。
    
    Returns:
        list[dict]: 多轮对话测试用例列表
            - id: 用例编号
            - conversations: 对话历史列表，按顺序排列
            - expected_context: 最后一轮回答中应包含的上下文关键词
    """
    return [
        {
            "id": "MT001",
            "conversations": [
                {"role": "user", "content": "社区时间银行养老是什么？"},
                {"role": "user", "content": "这个模式对老年人有什么好处？"}
            ],
            "expected_context": ["养老", "老人", "好处", "模式", "社区"]
        }
    ]


@pytest.fixture
def test_invalid_inputs():
    """
    无效输入测试用例 fixture
    
    定义了各种边界和异常输入场景，
    用于测试接口的参数校验能力。
    
    Returns:
        list[dict]: 无效输入测试用例列表
            - question: 测试输入
            - desc: 用例描述
    """
    return [
        {"question": "", "desc": "空问题"},
        {"question": "   ", "desc": "仅空格"},
        {"question": "a" * 10000, "desc": "超长输入"}
    ]
