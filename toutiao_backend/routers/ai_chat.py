import os
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import List, Optional
import httpx
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from rag.rag_service import rag_chat, sync_news_to_vector_db, unified_chat
from agent.agent_service import agent_chat as agent_chat_service
from agent.news_agent import (
    process_news_with_skills,
    format_skill_result_as_text,
    get_skill_choices,
    SKILL_DEFINITIONS,
    SKILL_CHOICES
)
from config.db_conf import get_db

router = APIRouter(prefix="/api/ai", tags=["AI问答"])


class UnifiedChatRequest(BaseModel):
    question: str
    history: list = []


@router.post("/unified_chat")
async def unified_chat_api(request: UnifiedChatRequest):
    """统一聊天：RAG优先，无相关新闻则回退普通对话"""
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    try:
        result = await unified_chat(request.question, request.history)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
DASHSCOPE_ENDPOINT = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"


class ChatRequest(BaseModel):
    messages: list


class RAGChatRequest(BaseModel):
    question: str
    history: list = []


@router.post("/chat")
async def ai_chat(request: ChatRequest):
    if not DASHSCOPE_API_KEY:
        raise HTTPException(status_code=500, detail="DASHSCOPE_API_KEY 未配置")

    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json",
        "X-DashScope-SSE": "enable"
    }
    payload = {
        "model": "qwen3-max-preview",
        "messages": request.messages,
        "stream": True
    }

    async def stream_response():
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream("POST", DASHSCOPE_ENDPOINT, headers=headers, json=payload) as response:
                response.raise_for_status()
                async for chunk in response.aiter_text():
                    yield chunk

    return StreamingResponse(
        stream_response(),
        media_type="text/event-stream"
    )


@router.post("/rag_chat")
async def rag_chat_api(request: RAGChatRequest):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    try:
        result = await rag_chat(request.question, request.history)
        return {
            "answer": result["answer"],
            "reference_news": result["reference_news"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync_news_to_vector")
async def sync_news_api(db: AsyncSession = Depends(get_db), limit: int = 0):
    try:
        count = await sync_news_to_vector_db(db, limit=limit)
        return {"message": f"成功同步 {count} 个新闻片段到向量库"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class AgentChatRequest(BaseModel):
    question: str


@router.post("/agent_chat")
async def agent_chat_api(request: AgentChatRequest, db: AsyncSession = Depends(get_db)):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    try:
        result = await agent_chat_service(db, request.question)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============ 新闻Agent路由 ============

class NewsProcessRequest(BaseModel):
    news_text: str
    news_title: str = ""
    skills: Optional[List[str]] = None


@router.get("/news_skills")
async def get_news_skills():
    """获取所有可用的新闻处理Skill列表"""
    return {
        "code": 200,
        "data": SKILL_CHOICES
    }


@router.post("/news_process")
async def news_process_api(request: NewsProcessRequest):
    """使用指定Skill处理新闻"""
    if not request.news_text or len(request.news_text.strip()) < 10:
        raise HTTPException(status_code=400, detail="新闻内容太短")

    try:
        result = await process_news_with_skills(
            news_text=request.news_text,
            news_title=request.news_title,
            skills=request.skills
        )

        if result["status"] == "success":
            formatted_text = format_skill_result_as_text(result["results"])
            return {
                "code": 200,
                "data": {
                    "status": "success",
                    "news_title": result["news_title"],
                    "skill_results": result["results"],
                    "formatted_text": formatted_text
                }
            }
        else:
            return {
                "code": 500,
                "data": result
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class NewsShareRequest(BaseModel):
    news_id: int
    news_title: str
    news_content: str
    user_message: str = ""


@router.post("/news_share")
async def news_share_api(request: NewsShareRequest):
    """分享新闻到AI，自动执行默认Skill并返回结果"""
    if not request.news_content or len(request.news_content.strip()) < 10:
        raise HTTPException(status_code=400, detail="新闻内容太短")

    try:
        result = await process_news_with_skills(
            news_text=request.news_content,
            news_title=request.news_title,
            skills=["news_summarize", "news_extract", "news_question_gen"]
        )

        if result["status"] == "success":
            formatted_text = format_skill_result_as_text(result["results"])
            return {
                "code": 200,
                "data": {
                    "type": "news_share",
                    "status": "success",
                    "news_id": request.news_id,
                    "news_title": request.news_title,
                    "skill_results": result["results"],
                    "formatted_text": formatted_text,
                    "skill_choices": SKILL_CHOICES
                }
            }
        else:
            return {
                "code": 500,
                "data": result
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
