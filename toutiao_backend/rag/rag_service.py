import os
import logging
import httpx
from typing import List, Dict, Any
from vector_store.chroma_store import query as chroma_query, add_documents_async, get_collection_count, clear_collection
from vector_store.embedding import encode_single, aencode_single
from rag.text_splitter import split_text
from sqlalchemy.ext.asyncio import AsyncSession
from models.news import News

logger = logging.getLogger(__name__)

CHROMA_COLLECTION = "news_embeddings"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "sk-OTMHClV6J89TE3t11oF6UqIptAa1gyBJzHiJZmu7lQeoD6FV")
OPENAI_BASE_URL = os.environ.get("OPENAI_BASE_URL", "https://api.closeai-asia.com/v1")

SYNC_LIMIT = 0


def build_prompt(context: str, question: str, history_text: str = "") -> str:
    return f"""你是一个专业的新闻智能助手，请基于以下参考新闻内容回答用户问题。

重要规则：
1. 你的回答必须严格基于提供的参考新闻内容，禁止编造任何不在参考内容中的信息
2. 如果参考内容中没有相关信息，请明确回答"根据现有新闻资料，无法回答该问题"
3. 回答要简洁明了，直接针对用户问题
4. 不要提及"参考新闻"或"根据提供的内容"等字样
5. 如果有历史对话，请结合历史对话理解用户当前问题，保持回答的连贯性

参考新闻内容：
{context}

{history_text}

用户问题：
{question}"""


async def sync_news_to_vector_db(db: AsyncSession, limit: int = SYNC_LIMIT, chunk_size: int = 500, chunk_overlap: int = 50):
    """
    同步新闻到向量库
    chunk_size: 文本切片长度（A/B 测试用，默认 500）
    chunk_overlap: 切片重叠长度（默认 50）
    """
    logger.info(f"步骤1: 开始同步新闻到向量库 (chunk_size={chunk_size}, chunk_overlap={chunk_overlap})...")
    
    stmt = News.__table__.select()
    result = await db.execute(stmt)
    news_list = result.fetchall()
    
    logger.info(f"步骤2: 查询到 {len(news_list)} 条新闻")
    
    if limit > 0:
        news_list = news_list[:limit]
        logger.info(f"步骤2.1: 测试模式，仅处理前 {limit} 条新闻")
    
    documents = []
    metadatas = []
    ids = []
    
    for news in news_list:
        text = f"标题：{news.title}\n简介：{news.description or ''}\n内容：{news.content}"
        chunks = split_text(text, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        
        for i, chunk in enumerate(chunks):
            doc_id = f"news_{news.id}_chunk_{i}"
            documents.append(chunk)
            metadatas.append({
                "news_id": news.id,
                "title": news.title,
                "author": news.author,
                "category_id": news.category_id,
                "chunk_index": i
            })
            ids.append(doc_id)
    
    if not documents:
        logger.info("步骤3: 没有需要同步的新闻片段")
        return 0
    
    logger.info(f"步骤3: 共生成 {len(documents)} 个新闻片段")
    
    logger.info("步骤4: 清空旧向量数据...")
    clear_collection(CHROMA_COLLECTION)
    
    logger.info("步骤5: 开始向量化并写入向量库...")
    await add_documents_async(CHROMA_COLLECTION, documents, metadatas, ids)
    
    logger.info(f"步骤6: 成功同步 {len(documents)} 个新闻片段到向量库")
    return len(documents)


async def retrieve_relevant_news(question: str, n_results: int = 3, min_distance: float = 0.7) -> List[Dict[str, Any]]:
    """
    检索相关新闻。
    min_distance: cosine distance 阈值 (0=完全相同, 2=完全无关)。
    超过阈值的结果会被过滤掉。
    """
    try:
        query_embedding = await aencode_single(question)
    except Exception as e:
        logger.error(f"向量化失败: {e}")
        return []
    
    try:
        results = chroma_query(CHROMA_COLLECTION, [query_embedding], n_results)
    except Exception as e:
        logger.error(f"向量检索失败: {e}")
        return []
    
    documents_list = results.get("documents", [])
    metadatas_list = results.get("metadatas", [])
    distances_list = results.get("distances", [])
    
    if not documents_list or not metadatas_list:
        return []
    
    documents = documents_list[0] if isinstance(documents_list[0], list) else []
    metadatas = metadatas_list[0] if isinstance(metadatas_list[0], list) else []
    distances = distances_list[0] if distances_list and isinstance(distances_list[0], list) else []
    
    if not documents or not metadatas:
        return []
    
    news_snippets = []
    seen_titles = set()
    
    for i, (document, metadata) in enumerate(zip(documents, metadatas)):
        title = metadata.get("title", "")
        distance = distances[i] if i < len(distances) else 1.0
        
        # 过滤掉相似度太低的结果
        if distance > min_distance:
            logger.info(f"跳过低相似度结果: title={title}, distance={distance:.4f}")
            continue
            
        if title not in seen_titles:
            seen_titles.add(title)
            news_snippets.append({
                "title": title,
                "snippet": document[:200] + "..." if len(document) > 200 else document,
                "news_id": metadata.get("news_id"),
                "distance": distance
            })
    
    logger.info(f"检索到 {len(news_snippets)} 条相关新闻 (min_distance={min_distance})")
    return news_snippets


async def generate_answer(question: str, context: str, history_text: str = "") -> str:
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY 未配置")
    
    prompt = build_prompt(context, question, history_text)
    
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "stream": False,
        "temperature": 0.3
    }
    
    endpoint = f"{OPENAI_BASE_URL}/chat/completions"
    
    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(endpoint, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
        
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        return content.strip()


async def rag_chat(question: str, history: List[Dict[str, str]] = None) -> Dict[str, Any]:
    try:
        # 构建带上下文的检索查询
        search_query = question
        if history and isinstance(history, list) and len(history) > 0:
            context_queries = []
            for msg in history:
                if msg.get("role") == "user":
                    context_queries.append(msg.get("content", ""))
            if context_queries:
                search_query = " ".join(context_queries[-2:] + [question])
        
        relevant_news = await retrieve_relevant_news(search_query, n_results=3)
        
        if not relevant_news:
            return {
                "answer": "向量库中暂无新闻数据，请先执行同步操作。",
                "reference_news": []
            }
        
        context = "\n\n".join([f"【{news['title']}】\n{news['snippet']}" for news in relevant_news])
        
        history_text = ""
        if history and isinstance(history, list) and len(history) > 0:
            history_text = "\n\n历史对话记录：\n"
            for msg in history:
                role = "用户" if msg.get("role") == "user" else "助手"
                history_text += f"{role}：{msg.get('content', '')}\n"
        
        answer = await generate_answer(question, context, history_text)
        
        return {
            "answer": answer,
            "reference_news": [news["title"] for news in relevant_news],
            "reference_news_ids": [news.get("news_id") for news in relevant_news if news.get("news_id")]
        }
    except Exception as e:
        logger.error(f"RAG问答失败: {type(e).__name__}: {repr(e)}")
        return {
            "answer": f"问答失败: {type(e).__name__}: {repr(e)}",
            "reference_news": [],
            "reference_news_ids": []
        }


async def direct_chat(question: str, history: List[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    直接对话（不依赖RAG），用于闲聊/通用问答场景。
    当向量库找不到相关新闻时回退使用。
    """
    if not OPENAI_API_KEY:
        return {"answer": "API Key 未配置", "reference_news": [], "is_rag": False}

    messages = [
        {"role": "system", "content": "你是一个友好的AI助手，可以和用户闲聊、回答各种问题。回答要简洁有趣，语气自然。"},
    ]
    if history and isinstance(history, list) and len(history) > 0:
        for msg in history:
            messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
    
    messages.append({"role": "user", "content": question})

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "gpt-4o-mini",
        "messages": messages,
        "stream": False,
        "temperature": 0.7
    }

    endpoint = f"{OPENAI_BASE_URL}/chat/completions"

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return {
                "answer": content.strip() if content else "抱歉，我暂时无法回答这个问题。",
                "reference_news": [],
                "is_rag": False
            }
    except Exception as e:
        logger.error(f"直接对话失败: {e}")
        return {
            "answer": f"对话失败: {str(e)}",
            "reference_news": [],
            "is_rag": False
        }


async def unified_chat(question: str, history: List[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    统一聊天接口：
    1. 先尝试 RAG 检索新闻
    2. 如果找到相关新闻且能生成有意义的回答，使用 RAG 回答并附上参考来源
    3. 否则回退到普通对话模式
    """
    try:
        search_query = question
        if history and isinstance(history, list) and len(history) > 0:
            context_queries = []
            for msg in history:
                if msg.get("role") == "user":
                    context_queries.append(msg.get("content", ""))
            if context_queries:
                search_query = " ".join(context_queries[-2:] + [question])

        # 使用距离阈值(0.5)过滤不相关新闻
        # 相关新闻 distance ~0.39, 不相关新闻 distance >0.9
        relevant_news = await retrieve_relevant_news(search_query, n_results=3, min_distance=0.5)

        if relevant_news and len(relevant_news) >= 1:
            context = "\n\n".join([f"【{news['title']}】\n{news['snippet']}" for news in relevant_news])

            history_text = ""
            if history and isinstance(history, list) and len(history) > 0:
                history_text = "\n\n历史对话记录：\n"
                for msg in history:
                    role = "用户" if msg.get("role") == "user" else "助手"
                    history_text += f"{role}：{msg.get('content', '')}\n"

            answer = await generate_answer(question, context, history_text)

            # 检查RAG是否生成了有意义的回答
            no_answer_indicators = [
                "无法回答", "未找到", "没有相关", "没有找到",
                "无法提供", "不了解", "抱歉", "暂无相关", "根据现有新闻资料"
            ]
            is_empty_answer = not answer or any(ind in answer for ind in no_answer_indicators)

            if is_empty_answer:
                logger.info("RAG未生成有意义回答，回退到普通对话模式")
                result = await direct_chat(question, history)
                return result

            logger.info(f"RAG模式：找到 {len(relevant_news)} 条相关新闻，回答成功")
            return {
                "answer": answer,
                "reference_news": [news["title"] for news in relevant_news],
                "is_rag": True
            }
        else:
            logger.info("普通对话模式：未找到相关新闻，使用通用对话")
            result = await direct_chat(question, history)
            return result
    except Exception as e:
        logger.error(f"统一聊天失败，回退到普通对话: {e}")
        result = await direct_chat(question, history)
        return result