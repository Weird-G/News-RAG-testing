import os
import json
import re
import httpx
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "sk-OTMHClV6J89TE3t11oF6UqIptAa1gyBJzHiJZmu7lQeoD6FV")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.closeai-asia.com/v1")

SKILL_DEFINITIONS = {
    "news_summarize": {
        "name": "新闻摘要总结",
        "icon": "📝",
        "desc": "总结新闻核心内容",
        "prompt": """你是新闻摘要专家。请对以下新闻进行总结，严格按JSON格式输出：

新闻内容：
{news_text}

输出JSON格式：
{{
  "skill_name": "news_summarize",
  "status": "success",
  "result": {{
    "title": "提炼新闻标题",
    "core_event": "一句话概括核心事件（25-40字）",
    "key_points": ["要点1", "要点2", "要点3"],
    "emotion_tone": "新闻倾向：客观/正面/负面/中性",
    "source_hint": "推测新闻来源类型：官方媒体/自媒体/社交平台"
  }}
}}"""
    },
    "news_extract": {
        "name": "关键信息抽取",
        "icon": "🔍",
        "desc": "提取实体、时间、地点等",
        "prompt": """你是信息抽取专家。请从以下新闻中抽取关键信息，严格按JSON格式输出：

新闻内容：
{news_text}

输出JSON格式：
{{
  "skill_name": "news_extract",
  "status": "success",
  "result": {{
    "event_time": "新闻发生时间，无则填未知",
    "location": "涉及地点，无则填未知",
    "person_list": ["人物1", "人物2"],
    "organization_list": ["机构1", "机构2"],
    "core_object": "事件主体对象",
    "important_numbers": ["涉及数字、金额、数据"]
  }}
}}"""
    },
    "news_opinion": {
        "name": "观点立场提炼",
        "icon": "⚖️",
        "desc": "区分事实与观点",
        "prompt": """你是新闻分析专家。请从以下新闻中区分事实与观点，严格按JSON格式输出：

新闻内容：
{news_text}

输出JSON格式：
{{
  "skill_name": "news_opinion",
  "status": "success",
  "result": {{
    "fact_content": ["客观事实条目1", "客观事实条目2"],
    "opinion_content": ["媒体/当事人观点1", "观点2"],
    "conflict_view": ["存在争议的不同看法，没有则为空数组"]
  }}
}}"""
    },
    "news_risk_check": {
        "name": "风险提示",
        "icon": "⚠️",
        "desc": "识别谣言、夸大等",
        "prompt": """你是新闻风险分析专家。请检查以下新闻是否存在风险，严格按JSON格式输出：

新闻内容：
{news_text}

输出JSON格式：
{{
  "skill_name": "news_risk_check",
  "status": "success",
  "result": {{
    "risk_level": "low/middle/high",
    "risk_type": ["谣言嫌疑", "夸大宣传", "情绪煽动", "无风险"],
    "risk_reason": "简要说明判断依据，无风险填：未识别明显风险"
  }}
}}"""
    },
    "news_rewrite": {
        "name": "新闻改写",
        "icon": "✏️",
        "desc": "简讯/科普/标题党版",
        "prompt": """你是新闻改写专家。请将以下新闻改写为多种风格，严格按JSON格式输出：

新闻内容：
{news_text}

输出JSON格式：
{{
  "skill_name": "news_rewrite",
  "status": "success",
  "result": {{
    "short_bulletin": "简短简讯（适合推送，80字以内）",
    "popular_version": "通俗易懂版本，适合普通读者",
    "candidate_titles": ["备选标题1", "备选标题2", "备选标题3"]
  }}
}}"""
    },
    "news_question_gen": {
        "name": "关联提问生成",
        "icon": "❓",
        "desc": "生成追问问题",
        "prompt": """你是新闻追问专家。请根据以下新闻生成3-5个可以继续追问的问题，严格按JSON格式输出：

新闻内容：
{news_text}

输出JSON格式：
{{
  "skill_name": "news_question_gen",
  "status": "success",
  "result": {{
    "follow_questions": ["问题1", "问题2", "问题3", "问题4"]
  }}
}}"""
    },
    "news_compare": {
        "name": "多新闻对比",
        "icon": "🔀",
        "desc": "对比多篇报道差异",
        "prompt": """你是新闻对比分析专家。请对以下新闻进行对比分析，严格按JSON格式输出：

新闻A：
{news_text}

输出JSON格式：
{{
  "skill_name": "news_compare",
  "status": "success",
  "result": {{
    "same_points": ["报道相同点"],
    "diff_points": ["报道差异点"],
    "angle_summary": "总结各家报道立场差异"
  }}
}}"""
    }
}

SKILL_CHOICES = [
    {"skill": "news_summarize", "icon": "📝", "label": "总结新闻", "desc": "快速了解新闻核心"},
    {"skill": "news_extract", "icon": "🔍", "label": "提取信息", "desc": "时间/地点/人物"},
    {"skill": "news_opinion", "icon": "⚖️", "label": "观点分析", "desc": "事实vs观点"},
    {"skill": "news_risk_check", "icon": "⚠️", "label": "风险检测", "desc": "识别虚假/夸大"},
    {"skill": "news_rewrite", "icon": "✏️", "label": "改写新闻", "desc": "简讯/科普版"},
    {"skill": "news_question_gen", "icon": "❓", "label": "追问生成", "desc": "生成延伸问题"},
    {"skill": "news_compare", "icon": "🔀", "label": "对比分析", "desc": "多篇报道对比"},
]


def get_skill_choices(news_title: str) -> List[Dict[str, str]]:
    """根据新闻标题生成推荐的Skill选择列表"""
    return SKILL_CHOICES.copy()


async def call_llm(prompt: str) -> str:
    """调用大语言模型"""
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "你是专业的新闻处理助手。请严格按JSON格式输出，不要输出任何多余内容。"},
            {"role": "user", "content": prompt}
        ],
        "stream": False,
        "temperature": 0.3
    }

    endpoint = f"{OPENAI_BASE_URL}/chat/completions"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return content.strip()
    except Exception as e:
        logger.error(f"LLM调用失败: {e}")
        raise


def parse_llm_response(raw: str) -> Dict[str, Any]:
    """解析LLM返回的JSON，处理可能的markdown包裹"""
    cleaned = raw.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # 尝试从文本中提取JSON
        match = re.search(r'\{[\s\S]*\}', cleaned)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        logger.error(f"无法解析LLM返回: {raw[:200]}")
        return {
            "skill_name": "unknown",
            "status": "fail",
            "msg": f"AI返回格式错误，无法解析"
        }


async def execute_skill(skill_name: str, news_text: str) -> Dict[str, Any]:
    """执行单个Skill"""
    skill_def = SKILL_DEFINITIONS.get(skill_name)
    if not skill_def:
        return {
            "skill_name": skill_name,
            "status": "fail",
            "msg": f"未知Skill: {skill_name}"
        }

    prompt = skill_def["prompt"].format(news_text=news_text)

    try:
        raw_response = await call_llm(prompt)
        result = parse_llm_response(raw_response)

        if result.get("status") == "success":
            result["skill_name"] = skill_name
        else:
            result = {
                "skill_name": skill_name,
                "status": "fail",
                "msg": "处理失败"
            }

        return result
    except Exception as e:
        logger.error(f"Skill {skill_name} 执行失败: {e}")
        return {
            "skill_name": skill_name,
            "status": "fail",
            "msg": str(e)
        }


async def process_news_with_skills(
    news_text: str,
    news_title: str = "",
    skills: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    处理新闻的主入口：
    - 如果指定skills，按指定执行
    - 如果未指定，默认执行 summarize + extract + question_gen
    """
    if not news_text or len(news_text.strip()) < 10:
        return {
            "status": "fail",
            "msg": "新闻内容太短，无法分析",
            "news_title": news_title,
            "results": []
        }

    if skills is None:
        skills = ["news_summarize", "news_extract", "news_question_gen"]

    results = []
    for skill_name in skills:
        if skill_name in SKILL_DEFINITIONS:
            result = await execute_skill(skill_name, news_text)
            results.append(result)

    return {
        "status": "success",
        "news_title": news_title,
        "results": results
    }


def format_skill_result_as_text(skill_results: List[Dict[str, Any]]) -> str:
    """将Skill结果格式化为可读文本"""
    output_parts = []

    for result in skill_results:
        skill_name = result.get("skill_name", "unknown")
        status = result.get("status", "fail")

        if status != "success":
            output_parts.append(f"❌ {SKILL_DEFINITIONS.get(skill_name, {}).get('name', skill_name)}: 处理失败")
            continue

        skill_def = SKILL_DEFINITIONS.get(skill_name, {})
        skill_title = skill_def.get("name", skill_name)
        data = result.get("result", {})

        output_parts.append(f"## {skill_def.get('icon', '')} {skill_title}")

        if skill_name == "news_summarize":
            output_parts.append(f"**标题**: {data.get('title', '')}")
            output_parts.append(f"**核心事件**: {data.get('core_event', '')}")
            output_parts.append(f"**要点**:")
            for i, point in enumerate(data.get("key_points", []), 1):
                output_parts.append(f"  {i}. {point}")
            output_parts.append(f"**情感倾向**: {data.get('emotion_tone', '')}")
            output_parts.append(f"**来源推测**: {data.get('source_hint', '')}")

        elif skill_name == "news_extract":
            output_parts.append(f"**事件时间**: {data.get('event_time', '未知')}")
            output_parts.append(f"**地点**: {data.get('location', '未知')}")
            output_parts.append(f"**人物**: {', '.join(data.get('person_list', [])) or '无'}")
            output_parts.append(f"**机构**: {', '.join(data.get('organization_list', [])) or '无'}")
            output_parts.append(f"**事件主体**: {data.get('core_object', '未知')}")
            output_parts.append(f"**关键数据**: {', '.join(data.get('important_numbers', [])) or '无'}")

        elif skill_name == "news_opinion":
            output_parts.append("**客观事实**:")
            for item in data.get("fact_content", []):
                output_parts.append(f"  • {item}")
            output_parts.append("**观点主张**:")
            for item in data.get("opinion_content", []):
                output_parts.append(f"  • {item}")
            conflicts = data.get("conflict_view", [])
            if conflicts:
                output_parts.append("**争议焦点**:")
                for item in conflicts:
                    output_parts.append(f"  • {item}")

        elif skill_name == "news_risk_check":
            risk_level = data.get("risk_level", "unknown")
            level_map = {"low": "🟢 低风险", "middle": "🟡 中风险", "high": "🔴 高风险"}
            output_parts.append(f"**风险等级**: {level_map.get(risk_level, risk_level)}")
            output_parts.append(f"**风险类型**: {', '.join(data.get('risk_type', ['无风险']))}")
            output_parts.append(f"**判断依据**: {data.get('risk_reason', '')}")

        elif skill_name == "news_rewrite":
            output_parts.append(f"**简讯版**: {data.get('short_bulletin', '')}")
            output_parts.append(f"**通俗版**: {data.get('popular_version', '')}")
            output_parts.append("**备选标题**:")
            for i, title in enumerate(data.get("candidate_titles", []), 1):
                output_parts.append(f"  {i}. {title}")

        elif skill_name == "news_question_gen":
            output_parts.append("**建议追问**:")
            for i, q in enumerate(data.get("follow_questions", []), 1):
                output_parts.append(f"  {i}. {q}")

        elif skill_name == "news_compare":
            output_parts.append("**相同点**:")
            for item in data.get("same_points", []):
                output_parts.append(f"  • {item}")
            output_parts.append("**差异点**:")
            for item in data.get("diff_points", []):
                output_parts.append(f"  • {item}")
            output_parts.append(f"**角度总结**: {data.get('angle_summary', '')}")

        output_parts.append("")

    return "\n".join(output_parts)