"""
rag_evaluator.py - RAG 三维度评测主脚本

评测维度：
1. Top-K 召回率（Top1/Top3/Top5）：RAG 检索命中的 news_id 与人工标注 expected_news_ids 的重叠率
2. Rouge-L 文本重叠度：LLM 生成答案 vs 数据库 news.description 参考答案的最长公共子序列 F1
3. 向量语义相似度：query embedding vs answer embedding 的 cosine 相似度

用法：
    python scripts/rag_evaluation/rag_evaluator.py              # 全量120条
    python scripts/rag_evaluation/rag_evaluator.py --limit 10   # 只跑前10条快速验证
    python scripts/rag_evaluation/rag_evaluator.py --category 事实查询  # 只跑某分类
"""

import asyncio
import json
import sys
import os
import logging
import argparse
from pathlib import Path
from typing import List, Dict, Any

# 绕过系统级 HTTP 代理（httpx trust_env 会读 Windows 代理导致 SSL 握手失败）
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

# 添加项目根目录到 sys.path（脚本在 scripts/rag_evaluation/，向上两级到 toutiao_backend）
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
# 加入脚本所在目录，便于 from rouge_l import rouge_l（无需 __init__.py）
sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
# 抑制 SQLAlchemy echo 日志（db_conf 默认 echo=True 会刷屏）
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logging.getLogger("aiomysql").setLevel(logging.WARNING)

from config.db_conf import AsyncSessionLocal
from models.news import News
from rag.rag_service import rag_chat
from vector_store.embedding import aencode_single
from rouge_l import rouge_l

# 配置应用层日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

TEST_CASES_FILE = Path(__file__).parent / "rag_test_cases_120.json"


async def load_test_cases() -> List[Dict[str, Any]]:
    """加载测试集"""
    with open(TEST_CASES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["test_cases"]


async def get_golden_answer(news_ids: List[int]) -> str:
    """
    从数据库查 expected_news_ids 对应的新闻 description 作为参考答案
    若 description 为空，用 content 前 200 字兜底
    """
    if not news_ids:
        return ""
    async with AsyncSessionLocal() as db:
        stmt = select(News.id, News.title, News.description, News.content).where(News.id.in_(news_ids))
        result = await db.execute(stmt)
        rows = result.fetchall()

    parts = []
    for row in rows:
        if row.description:
            parts.append(f"【{row.title}】{row.description}")
        elif row.content:
            parts.append(f"【{row.title}】{row.content[:200]}")
    return "\n".join(parts)


def compute_topk_recall(retrieved_ids: List[int], expected_ids: List[int], k: int) -> float:
    """
    Top-K 召回率：retrieved 前 K 个里命中 expected 的比例
    recall = |retrieved[:k] ∩ expected| / |expected|
    """
    if not expected_ids:
        return 0.0
    topk = retrieved_ids[:k]
    hits = len(set(topk) & set(expected_ids))
    return hits / len(set(expected_ids))


def compute_precision_at_k(retrieved_ids: List[int], expected_ids: List[int], k: int) -> float:
    """Top-K 精确率：retrieved 前 K 个里命中的比例"""
    if not retrieved_ids[:k]:
        return 0.0
    topk = retrieved_ids[:k]
    hits = len(set(topk) & set(expected_ids))
    return hits / len(topk)


async def compute_vector_similarity(text1: str, text2: str) -> float:
    """向量语义相似度：cosine"""
    if not text1 or not text2:
        return 0.0
    try:
        import numpy as np
        emb1 = await aencode_single(text1)
        emb2 = await aencode_single(text2)
        if not emb1 or not emb2:
            return 0.0
        v1 = np.array(emb1)
        v2 = np.array(emb2)
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        cosine = float(np.dot(v1, v2) / (norm1 * norm2))
        return cosine
    except Exception as e:
        logger.warning(f"向量相似度计算失败: {e}")
        return 0.0


async def evaluate_single(test_case: Dict[str, Any]) -> Dict[str, Any]:
    """评测单条 Query，返回三维度指标"""
    question = test_case["question"]
    expected_ids = test_case["expected_news_ids"]

    # 维度1前置：调用 RAG 拿 answer 和 retrieved_ids
    try:
        rag_result = await rag_chat(question)
        answer = rag_result.get("answer", "")
        retrieved_ids = rag_result.get("reference_news_ids", []) or []
    except Exception as e:
        logger.error(f"RAG 调用失败 {test_case['id']}: {e}")
        answer = ""
        retrieved_ids = []

    # 维度1：Top-K 召回率
    top1_recall = compute_topk_recall(retrieved_ids, expected_ids, 1)
    top3_recall = compute_topk_recall(retrieved_ids, expected_ids, 3)
    top5_recall = compute_topk_recall(retrieved_ids, expected_ids, 5)
    top3_precision = compute_precision_at_k(retrieved_ids, expected_ids, 3)

    # 维度2前置：拿 golden_answer
    golden_answer = await get_golden_answer(expected_ids)

    # 维度2：Rouge-L 文本重叠度
    if answer and golden_answer:
        rouge_result = rouge_l(answer, golden_answer)
    else:
        rouge_result = {"f1": 0.0, "precision": 0.0, "recall": 0.0, "lcs": 0}

    # 维度3：向量语义相似度
    vector_sim = await compute_vector_similarity(question, answer)

    return {
        "id": test_case["id"],
        "category": test_case["category"],
        "question": question,
        "expected_news_ids": expected_ids,
        "retrieved_ids": retrieved_ids,
        "answer_preview": (answer or "")[:200],
        "golden_answer_preview": (golden_answer or "")[:200],
        # 维度1
        "top1_recall": round(top1_recall, 4),
        "top3_recall": round(top3_recall, 4),
        "top5_recall": round(top5_recall, 4),
        "top3_precision": round(top3_precision, 4),
        # 维度2
        "rouge_l_f1": round(rouge_result["f1"], 4),
        "rouge_l_precision": round(rouge_result["precision"], 4),
        "rouge_l_recall": round(rouge_result["recall"], 4),
        # 维度3
        "vector_similarity": round(vector_sim, 4)
    }


def print_report(all_results: List[Dict[str, Any]]):
    """打印评测报告"""
    print("\n" + "=" * 90)
    print("RAG 三维度评测报告")
    print("=" * 90)

    # 按分类聚合
    category_stats = {}
    for r in all_results:
        cat = r["category"]
        if cat not in category_stats:
            category_stats[cat] = {
                "count": 0, "top1": [], "top3": [], "top5": [],
                "rouge_f1": [], "vector_sim": []
            }
        s = category_stats[cat]
        s["count"] += 1
        s["top1"].append(r["top1_recall"])
        s["top3"].append(r["top3_recall"])
        s["top5"].append(r["top5_recall"])
        s["rouge_f1"].append(r["rouge_l_f1"])
        s["vector_sim"].append(r["vector_similarity"])

    # 按分类输出
    print(f"\n{'分类':<12} {'条数':>4} {'Top1':>8} {'Top3':>8} {'Top5':>8} {'RougeF1':>10} {'向量相似':>10}")
    print("-" * 90)

    for cat, s in category_stats.items():
        top1_avg = sum(s["top1"]) / len(s["top1"]) * 100
        top3_avg = sum(s["top3"]) / len(s["top3"]) * 100
        top5_avg = sum(s["top5"]) / len(s["top5"]) * 100
        rouge_avg = sum(s["rouge_f1"]) / len(s["rouge_f1"])
        vec_avg = sum(s["vector_sim"]) / len(s["vector_sim"])
        print(f"{cat:<12} {s['count']:>4} {top1_avg:>7.1f}% {top3_avg:>7.1f}% {top5_avg:>7.1f}% {rouge_avg:>10.4f} {vec_avg:>10.4f}")

    # 总体
    all_top1 = [r["top1_recall"] for r in all_results]
    all_top3 = [r["top3_recall"] for r in all_results]
    all_top5 = [r["top5_recall"] for r in all_results]
    all_rouge = [r["rouge_l_f1"] for r in all_results]
    all_vec = [r["vector_similarity"] for r in all_results]

    print("-" * 90)
    print(f"{'总体':<12} {len(all_results):>4} "
          f"{sum(all_top1)/len(all_top1)*100:>7.1f}% "
          f"{sum(all_top3)/len(all_top3)*100:>7.1f}% "
          f"{sum(all_top5)/len(all_top5)*100:>7.1f}% "
          f"{sum(all_rouge)/len(all_rouge):>10.4f} "
          f"{sum(all_vec)/len(all_vec):>10.4f}")

    # 问答准确率（综合判定：Top3召回>0 且 Rouge-L F1>0.1 且 向量相似>0.5）
    qa_accuracy = sum(
        1 for r in all_results
        if r["top3_recall"] > 0 and r["rouge_l_f1"] > 0.1 and r["vector_similarity"] > 0.5
    ) / len(all_results) * 100
    print(f"\n问答准确率（Top3>0 且 Rouge>0.1 且 向量相似>0.5）: {qa_accuracy:.1f}%")


def save_results(all_results: List[Dict[str, Any]]):
    """保存详细结果到 JSON"""
    all_top1 = [r["top1_recall"] for r in all_results]
    all_top3 = [r["top3_recall"] for r in all_results]
    all_top5 = [r["top5_recall"] for r in all_results]
    all_rouge = [r["rouge_l_f1"] for r in all_results]
    all_vec = [r["vector_similarity"] for r in all_results]
    qa_accuracy = sum(
        1 for r in all_results
        if r["top3_recall"] > 0 and r["rouge_l_f1"] > 0.1 and r["vector_similarity"] > 0.5
    ) / len(all_results)

    # 按分类聚合
    by_category = {}
    for r in all_results:
        cat = r["category"]
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(r)

    category_summary = {}
    for cat, items in by_category.items():
        category_summary[cat] = {
            "count": len(items),
            "top1_recall": sum(r["top1_recall"] for r in items) / len(items),
            "top3_recall": sum(r["top3_recall"] for r in items) / len(items),
            "top5_recall": sum(r["top5_recall"] for r in items) / len(items),
            "rouge_l_f1": sum(r["rouge_l_f1"] for r in items) / len(items),
            "vector_similarity": sum(r["vector_similarity"] for r in items) / len(items),
        }

    output = {
        "summary": {
            "total": len(all_results),
            "top1_recall": sum(all_top1) / len(all_top1),
            "top3_recall": sum(all_top3) / len(all_top3),
            "top5_recall": sum(all_top5) / len(all_top5),
            "rouge_l_f1": sum(all_rouge) / len(all_rouge),
            "vector_similarity": sum(all_vec) / len(all_vec),
            "qa_accuracy": qa_accuracy
        },
        "by_category": category_summary,
        "details": all_results
    }

    output_file = Path(__file__).parent / "rag_eval_results.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\n详细结果已保存：{output_file}")
    return output_file


async def main():
    parser = argparse.ArgumentParser(description="RAG 三维度评测")
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 条（0=全量）")
    parser.add_argument("--category", type=str, default="", help="只跑某分类（如 事实查询）")
    args = parser.parse_args()

    print("=" * 90)
    print("RAG 三维度评测脚本")
    print("维度1: Top-K 召回率  |  维度2: Rouge-L 文本重叠度  |  维度3: 向量语义相似度")
    print("=" * 90)

    test_cases = await load_test_cases()
    print(f"\n加载测试集：{len(test_cases)} 条")

    # 过滤
    if args.category:
        test_cases = [tc for tc in test_cases if tc["category"] == args.category]
        print(f"按分类过滤 '{args.category}'：剩余 {len(test_cases)} 条")
    if args.limit > 0:
        test_cases = test_cases[:args.limit]
        print(f"--limit {args.limit}：只跑前 {len(test_cases)} 条")

    all_results = []
    for i, tc in enumerate(test_cases, 1):
        print(f"\r[{i}/{len(test_cases)}] 评测中: {tc['id']} ({tc['category']})", end="", flush=True)
        try:
            result = await evaluate_single(tc)
            all_results.append(result)
        except Exception as e:
            logger.error(f"评测异常 {tc['id']}: {e}", exc_info=True)
            all_results.append({
                "id": tc["id"], "category": tc["category"], "question": tc["question"],
                "error": str(e), "top1_recall": 0, "top3_recall": 0, "top5_recall": 0,
                "rouge_l_f1": 0, "vector_similarity": 0
            })

    print()  # 换行
    print_report(all_results)
    save_results(all_results)


if __name__ == "__main__":
    asyncio.run(main())
