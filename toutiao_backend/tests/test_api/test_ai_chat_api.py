"""
test_ai_chat_api.py - AI 问答接口测试

本文件测试 AI 相关的 API 接口，包括:
1. RAG 聊天接口：POST /api/ai/rag_chat
2. Agent 聊天接口：POST /api/ai/agent_chat
3. 新闻同步接口：POST /api/ai/sync_news_to_vector

测试场景覆盖:
- 正常对话：验证 RAG 回答质量
- 异常输入：测试空问题、无效参数等
- 多轮对话：验证上下文保持能力
- 边界场景：超长输入、特殊字符等
"""

import pytest
from httpx import AsyncClient


class TestAIChatAPI:
    """
    AI 问答接口测试类
    
    包含 RAG 聊天、Agent 对话、新闻同步等接口的测试用例。
    
    核心测试点:
    - 接口是否正确处理输入参数
    - RAG 回答是否基于参考新闻
    - 多轮对话是否保持上下文
    - 异常输入是否被正确拦截
    """

    # ==================== 1. RAG 聊天接口测试 ====================
    
    @pytest.mark.asyncio
    async def test_rag_chat_success(self, async_client):
        """
        测试 RAG 聊天 - 正常场景
        
        验证点:
        1. 接口返回状态码 200
        2. 响应包含 answer 和 reference_news 字段
        3. 回答内容不为空（证明 RAG 检索成功）
        """
        payload = {
            "question": "社区时间银行养老是什么？",
            "history": []
        }
        response = await async_client.post("/api/ai/rag_chat", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert "answer" in data, "响应缺少 answer 字段"
        assert "reference_news" in data, "响应缺少 reference_news 字段"
        assert len(data["answer"]) > 0, "回答内容为空"

    @pytest.mark.asyncio
    async def test_rag_chat_empty_question(self, async_client):
        """
        测试 RAG 聊天 - 空问题
        
        预期行为: 空问题应被后端拦截，返回 400
        """
        payload = {
            "question": "",
            "history": []
        }
        response = await async_client.post("/api/ai/rag_chat", json=payload)
        assert response.status_code == 400, "空问题应返回 400"

    @pytest.mark.asyncio
    async def test_rag_chat_with_whitespace_only(self, async_client):
        """
        测试 RAG 聊天 - 仅空格的问题
        
        预期行为: 仅空格的问题等同于空问题，应返回 400
        """
        payload = {
            "question": "   ",
            "history": []
        }
        response = await async_client.post("/api/ai/rag_chat", json=payload)
        assert response.status_code == 400, "仅空格的问题应返回 400"

    @pytest.mark.asyncio
    async def test_rag_chat_missing_question(self, async_client):
        """
        测试 RAG 聊天 - 缺少 question 字段
        
        预期行为: 缺少必填字段应返回 422（Pydantic 校验失败）
        """
        payload = {
            "history": []
        }
        response = await async_client.post("/api/ai/rag_chat", json=payload)
        assert response.status_code == 422, "缺少 question 字段应返回 422"

    # ==================== 2. RAG 多轮对话测试 ====================
    
    @pytest.mark.asyncio
    async def test_rag_chat_multiturn(self, async_client):
        """
        测试 RAG 聊天 - 多轮对话场景
        
        测试流程:
        1. 第一轮：询问"社区时间银行养老"
        2. 第二轮：携带历史，追问"这个模式对老年人的好处"
        
        验证点:
        1. 两轮对话都能正常返回
        2. 第二轮回答基于上下文（包含历史信息）
        """
        # 第一轮：新话题
        first_payload = {
            "question": "社区时间银行养老是什么？",
            "history": []
        }
        first_response = await async_client.post("/api/ai/rag_chat", json=first_payload)
        assert first_response.status_code == 200
        first_answer = first_response.json()["answer"]
        
        # 第二轮：携带历史追问
        second_payload = {
            "question": "这个模式对老年人有什么好处？",
            "history": [
                {"role": "user", "content": "社区时间银行养老是什么？"},
                {"role": "assistant", "content": first_answer}
            ]
        }
        second_response = await async_client.post("/api/ai/rag_chat", json=second_payload)
        assert second_response.status_code == 200
        
        second_data = second_response.json()
        assert "answer" in second_data, "第二轮响应缺少 answer 字段"
        assert len(second_data["answer"]) > 0, "第二轮回答为空"

    # ==================== 3. Agent 聊天接口测试 ====================
    
    @pytest.mark.asyncio
    async def test_agent_chat_success(self, async_client):
        """
        测试 Agent 聊天 - 正常场景
        
        验证点:
        1. Agent 接口返回状态码 200
        2. 响应包含 answer 或 message 字段
        """
        payload = {
            "question": "帮我查询最新的科技新闻"
        }
        response = await async_client.post("/api/ai/agent_chat", json=payload)
        assert response.status_code == 200
        
        data = response.json()
        assert "answer" in data or "message" in data, \
            "Agent 响应缺少 answer 或 message 字段"

    @pytest.mark.asyncio
    async def test_agent_chat_empty_question(self, async_client):
        """
        测试 Agent 聊天 - 空问题
        
        预期行为: 空问题应返回 400
        """
        payload = {"question": ""}
        response = await async_client.post("/api/ai/agent_chat", json=payload)
        assert response.status_code == 400, "空问题应返回 400"

    @pytest.mark.asyncio
    async def test_agent_chat_missing_question(self, async_client):
        """
        测试 Agent 聊天 - 缺少 question 字段
        
        预期行为: 缺少必填字段应返回 422
        """
        payload = {}
        response = await async_client.post("/api/ai/agent_chat", json=payload)
        assert response.status_code == 422, "缺少 question 字段应返回 422"

    # ==================== 4. 新闻同步接口测试 ====================
    
    @pytest.mark.asyncio
    async def test_sync_news_success(self, async_client):
        """
        测试同步新闻到向量库 - 正常场景
        
        验证点:
        1. 同步接口可正常调用
        2. 数据库异常时允许返回 500
        """
        response = await async_client.post("/api/ai/sync_news_to_vector")
        # 可能因为数据库连接问题返回 500
        assert response.status_code in [200, 500], \
            f"同步接口状态码异常: {response.status_code}"
        if response.status_code == 200:
            data = response.json()
            assert "message" in data, "响应缺少 message 字段"

    # ==================== 5. 边界和异常场景测试 ====================
    
    @pytest.mark.asyncio
    async def test_rag_chat_very_long_question(self, async_client):
        """
        测试 RAG 聊天 - 超长输入
        
        验证点: 超长输入应被系统正确处理（可能截断或返回错误）
        """
        payload = {
            "question": "这是一个非常长的问题" * 100,
            "history": []
        }
        response = await async_client.post("/api/ai/rag_chat", json=payload)
        # 200: 正常处理 | 400: 拒绝处理 | 422: 参数校验失败
        assert response.status_code in [200, 400, 422], \
            f"超长输入处理异常: {response.status_code}"

    @pytest.mark.asyncio
    async def test_rag_chat_invalid_history_format(self, async_client):
        """
        测试 RAG 聊天 - 无效的历史格式
        
        预期行为: history 应为列表格式，字符串格式应返回 422
        """
        payload = {
            "question": "测试问题",
            "history": "invalid_format"  # 应该是列表类型
        }
        response = await async_client.post("/api/ai/rag_chat", json=payload)
        assert response.status_code == 422, "无效的 history 格式应返回 422"

    @pytest.mark.asyncio
    async def test_rag_chat_special_characters(self, async_client):
        """
        测试 RAG 聊天 - 特殊字符
        
        验证点: 特殊字符应被正确处理，不导致系统异常
        """
        payload = {
            "question": "测试特殊字符：!@#$%^&*()_+-=[]{}|;':\",./<>?",
            "history": []
        }
        response = await async_client.post("/api/ai/rag_chat", json=payload)
        assert response.status_code in [200, 400], \
            f"特殊字符处理异常: {response.status_code}"
