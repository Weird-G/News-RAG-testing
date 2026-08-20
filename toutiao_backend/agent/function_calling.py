import os
import re
import json
import logging
import httpx
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from .tools import TOOLS_CONFIG, TOOL_FUNCTIONS

logger = logging.getLogger(__name__)

DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
DASHSCOPE_ENDPOINT = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

# 工具名 → 必填参数名（从 TOOLS_CONFIG 自动推导，避免硬编码漂移）
def _required_params(tool_name: str) -> List[str]:
    for tool in TOOLS_CONFIG:
        if tool["name"] == tool_name:
            return [p["name"] for p in tool.get("parameters", []) if p.get("required")]
    return []


def _all_param_specs(tool_name: str) -> List[Dict[str, Any]]:
    for tool in TOOLS_CONFIG:
        if tool["name"] == tool_name:
            return tool.get("parameters", [])
    return []


# ====================================================================
# 步骤1：意图识别（LLM 不可用时降级到规则匹配）
# 简历措辞：基于规则+正则的意图识别（与 LLM Function Calling 互补）
# ====================================================================

# 规则兜底：LLM 不可用 / 输出无法解析时，基于关键词正则匹配工具
RULE_BASED_INTENT = [
    # 精确查询类
    {
        "patterns": [r"浏览量|阅读量|阅读数|点击量|看了多少"],
        "params_extractor": lambda q: {"news_id": _extract_news_id(q)},
        "tool": "get_news_views"
    },
    {
        "patterns": [r"字数|多少字|正文字数|内容长度"],
        "params_extractor": lambda q: {"news_id": _extract_news_id(q)},
        "tool": "count_news_words"
    },
    # 列表检索类
    {
        "patterns": [r"(科技|财经|体育|娱乐|政治|社会|国际|军事|教育|健康|推荐|热榜).*(?:新闻|资讯|文章)"],
        "params_extractor": lambda q: {"category_name": _extract_category(q)},
        "tool": "list_news_by_category"
    },
    {
        "patterns": [r"今天.*新闻|今日.*新闻|(\d{4}[-/]\d{1,2}[-/]\d{1,2}).*新闻|某天.*新闻"],
        "params_extractor": lambda q: {"date_str": _extract_date(q) or datetime.now().strftime("%Y-%m-%d")},
        "tool": "get_news_by_date"
    },
    {
        "patterns": [r"最新.*新闻|最近.*新闻|新发布"],
        "params_extractor": lambda q: {"limit": 10},
        "tool": "get_latest_news"
    },
    {
        "patterns": [r"热门|热点|排行|最火|人气.*高"],
        "params_extractor": lambda q: {"limit": 10},
        "tool": "get_hot_news"
    },
    # 统计聚合类
    {
        "patterns": [r"统计|多少条|总量|总览|分类.*数量|新闻.*总数"],
        "params_extractor": lambda q: {},
        "tool": "get_news_statistics"
    }
]

CATEGORY_KEYWORDS = ["科技", "财经", "娱乐", "体育", "政治", "社会", "国际", "军事", "教育", "健康", "推荐", "热榜"]


def _extract_news_id(question: str) -> Optional[int]:
    """从问题中提取新闻ID（如「新闻1」「新闻ID为3」「ID=5」）"""
    m = re.search(r"(?:新闻\s*ID\s*(?:为|=)?\s*|新闻\s*ID[:：]?\s*|新闻\s*)(\d+)", question)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            return None
    return None


def _extract_category(question: str) -> str:
    for kw in CATEGORY_KEYWORDS:
        if kw in question:
            return kw
    return ""


def _extract_date(question: str) -> Optional[str]:
    """从问题中提取日期（YYYY-MM-DD 或 YYYY/M/D）"""
    m = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", question)
    if m:
        try:
            d = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            return d.strftime("%Y-%m-%d")
        except ValueError:
            return None
    return None


def rule_based_tool_selection(question: str) -> Optional[Dict[str, Any]]:
    """规则兜底：基于正则匹配选择工具（LLM 不可用时使用）"""
    for rule in RULE_BASED_INTENT:
        for pattern in rule["patterns"]:
            if re.search(pattern, question):
                params = rule["params_extractor"](question)
                # 校验必填参数是否齐全
                required = _required_params(rule["tool"])
                missing = [p for p in required if not params.get(p)]
                if missing:
                    logger.info(f"规则匹配到工具 {rule['tool']} 但缺少必填参数 {missing}")
                    continue
                return {"tool": rule["tool"], "params": params}
    return None


# ====================================================================
# 步骤2：LLM 意图识别（构造 prompt，让 LLM 输出工具调用 JSON）
# ====================================================================

def build_function_calling_prompt(question: str) -> str:
    tools_desc = json.dumps(TOOLS_CONFIG, ensure_ascii=False, indent=2)

    return f"""你是一个智能工具调用助手。请根据用户问题判断是否需要调用工具。

可用工具列表：
{tools_desc}

判断规则：
1. 如果用户问题需要查询：新闻浏览量、新闻字数、按分类列新闻、按日期查新闻、最新新闻、热门新闻、新闻统计 → 调用对应工具
2. 如果用户问题是普通聊天、闲聊、新闻内容咨询（如「社区时间银行是什么」）→ 直接回答，不调用工具（这类问题应走RAG）
3. 工具调用规则：先判断意图→选对工具→提取参数→严格按JSON输出
4. 输出格式（必须严格遵循，不要加其他文字）：
{{"tool": "工具名称", "params": {{"参数名": "参数值"}}}}
5. 不需要调用工具时，直接输出对用户问题的自然回答，不要输出JSON

示例：
- 用户「新闻1的浏览量是多少」→ {{"tool": "get_news_views", "params": {{"news_id": 1}}}}
- 用户「今天有什么新闻」→ {{"tool": "get_news_by_date", "params": {{"date_str": "今天日期"}}}}
- 用户「科技类有哪些新闻」→ {{"tool": "list_news_by_category", "params": {{"category_name": "科技"}}}}
- 用户「社区时间银行是什么」→ 不输出JSON，直接说走RAG回答

用户问题：
{question}"""


# ====================================================================
# 步骤3：参数提取与类型转换（LLM 输出的 JSON 可能类型不对）
# ====================================================================

async def parse_tool_call(response: str) -> Optional[Dict[str, Any]]:
    """从 LLM 响应中解析工具调用 JSON"""
    try:
        start = response.find("{")
        end = response.rfind("}") + 1
        if start != -1 and end != -1:
            json_str = response[start:end]
            return json.loads(json_str)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning(f"工具调用JSON解析失败: {e}, 原始响应: {response[:200]}")
    return None


def _convert_param_type(value: Any, target_type: str) -> Any:
    """参数类型转换：LLM 可能返回字符串「1」，工具期望 int 1"""
    try:
        if target_type == "integer":
            if isinstance(value, str):
                return int(value)
            return int(value)
        elif target_type == "string":
            return str(value)
    except (ValueError, TypeError):
        return None
    return value


def _validate_and_convert_params(tool_name: str, params: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """
    参数校验与类型转换
    返回：(转换后的参数, 错误信息列表)
    """
    converted = {}
    errors = []
    param_specs = _all_param_specs(tool_name)

    # 构建 spec 字典
    spec_dict = {p["name"]: p for p in param_specs}

    for name, value in params.items():
        if name not in spec_dict:
            # 未知参数，跳过（不报错，宽松处理）
            continue
        spec = spec_dict[name]
        target_type = spec.get("type", "string")
        converted_value = _convert_param_type(value, target_type)
        if converted_value is None and value is not None:
            errors.append(f"参数 '{name}' 类型转换失败（期望 {target_type}，实际 {type(value).__name__}）")
        else:
            converted[name] = converted_value

    # 检查必填参数
    required = _required_params(tool_name)
    for r in required:
        if r not in converted or converted[r] in (None, "", 0):
            errors.append(f"缺少必填参数 '{r}'")

    return converted, errors


# ====================================================================
# 步骤4：工具执行（含异常兜底）
# ====================================================================

async def call_tool(db: AsyncSession, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """调用工具，含参数校验与异常兜底"""
    if tool_name not in TOOL_FUNCTIONS:
        return {
            "success": False,
            "error": f"工具 '{tool_name}' 不存在",
            "fallback": "unknown_tool"
        }

    # 参数校验与类型转换
    converted_params, errors = _validate_and_convert_params(tool_name, params)
    if errors:
        return {
            "success": False,
            "error": "参数校验失败: " + "; ".join(errors),
            "fallback": "invalid_params"
        }

    try:
        tool_func = TOOL_FUNCTIONS[tool_name]
        result = await tool_func(db, **converted_params)
        return result
    except Exception as e:
        logger.error(f"工具 {tool_name} 执行异常: {e}", exc_info=True)
        return {
            "success": False,
            "error": f"工具执行异常: {str(e)}",
            "fallback": "tool_exception"
        }


# ====================================================================
# 步骤5：执行反馈（基于工具结果生成自然语言回答）
# ====================================================================

async def generate_final_answer(question: str, tool_result: Dict[str, Any]) -> str:
    """基于工具执行结果，让 LLM 生成自然语言回答"""
    if not DASHSCOPE_API_KEY:
        # LLM 不可用时降级：直接格式化工具结果
        return _fallback_format_result(question, tool_result)

    context = json.dumps(tool_result, ensure_ascii=False, indent=2)

    prompt = f"""你是一个专业的新闻助手。请严格基于工具执行结果回答用户问题。

重要规则：
1. 你的回答必须严格基于工具返回的数据，禁止编造或篡改数字
2. 如果工具返回 success=false，请如实告诉用户「查询失败」并说明原因
3. 如果工具返回的数据为空，请告诉用户「没有找到相关数据」
4. 数字（浏览量、字数、统计量）必须与工具返回值完全一致，不可修改

工具执行结果：
{context}

用户问题：
{question}

请用自然、友好的语言总结工具执行结果，回答用户问题。"""

    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "qwen3-max-preview",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(DASHSCOPE_ENDPOINT, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    except Exception as e:
        logger.error(f"LLM生成回答失败，降级到格式化输出: {e}")
        return _fallback_format_result(question, tool_result)


def _fallback_format_result(question: str, tool_result: Dict[str, Any]) -> str:
    """LLM 不可用时的兜底：直接格式化工具结果为文字"""
    if not tool_result.get("success"):
        return f"查询失败：{tool_result.get('error', '未知错误')}"

    data = tool_result.get("data")
    if isinstance(data, dict) and "views" in data:
        return f"新闻《{data.get('title')}》的浏览量为 {data['views']}"
    if isinstance(data, dict) and "word_count" in data:
        return f"新闻《{data.get('title')}》的正文字数为 {data['word_count']} 字"
    if isinstance(data, list):
        return f"共查询到 {len(data)} 条相关数据"
    if isinstance(data, dict) and "by_category" in data:
        return f"共 {data['global']['total_news']} 条新闻，{data['global']['category_count']} 个分类"
    return "查询完成"


# ====================================================================
# 主流程：意图识别 → 工具选择 → 参数提取 → 执行反馈 → 异常降级
# ====================================================================

async def function_calling_flow(db: AsyncSession, question: str) -> Dict[str, Any]:
    """
    Function Calling 主流程
    返回 type 字段供 agent_service 路由：
    - tool_call: 成功调用工具
    - direct_answer: LLM 直接回答（无需工具）
    - rule_fallback: LLM 不可用，规则兜底
    - need_rag: 工具调用失败，降级到 RAG
    - error: 系统异常
    """
    # LLM 不可用 → 直接走规则兜底
    if not DASHSCOPE_API_KEY:
        rule_result = rule_based_tool_selection(question)
        if rule_result:
            tool_result = await call_tool(db, rule_result["tool"], rule_result["params"])
            answer = _fallback_format_result(question, tool_result)
            return {
                "type": "rule_fallback",
                "answer": answer,
                "tool_used": rule_result["tool"],
                "tool_result": tool_result,
                "fallback_reason": "LLM未配置，使用规则匹配"
            }
        return {
            "type": "need_rag",
            "answer": None,
            "tool_used": None,
            "tool_result": None,
            "fallback_reason": "LLM未配置且规则未匹配，降级到RAG"
        }

    # LLM 可用 → 构造 prompt 调用
    prompt = build_function_calling_prompt(question)
    headers = {
        "Authorization": f"Bearer {DASHSCOPE_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "qwen3-max-preview",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(DASHSCOPE_ENDPOINT, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            model_response = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()

        # 尝试解析工具调用 JSON
        tool_call = await parse_tool_call(model_response)

        if tool_call:
            tool_name = tool_call.get("tool")
            params = tool_call.get("params", {})

            # 参数提取与类型转换
            converted_params, errors = _validate_and_convert_params(tool_name, params)

            if errors:
                # 参数校验失败 → 先尝试规则兜底提取参数
                logger.warning(f"LLM参数校验失败: {errors}，尝试规则兜底")
                rule_result = rule_based_tool_selection(question)
                if rule_result and rule_result["tool"] == tool_name:
                    converted_params = rule_result["params"]
                else:
                    return {
                        "type": "need_rag",
                        "answer": None,
                        "tool_used": tool_name,
                        "tool_result": None,
                        "fallback_reason": f"参数校验失败: {errors}"
                    }

            tool_result = await call_tool(db, tool_name, converted_params)

            # 工具执行失败 → 降级到 RAG
            if not tool_result.get("success"):
                logger.info(f"工具 {tool_name} 执行失败，降级到 RAG: {tool_result.get('error')}")
                return {
                    "type": "need_rag",
                    "answer": None,
                    "tool_used": tool_name,
                    "tool_result": tool_result,
                    "fallback_reason": f"工具执行失败: {tool_result.get('error')}"
                }

            final_answer = await generate_final_answer(question, tool_result)

            return {
                "type": "tool_call",
                "answer": final_answer,
                "tool_used": tool_name,
                "tool_result": tool_result
            }
        else:
            # LLM 判断无需工具，直接回答
            return {
                "type": "direct_answer",
                "answer": model_response,
                "tool_used": None,
                "tool_result": None
            }

    except Exception as e:
        logger.error(f"Function Calling 主流程异常，降级到规则兜底: {e}", exc_info=True)
        # LLM 调用异常 → 规则兜底
        rule_result = rule_based_tool_selection(question)
        if rule_result:
            tool_result = await call_tool(db, rule_result["tool"], rule_result["params"])
            answer = _fallback_format_result(question, tool_result)
            return {
                "type": "rule_fallback",
                "answer": answer,
                "tool_used": rule_result["tool"],
                "tool_result": tool_result,
                "fallback_reason": f"LLM调用异常: {str(e)}"
            }
        return {
            "type": "need_rag",
            "answer": None,
            "tool_used": None,
            "tool_result": None,
            "fallback_reason": f"LLM异常且规则未匹配: {str(e)}"
        }
