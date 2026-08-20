import requests
import json

test_queries = [
    '社区时间银行养老',
    '中国乒乓世乒赛',
    '消费复苏',
    '谷歌AI艺术',
    '科技创新',
]

for query in test_queries:
    r = requests.post('http://localhost:8000/api/ai/rag_chat', json={'question': query, 'history': []})
    if r.status_code == 200:
        data = r.json()
        answer = data.get('answer', '')[:100]
        refs = data.get('reference_news', [])[:2]
        print(f'查询: {query}')
        print(f'回答: {answer}...')
        print(f'参考: {refs}')
        print('-' * 50)
    else:
        print(f'查询 {query} 失败: {r.status_code} - {r.text}')
        print('-' * 50)