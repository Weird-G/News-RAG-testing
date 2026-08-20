import asyncio
from rag.rag_service import retrieve_relevant_news

async def debug():
    q = "社区时间银行养老是什么模式？"
    results = await retrieve_relevant_news(q, n_results=3)
    print(f"\n查询: {q}")
    print(f"返回 {len(results)} 条:")
    for i, r in enumerate(results):
        print(f"  [{i+1}] 标题={r['title']}")
        print(f"      摘要={r['snippet'][:100]}")

    q2 = "中国消费复苏的情况怎么样？"
    results2 = await retrieve_relevant_news(q2, n_results=3)
    print(f"\n查询: {q2}")
    print(f"返回 {len(results2)} 条:")
    for i, r in enumerate(results2):
        print(f"  [{i+1}] 标题={r['title']}")
        print(f"      摘要={r['snippet'][:100]}")

asyncio.run(debug())