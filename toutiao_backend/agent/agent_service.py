import re
import logging
from datetime import datetime
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from .function_calling import function_calling_flow
from .workflows import WORKFLOW_CONFIG, WORKFLOW_FUNCTIONS, category_summary_workflow
from rag.rag_service import rag_chat

logger = logging.getLogger(__name__)


async def detect_workflow(question: str) -> Dict[str, Any]:
    """
    意图识别：基于规则+正则匹配 workflow trigger_patterns
    返回 {"detected": True, "workflow": name, "params": {...}} 或 {"detected": False}
    """
    for workflow in WORKFLOW_CONFIG:
        patterns = workflow.get("trigger_patterns", [])
        for pattern in patterns:
            if re.search(pattern, question):
                workflow_name = workflow["name"]
                # 按不同 workflow 提取参数
                if workflow_name == "category_summary":
                    category_name = _extract_category_name(question)
                    if category_name:
                        return {
                            "detected": True,
                            "workflow": workflow_name,
                            "params": {"category_name": category_name}
                        }
                    # 匹配到 pattern 但没提取到分类名 → 继续找下一个 workflow
                    continue
                elif workflow_name == "daily_news_brief":
                    date_str = _extract_date_from_question(question)
                    return {
                        "detected": True,
                        "workflow": workflow_name,
                        "params": {"date_str": date_str} if date_str else {}
                    }
                elif workflow_name == "hot_news_ranking":
                    return {
                        "detected": True,
                        "workflow": workflow_name,
                        "params": {"limit": 10}
                    }
    return {"detected": False}


def _extract_category_name(question: str) -> str:
    category_keywords = ["科技", "财经", "娱乐", "体育", "政治", "社会", "国际", "军事", "教育", "健康", "推荐", "热榜"]
    for keyword in category_keywords:
        if keyword in question:
            return keyword
    return ""


def _extract_date_from_question(question: str) -> str:
    """从问题中提取日期（YYYY-MM-DD），提取不到返回今日"""
    m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", question)
    if m:
        try:
            d = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return d.strftime("%Y-%m-%d")
        except ValueError:
            pass
    # 没提取到日期 → 默认今日
    return datetime.now().strftime("%Y-%m-%d")


async def agent_chat(db: AsyncSession, question: str) -> Dict[str, Any]:
    """
    Agent 主路由：意图识别 → workflow / function_calling / RAG 三路分发
    路由优先级：workflow（正则匹配） > function_calling（LLM+规则） > RAG（兜底）
    """
    # ============ 路径1：workflow 意图识别（正则匹配） ============
    workflow_detection = await detect_workflow(question)

    if workflow_detection["detected"]:
        workflow_name = workflow_detection["workflow"]
        params = workflow_detection["params"]

        workflow_func = WORKFLOW_FUNCTIONS.get(workflow_name)
        if workflow_func:
            try:
                result = await workflow_func(db, **params)
                return {
                    "type": "workflow",
                    "workflow": workflow_name,
                    "answer": result["answer"],
                    "workflow_steps": result.get("workflow_steps", []),
                    "summary": result.get("summary", {})
                }
            except Exception as e:
                logger.error(f"workflow {workflow_name} 执行异常，降级到 function_calling: {e}", exc_info=True)
                # workflow 异常 → 继续走 function_calling
        else:
            logger.warning(f"workflow {workflow_name} 未注册到 WORKFLOW_FUNCTIONS")

    # ============ 路径2：Function Calling（LLM + 规则兜底） ============
    function_calling_result = await function_calling_flow(db, question)

    fc_type = function_calling_result.get("type")

    # 类型1：成功调用工具
    if fc_type == "tool_call":
        return {
            "type": "tool_call",
            "answer": function_calling_result["answer"],
            "tool_used": function_calling_result["tool_used"],
            "tool_result": function_calling_result["tool_result"]
        }

    # 类型2：LLM 直接回答（无需工具，闲聊场景）
    if fc_type == "direct_answer":
        return {
            "type": "direct_answer",
            "answer": function_calling_result["answer"],
            "tool_used": None,
            "tool_result": None
        }

    # 类型3：规则兜底（LLM 不可用时基于正则匹配工具）
    if fc_type == "rule_fallback":
        return {
            "type": "rule_fallback",
            "answer": function_calling_result["answer"],
            "tool_used": function_calling_result["tool_used"],
            "tool_result": function_calling_result["tool_result"],
            "fallback_reason": function_calling_result.get("fallback_reason")
        }

    # 类型4：需要降级到 RAG（工具调用失败 / 未匹配工具 / LLM 异常）
    if fc_type == "need_rag":
        logger.info(f"降级到 RAG，原因: {function_calling_result.get('fallback_reason')}")
        rag_result = await rag_chat(question)
        return {
            "type": "rag_fallback",
            "answer": rag_result["answer"],
            "reference_news": rag_result["reference_news"],
            "tool_used": function_calling_result.get("tool_used"),
            "tool_result": function_calling_result.get("tool_result"),
            "fallback_reason": function_calling_result.get("fallback_reason")
        }

    # 类型5：系统异常兜底
    return {
        "type": "error",
        "answer": function_calling_result.get("answer") or "系统异常，请稍后重试",
        "tool_used": None,
        "tool_result": None,
        "fallback_reason": function_calling_result.get("fallback_reason")
    }
