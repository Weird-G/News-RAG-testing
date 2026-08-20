﻿﻿﻿﻿﻿﻿﻿﻿import asyncio
import logging
import json
from typing import List, Dict, Any

from rag.rag_service import rag_chat, retrieve_relevant_news
from vector_store.chroma_store import query as chroma_query, get_collection
from vector_store.embedding import aencode_single

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


class RAGQualityTester:
    """RAG质量评测器"""

    def __init__(self):
        self.test_cases = [
            {
                "id": "TC001",
                "question": "社区时间银行养老是什么模式？",
                "expected_keywords": ["社区", "时间银行", "养老"],
                "category": "事实查询"
            },
            {
                "id": "TC002",
                "question": "中国乒乓球队在世乒赛上取得了什么成绩？",
                "expected_keywords": ["中国", "乒乓球", "世乒赛", "冠军"],
                "category": "事实查询"
            },
            {
                "id": "TC003",
                "question": "中国消费复苏的情况怎么样？",
                "expected_keywords": ["中国", "消费", "复苏"],
                "category": "趋势分析"
            },
            {
                "id": "TC004",
                "question": "谷歌发布的AI艺术创作工具有什么功能？",
                "expected_keywords": ["谷歌", "AI", "艺术", "创作"],
                "category": "应用场景"
            },
            {
                "id": "TC005",
                "question": "中国在科技创新方面有哪些投入和进展？",
                "expected_keywords": ["中国", "科技", "创新", "投入"],
                "category": "汇总查询"
            }
        ]

        self.multiturn_test_cases = [
            {
                "id": "MT001",
                "conversations": [
                    {"role": "user", "content": "NBA球星杜兰特转会去了哪个队？"},
                    {"role": "user", "content": "他加盟之后NBA还有什么重要赛事或活动？"}
                ],
                "expected_context": ["NBA", "杜兰特", "篮网"]
            }
        ]

    async def test_top_k_recall(self, k_values: List[int] = [1, 3, 5]) -> Dict[str, Any]:
        """测试Chroma Top-K召回准确率"""
        logger.info("\n" + "=" * 60)
        logger.info("测试1: Top-K召回准确率")
        logger.info("=" * 60)

        results = {}
        for k in k_values:
            correct_count = 0
            total_count = 0

            for test_case in self.test_cases:
                relevant_news = await retrieve_relevant_news(test_case["question"], n_results=k)
                total_count += 1

                found_keywords = set()
                for news in relevant_news:
                    for kw in test_case["expected_keywords"]:
                        if kw in news["title"] or kw in news["snippet"]:
                            found_keywords.add(kw)

                recall_rate = len(found_keywords) / len(test_case["expected_keywords"])
                if recall_rate >= 0.6:
                    correct_count += 1

            accuracy = correct_count / total_count
            results[f"Top-{k}"] = {
                "accuracy": round(accuracy * 100, 2),
                "correct": correct_count,
                "total": total_count
            }

            logger.info(f"  Top-{k} 召回准确率: {accuracy * 100:.1f}% ({correct_count}/{total_count})")

        return results

    async def test_hallucination_detection(self) -> Dict[str, Any]:
        """测试大模型幻觉检测"""
        logger.info("\n" + "=" * 60)
        logger.info("测试2: 大模型幻觉检测")
        logger.info("=" * 60)

        hallucination_count = 0
        total_count = 0
        detailed_results = []

        for test_case in self.test_cases:
            result = await rag_chat(test_case["question"])
            answer = result["answer"]
            references = result["reference_news"]
            total_count += 1

            is_hallucination = False
            hallucination_reasons = []

            if "根据现有新闻资料，无法回答该问题" in answer:
                is_hallucination = False
            else:
                answer_lower = answer.lower()
                for keyword in test_case["expected_keywords"]:
                    if keyword.lower() not in answer_lower:
                        hallucination_reasons.append(f"缺少关键词 '{keyword}'")

                for ref in references:
                    ref_lower = ref.lower()
                    has_overlap = any(kw.lower() in ref_lower for kw in test_case["expected_keywords"])
                    if not has_overlap:
                        hallucination_reasons.append(f"参考新闻 '{ref}' 与问题无关")

                if hallucination_reasons:
                    is_hallucination = True
                    hallucination_count += 1

            detailed_results.append({
                "question": test_case["question"],
                "is_hallucination": is_hallucination,
                "reasons": hallucination_reasons,
                "answer": answer[:100] + "..." if len(answer) > 100 else answer,
                "references": references
            })

        hallucination_rate = hallucination_count / total_count
        logger.info(f"  幻觉检测完成")
        logger.info(f"  总测试用例: {total_count}")
        logger.info(f"  检测到幻觉: {hallucination_count}")
        logger.info(f"  幻觉率: {hallucination_rate * 100:.1f}%")

        for result in detailed_results:
            status = "疑似幻觉" if result["is_hallucination"] else "正常"
            logger.info(f"\n  [{status}] {result['question']}")
            if result["is_hallucination"]:
                for reason in result["reasons"]:
                    logger.info(f"     - {reason}")

        return {
            "hallucination_rate": round(hallucination_rate * 100, 2),
            "total_cases": total_count,
            "hallucination_cases": hallucination_count,
            "details": detailed_results
        }

    async def test_multiturn_context(self) -> Dict[str, Any]:
        """测试多轮对话上下文保持能力"""
        logger.info("\n" + "=" * 60)
        logger.info("测试3: 多轮对话上下文校验")
        logger.info("=" * 60)

        success_count = 0
        total_count = 0
        detailed_results = []

        for test_case in self.multiturn_test_cases:
            total_count += 1
            history = []

            for i, msg in enumerate(test_case["conversations"]):
                if msg["role"] == "user":
                    result = await rag_chat(msg["content"], history)
                    answer = result["answer"]

                    # 将系统真实回答加入历史，供下一轮使用
                    history.append({"role": "assistant", "content": answer})

                    if i == len(test_case["conversations"]) - 1:
                        context_found = sum(1 for kw in test_case["expected_context"] if kw in answer)
                        context_coverage = context_found / len(test_case["expected_context"])
                        is_success = context_coverage >= 0.5

                        if is_success:
                            success_count += 1

                        detailed_results.append({
                            "test_id": test_case["id"],
                            "final_question": msg["content"],
                            "answer": answer[:150] + "..." if len(answer) > 150 else answer,
                            "context_coverage": f"{context_found}/{len(test_case['expected_context'])}",
                            "is_success": is_success,
                            "history_rounds": len(history)
                        })

        accuracy = success_count / total_count if total_count > 0 else 0
        logger.info(f"  多轮对话测试完成")
        logger.info(f"  总测试用例: {total_count}")
        logger.info(f"  上下文保持成功: {success_count}")
        logger.info(f"  准确率: {accuracy * 100:.1f}%")

        for result in detailed_results:
            status = "通过" if result["is_success"] else "失败"
            logger.info(f"\n  [{status}] {result['final_question']}")
            logger.info(f"     上下文覆盖率: {result['context_coverage']}")
            logger.info(f"     历史对话轮数: {result['history_rounds']}")

        return {
            "accuracy": round(accuracy * 100, 2),
            "total_cases": total_count,
            "success_cases": success_count,
            "details": detailed_results
        }

    async def run_all_tests(self) -> Dict[str, Any]:
        """运行所有测试"""
        logger.info("=" * 60)
        logger.info("RAG质量评测脚本启动")
        logger.info("=" * 60)

        results = {}

        results["top_k_recall"] = await self.test_top_k_recall()
        results["hallucination_detection"] = await self.test_hallucination_detection()
        results["multiturn_context"] = await self.test_multiturn_context()

        logger.info("\n" + "=" * 60)
        logger.info("RAG质量评测完成")
        logger.info("=" * 60)

        return results


async def main():
    tester = RAGQualityTester()
    results = await tester.run_all_tests()

    summary = {
        "top_k_recall": results["top_k_recall"],
        "hallucination_rate": results["hallucination_detection"]["hallucination_rate"],
        "multiturn_accuracy": results["multiturn_context"]["accuracy"]
    }

    print("\n" + "=" * 60)
    print("RAG质量评测汇总报告")
    print("=" * 60)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
