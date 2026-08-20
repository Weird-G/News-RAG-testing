import requests
import json

# 测试多轮对话
history = []

# 第一轮
r1 = requests.post('http://localhost:8000/api/ai/rag_chat', json={'question': '社区时间银行养老是什么？', 'history': []})
if r1.status_code == 200:
    d1 = r1.json()
    print(f'第一轮问题: 社区时间银行养老是什么？')
    print(f'第一轮回答: {d1["answer"]}')
    print(f'第一轮参考: {d1["reference_news"]}')
    history.append({"role": "assistant", "content": d1["answer"]})
    print()

# 第二轮
r2 = requests.post('http://localhost:8000/api/ai/rag_chat', json={'question': '这个模式对老年人有什么好处？', 'history': history})
if r2.status_code == 200:
    d2 = r2.json()
    print(f'第二轮问题: 这个模式对老年人有什么好处？')
    print(f'第二轮回答: {d2["answer"]}')
    print(f'第二轮参考: {d2["reference_news"]}')
    
    # 检查关键词覆盖
    expected = ["养老", "社区时间银行", "好处"]
    for kw in expected:
        found = kw in d2["answer"]
        print(f'  关键词 "{kw}": {"✅ 找到" if found else "❌ 未找到"}')