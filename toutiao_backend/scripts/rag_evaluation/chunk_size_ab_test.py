"""
chunk_size_ab_test.py - chunk_size A/B 对比测试

扫描 4 个 chunk_size 档位（300/500/800/1000），每个档位：
1. 清空 Chroma collection
2. 用该 chunk_size 重新切分+向量化 403 条新闻
3. 跑 RAG 评测（Top-K 召回率 + Rouge-L + 向量相似度）
4. 记录该档位的 Top3 recall 和问答准确率

最终生成对比报告，定位最优 chunk_size，回填简历数字。

用法：
    python scripts/rag_evaluation/chunk_size_ab_test.py              # 全量120条×4档
    python scripts/rag_evaluation/chunk_size_ab_test.py --limit 5   # 每档只跑5条快速验证
"""

import asyncio
import json
import sys
import os
import logging
import argparse
from pathlib import Path
from typing import List, Dict, Any

# 绕过系统级 HTTP 代理
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import select
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("aiomysql").setLevel(logging.WARNING)

from config.db_conf import AsyncSessionLocal
from rag.rag_service import sync_news_to_vector_db, CHROMA_COLLECTION
from vector_store.chroma_store import clear_collection, get_collection_count
from rag_evaluator import load_test_cases, evaluate_single

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

# A/B 测试档位（简历写 1000→500，这里扫描 4 档覆盖更广）
CHUNK_SIZES = [300, 500, 800, 1000]


async def run_single_chunk_size(chunk_size: int, test_cases: List[Dict[str, Any]]) -> Dict[str, Any]:
    """跑单个 chunk_size 档位"""
    print(f"\n{'=' * 70}")
    print(f"chunk_size = {chunk_size}")
    print(f"{'=' * 70}")

    # 步骤1：清空 Chroma collection
    print(f"[1/3] 清空 Chroma collection ({CHROMA_COLLECTION})...")
    clear_collection(CHROMA_COLLECTION)
    before_count = get_collection_count(CHROMA_COLLECTION)
    print(f"  清空后 count = {before_count}")

    # 步骤2：用新 chunk_size 重新同步
    print(f"[2/3] 用 chunk_size={chunk_size} 重新切分并同步新闻...")
    async with AsyncSessionLocal() as db:
        chunk_count = await sync_news_to_vector_db(db, chunk_size=chunk_size, chunk_overlap=50)
    after_count = get_collection_count(CHROMA_COLLECTION)
    print(f"  同步完成，Chroma count = {after_count}")

    # 步骤3：跑评测
    print(f"[3/3] 跑 RAG 评测（{len(test_cases)} 条 Query）...")
    results = []
    for i, tc in enumerate(test_cases, 1):
        print(f"\r  [{i}/{len(test_cases)}] {tc['id']} ({tc['category']})", end="", flush=True)
        try:
            result = await evaluate_single(tc)
            results.append(result)
        except Exception as e:
            logger.error(f"评测异常 {tc['id']}: {e}")
            results.append({
                "id": tc["id"], "category": tc["category"], "question": tc["question"],
                "error": str(e), "top1_recall": 0, "top3_recall": 0, "top5_recall": 0,
                "rouge_l_f1": 0, "vector_similarity": 0
            })
    print()  # 换行

    # 汇总指标
    top1_avg = sum(r["top1_recall"] for r in results) / len(results)
    top3_avg = sum(r["top3_recall"] for r in results) / len(results)
    top5_avg = sum(r["top5_recall"] for r in results) / len(results)
    rouge_avg = sum(r["rouge_l_f1"] for r in results) / len(results)
    vec_avg = sum(r["vector_similarity"] for r in results) / len(results)
    # 问答准确率：Top3>0 且 Rouge>0.1 且 向量相似>0.5
    qa_accuracy = sum(
        1 for r in results
        if r["top3_recall"] > 0 and r["rouge_l_f1"] > 0.1 and r["vector_similarity"] > 0.5
    ) / len(results)

    # 按分类汇总
    by_category = {}
    for r in results:
        cat = r["category"]
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(r)

    category_summary = {}
    for cat, items in by_category.items():
        category_summary[cat] = {
            "count": len(items),
            "top3_recall": sum(r["top3_recall"] for r in items) / len(items),
            "rouge_l_f1": sum(r["rouge_l_f1"] for r in items) / len(items),
        }

    print(f"\n--- chunk_size={chunk_size} 结果 ---")
    print(f"  Top1 召回率: {top1_avg*100:.1f}%")
    print(f"  Top3 召回率: {top3_avg*100:.1f}%")
    print(f"  Top5 召回率: {top5_avg*100:.1f}%")
    print(f"  Rouge-L F1: {rouge_avg:.4f}")
    print(f"  向量相似度: {vec_avg:.4f}")
    print(f"  问答准确率: {qa_accuracy*100:.1f}%")

    return {
        "chunk_size": chunk_size,
        "chroma_count": after_count,
        "summary": {
            "top1_recall": top1_avg,
            "top3_recall": top3_avg,
            "top5_recall": top5_avg,
            "rouge_l_f1": rouge_avg,
            "vector_similarity": vec_avg,
            "qa_accuracy": qa_accuracy
        },
        "by_category": category_summary,
        "details": results
    }


def print_comparison_report(all_results: List[Dict[str, Any]]):
    """打印 4 档对比报告"""
    print("\n" + "=" * 90)
    print("chunk_size A/B 对比报告")
    print("=" * 90)

    print(f"\n{'chunk_size':>12} {'Chroma数':>10} {'Top1':>8} {'Top3':>8} {'Top5':>8} {'RougeF1':>10} {'向量相似':>10} {'问答准确':>10}")
    print("-" * 90)

    for r in all_results:
        s = r["summary"]
        print(f"{r['chunk_size']:>12} {r['chroma_count']:>10} "
              f"{s['top1_recall']*100:>7.1f}% {s['top3_recall']*100:>7.1f}% {s['top5_recall']*100:>7.1f}% "
              f"{s['rouge_l_f1']:>10.4f} {s['vector_similarity']:>10.4f} {s['qa_accuracy']*100:>9.1f}%")

    # 找最优档位
    best_top3 = max(all_results, key=lambda x: x["summary"]["top3_recall"])
    best_qa = max(all_results, key=lambda x: x["summary"]["qa_accuracy"])
    print("-" * 90)
    print(f"\nTop3 召回率最优: chunk_size={best_top3['chunk_size']} ({best_top3['summary']['top3_recall']*100:.1f}%)")
    print(f"问答准确率最优: chunk_size={best_qa['chunk_size']} ({best_qa['summary']['qa_accuracy']*100:.1f}%)")

    # 增量对比（1000 vs 500，对应简历描述）
    r1000 = next((r for r in all_results if r["chunk_size"] == 1000), None)
    r500 = next((r for r in all_results if r["chunk_size"] == 500), None)
    if r1000 and r500:
        top3_improvement = (r500["summary"]["top3_recall"] - r1000["summary"]["top3_recall"]) * 100
        qa_improvement = (r500["summary"]["qa_accuracy"] - r1000["summary"]["qa_accuracy"]) * 100
        print(f"\n=== 简历数字回填（1000 → 500）===")
        print(f"  Top3 召回率: {r1000['summary']['top3_recall']*100:.1f}% → {r500['summary']['top3_recall']*100:.1f}% (提升 {top3_improvement:+.1f} 个百分点)")
        print(f"  问答准确率: {r1000['summary']['qa_accuracy']*100:.1f}% → {r500['summary']['qa_accuracy']*100:.1f}% (提升 {qa_improvement*100:+.1f}%)")


def save_comparison(all_results: List[Dict[str, Any]]):
    """保存对比结果"""
    output_file = Path(__file__).parent / "chunk_size_ab_results.json"
    # details 太长，单独存
    output = {
        "comparison": [{
            "chunk_size": r["chunk_size"],
            "chroma_count": r["chroma_count"],
            "summary": r["summary"],
            "by_category": r["by_category"]
        } for r in all_results],
        "details_by_chunk_size": {str(r["chunk_size"]): r["details"] for r in all_results}
    }
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n对比结果已保存：{output_file}")


async def main():
    parser = argparse.ArgumentParser(description="chunk_size A/B 对比测试")
    parser.add_argument("--limit", type=int, default=0, help="每档只跑前 N 条（0=全量120）")
    parser.add_argument("--sizes", type=str, default="", help="自定义档位，逗号分隔（如 300,500）")
    args = parser.parse_args()

    print("=" * 90)
    print("chunk_size A/B 对比测试")
    print("维度: Top-K 召回率 + Rouge-L + 向量相似度 + 问答准确率")
    print("=" * 90)

    chunk_sizes = [int(s) for s in args.sizes.split(",")] if args.sizes else CHUNK_SIZES
    print(f"\n扫描档位: {chunk_sizes}")

    test_cases = await load_test_cases()
    if args.limit > 0:
        test_cases = test_cases[:args.limit]
    print(f"每档评测 Query 数: {len(test_cases)}")

    all_results = []
    for cs in chunk_sizes:
        result = await run_single_chunk_size(cs, test_cases)
        all_results.append(result)

    print_comparison_report(all_results)
    save_comparison(all_results)


if __name__ == "__main__":
    asyncio.run(main())
