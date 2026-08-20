import asyncio
import time
import aiohttp
import json

async def make_request(session, url, payload):
    start_time = time.time()
    try:
        async with session.post(url, json=payload) as response:
            await response.json()
            latency = (time.time() - start_time) * 1000
            return latency, response.status
    except Exception as e:
        latency = (time.time() - start_time) * 1000
        return latency, 0

async def run_load_test(url, payload, concurrency, requests_per_user):
    print(f"\n{'='*60}")
    print(f"并发数: {concurrency} | 每人请求数: {requests_per_user}")
    print(f"{'='*60}")
    
    all_latencies = []
    success_count = 0
    fail_count = 0
    
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as session:
        for batch in range(requests_per_user):
            tasks = [make_request(session, url, payload) for _ in range(concurrency)]
            results = await asyncio.gather(*tasks)
            
            for latency, status in results:
                all_latencies.append(latency)
                if status == 200:
                    success_count += 1
                else:
                    fail_count += 1
    
    if all_latencies:
        avg_latency = sum(all_latencies) / len(all_latencies)
        min_latency = min(all_latencies)
        max_latency = max(all_latencies)
        p95_latency = sorted(all_latencies)[int(len(all_latencies) * 0.95)]
        p99_latency = sorted(all_latencies)[int(len(all_latencies) * 0.99)]
        
        print(f"\n📊 性能测试结果:")
        print(f"总请求数: {success_count + fail_count}")
        print(f"成功数: {success_count} | 失败数: {fail_count}")
        print(f"成功率: {success_count / (success_count + fail_count) * 100:.2f}%")
        print(f"\n⏱️ 响应时间(ms):")
        print(f"  平均: {avg_latency:.2f}")
        print(f"  最小: {min_latency:.2f}")
        print(f"  最大: {max_latency:.2f}")
        print(f"  P95: {p95_latency:.2f}")
        print(f"  P99: {p99_latency:.2f}")
        print(f"\n✅ 达标: 平均响应时间 < 500ms" if avg_latency < 500 else f"\n❌ 未达标: 平均响应时间 >= 500ms")
    
    return all_latencies

async def main():
    url = "http://localhost:8001/api/ai/rag_chat"
    payload = {
        "question": "全球气候峰会的主要成果是什么？",
        "history": []
    }
    
    await run_load_test(url, payload, concurrency=10, requests_per_user=5)
    
    await run_load_test(url, payload, concurrency=50, requests_per_user=5)
    
    await run_load_test(url, payload, concurrency=100, requests_per_user=5)

if __name__ == "__main__":
    asyncio.run(main())