"""
rouge_l.py - ROUGE-L 评测指标自实现

ROUGE-L (Recall-Oriented Understudy for Gisting Evaluation - Longest Common Subsequence)
基于最长公共子序列衡量生成答案与参考答案的重叠度，常用于评估文本生成质量。

本实现特点：
1. 无第三方依赖（不引入 rouge-score / jieba），中文按字符级切分
2. 实现 LCS 动态规划算法
3. 输出 precision / recall / f1 三项指标
4. 支持句子级与摘要级（summary-level）两种聚合方式

公式：
- LCS(c, r) = 候选 c 与参考 r 的最长公共子序列长度
- Precision P = LCS / |c|
- Recall    R = LCS / |r|
- F1        F = 2*P*R / (P+R)
"""

from typing import List, Dict, Any


def lcs_length(s1: List[str], s2: List[str]) -> int:
    """
    最长公共子序列长度（动态规划）
    时间复杂度 O(m*n)，空间可优化到 O(min(m,n))，此处保留二维便于理解
    """
    m, n = len(s1), len(s2)
    if m == 0 or n == 0:
        return 0

    # dp[i][j] = s1[:i] 与 s2[:j] 的 LCS 长度
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if s1[i - 1] == s2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1] + 1
            else:
                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])
    return dp[m][n]


def _tokenize_zh(text: str) -> List[str]:
    """
    中文分词：按字符切分（中文 ROUGE 常用做法，避免引入 jieba）
    标点符号过滤掉，避免标点干扰重叠度
    """
    if not text:
        return []
    # 过滤标点和空白
    punctuation = " \t\n\r，。！？、；：""''（）《》【】〈〉「」『』,.!?;:\"'()[]{}<>-_+=*&#%@~`|\\/"
    return [ch for ch in text if ch not in punctuation]


def rouge_l_sentence(candidate: str, reference: str) -> Dict[str, float]:
    """
    句子级 ROUGE-L
    返回 {precision, recall, f1, lcs}
    """
    cand_tokens = _tokenize_zh(candidate)
    ref_tokens = _tokenize_zh(reference)

    if not cand_tokens or not ref_tokens:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "lcs": 0}

    lcs = lcs_length(cand_tokens, ref_tokens)
    precision = lcs / len(cand_tokens) if cand_tokens else 0.0
    recall = lcs / len(ref_tokens) if ref_tokens else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "lcs": lcs
    }


def rouge_l_summary(candidate_sentences: List[str], reference_sentences: List[str]) -> Dict[str, float]:
    """
    摘要级 ROUGE-L（Union LCS）
    把所有候选句子拼成整体，所有参考句子拼成整体，再算 LCS
    适用于多句答案的汇总类查询
    """
    cand_all = _tokenize_zh("".join(candidate_sentences))
    ref_all = _tokenize_zh("".join(reference_sentences))

    if not cand_all or not ref_all:
        return {"precision": 0.0, "recall": 0.0, "f1": 0.0, "lcs": 0}

    lcs = lcs_length(cand_all, ref_all)
    precision = lcs / len(cand_all) if cand_all else 0.0
    recall = lcs / len(ref_all) if ref_all else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "lcs": lcs
    }


def rouge_l(candidate: str, reference: str, mode: str = "sentence") -> Dict[str, float]:
    """
    ROUGE-L 统一入口
    mode: "sentence"（句子级，默认）或 "summary"（摘要级，多句聚合）
    """
    if mode == "summary":
        # 把候选和参考都按句号切分成多句
        import re
        cand_sents = [s.strip() for s in re.split(r"[。！？\n]", candidate) if s.strip()]
        ref_sents = [s.strip() for s in re.split(r"[。！？\n]", reference) if s.strip()]
        return rouge_l_summary(cand_sents, ref_sents)
    return rouge_l_sentence(candidate, reference)


# ============ 自检 ============
if __name__ == "__main__":
    # 自检：完全相同 → f1=1.0
    r = rouge_l("社区时间银行是一种新型养老模式", "社区时间银行是一种新型养老模式")
    assert r["f1"] == 1.0, f"完全相同应得1.0，实际{r['f1']}"
    print(f"[自检1] 完全相同: f1={r['f1']} ✓")

    # 自检：完全不同 → f1=0.0
    r = rouge_l("今天天气很好", "量子计算突破")
    assert r["f1"] == 0.0, f"完全不同应得0.0，实际{r['f1']}"
    print(f"[自检2] 完全不同: f1={r['f1']} ✓")

    # 自检：部分重叠
    r = rouge_l("社区时间银行养老模式受关注", "社区时间银行是一种新型养老模式")
    print(f"[自检3] 部分重叠: f1={r['f1']}, precision={r['precision']}, recall={r['recall']}, lcs={r['lcs']}")

    # 自检：摘要级
    r = rouge_l("中国乒乓球队包揽世乒赛冠军。中国女足亚洲杯夺冠。", "中国乒乓球队包揽世乒赛冠军。", mode="summary")
    print(f"[自检4] 摘要级: f1={r['f1']}, recall={r['recall']}")

    print("\n所有自检通过 ✓")
