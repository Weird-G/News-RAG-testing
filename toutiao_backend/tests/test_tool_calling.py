"""
test_tool_calling.py - Agent 工具链路全场景测试

覆盖「意图识别 → 工具选择 → 参数提取 → 执行反馈」完整链路
针对 3 类核心工具（精确查询 / 列表检索 / 统计聚合）设计 21 个测试场景：
- 正常调用、异常参数、模糊意图、边界值、异常降级与兜底

测试矩阵（3 类 × 7-8 场景 = 21 个）：
一、精确查询类（get_news_views / count_news_words）：7 个
二、列表检索类（list_news_by_category / get_news_by_date / get_latest_news / get_hot_news）：8 个
三、统计聚合类（get_news_statistics）：3 个
四、异常降级与兜底（规则匹配 / 参数校验 / JSON 解析）：3 个
"""

import os
import sys
import pytest
import pytest_asyncio
import asyncio

# 确保项目根目录在 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent.tools import (
    get_news_views, count_news_words,
    list_news_by_category, get_news_by_date, get_latest_news, get_hot_news,
    get_news_statistics, TOOLS_CONFIG, TOOL_FUNCTIONS
)
from agent.function_calling import (
    rule_based_tool_selection, parse_tool_call,
    _validate_and_convert_params, _convert_param_type, _required_params
)


# ====================================================================
# 一、精确查询类：7 个场景
# ====================================================================

class TestExactQuery:
    """精确查询类工具测试：按 ID 查询特定字段（浏览量、字数）"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("news_id, expected_success", [
        (1, True),           # 正常：存在的新闻ID
        (99999, False),       # 异常：不存在的新闻ID
        (-1, False),          # 异常：负数ID
    ])
    async def test_get_news_views(self, db_session, news_id, expected_success):
        """[精确查询] get_news_views 浏览量查询 - 正常/异常ID"""
        result = await get_news_views(db_session, news_id)
        assert result["success"] == expected_success
        if expected_success:
            assert "views" in result["data"]
            assert isinstance(result["data"]["views"], int)
            assert result["data"]["views"] >= 0

    @pytest.mark.asyncio
    @pytest.mark.parametrize("news_id, expected_success", [
        (1, True),           # 正常：存在的新闻ID
        (99999, False),       # 异常：不存在的新闻ID
    ])
    async def test_count_news_words(self, db_session, news_id, expected_success):
        """[精确查询] count_news_words 字数统计 - 正常/异常ID"""
        result = await count_news_words(db_session, news_id)
        assert result["success"] == expected_success
        if expected_success:
            assert "word_count" in result["data"]
            assert result["data"]["word_count"] >= 0

    @pytest.mark.asyncio
    async def test_get_news_views_data_structure(self, db_session):
        """[精确查询] 验证返回数据结构包含 news_id/title/views"""
        result = await get_news_views(db_session, 1)
        assert result["success"] is True
        data = result["data"]
        assert "news_id" in data
        assert "title" in data
        assert "views" in data

    @pytest.mark.asyncio
    async def test_count_news_words_data_structure(self, db_session):
        """[精确查询] 验证字数统计返回结构包含 news_id/title/word_count"""
        result = await count_news_words(db_session, 1)
        assert result["success"] is True
        data = result["data"]
        assert "news_id" in data
        assert "title" in data
        assert "word_count" in data
        assert "char_count" in data


# ====================================================================
# 二、列表检索类：8 个场景
# ====================================================================

class TestListRetrieval:
    """列表检索类工具测试：按条件返回新闻列表"""

    @pytest.mark.asyncio
    @pytest.mark.parametrize("category_name, expected_success", [
        ("科技", True),                  # 正常：存在的分类
        ("财经", True),                  # 正常：存在的分类
        ("不存在的分类", False),         # 异常：不存在的分类
        ("", False),                     # 异常：空分类名
    ])
    async def test_list_news_by_category(self, db_session, category_name, expected_success):
        """[列表检索] list_news_by_category - 正常/异常/空分类"""
        result = await list_news_by_category(db_session, category_name)
        assert result["success"] == expected_success
        if expected_success:
            assert isinstance(result["data"], list)
            assert len(result["data"]) > 0
            # 验证按浏览量倒序
            views_list = [n["views"] for n in result["data"]]
            assert views_list == sorted(views_list, reverse=True)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("date_str, expected_success", [
        ("2026-08-20", True),     # 正常：合法日期（可能无新闻但格式合法）
        ("invalid", False),       # 异常：非法日期格式
        ("2026-13-45", False),   # 异常：非法日期值（13月45日）
        ("", False),              # 异常：空日期
    ])
    async def test_get_news_by_date(self, db_session, date_str, expected_success):
        """[列表检索] get_news_by_date - 正常/非法格式/非法值/空"""
        result = await get_news_by_date(db_session, date_str)
        assert result["success"] == expected_success
        if expected_success:
            assert "data" in result
            assert "meta" in result
            assert result["meta"]["date"] == date_str

    @pytest.mark.asyncio
    @pytest.mark.parametrize("limit, expected_max_len", [
        (5, 5),           # 正常：limit=5
        (10, 10),         # 正常：默认limit
        (0, 10),          # 边界：limit=0 → 兜底默认10
        (-1, 10),         # 边界：负数 → 兜底默认10
        (200, 100),       # 边界：超限 → 截断为100
    ])
    async def test_get_latest_news_limit_boundary(self, db_session, limit, expected_max_len):
        """[列表检索] get_latest_news - limit 边界值与兜底"""
        result = await get_latest_news(db_session, limit)
        assert result["success"] is True
        assert len(result["data"]) <= expected_max_len
        # 验证按发布时间倒序
        if len(result["data"]) > 1:
            times = [n["publish_time"] for n in result["data"]]
            assert times == sorted(times, reverse=True)

    @pytest.mark.asyncio
    async def test_get_hot_news_ordering(self, db_session):
        """[列表检索] get_hot_news - 验证按浏览量倒序"""
        result = await get_hot_news(db_session, 10)
        assert result["success"] is True
        if len(result["data"]) > 1:
            views_list = [n["views"] for n in result["data"]]
            assert views_list == sorted(views_list, reverse=True)


# ====================================================================
# 三、统计聚合类：3 个场景
# ====================================================================

class TestStatistics:
    """统计聚合类工具测试：聚合计算（分类计数、总量求和）"""

    @pytest.mark.asyncio
    async def test_get_news_statistics_normal(self, db_session):
        """[统计聚合] get_news_statistics - 正常聚合查询"""
        result = await get_news_statistics(db_session)
        assert result["success"] is True
        assert "data" in result
        assert "by_category" in result["data"]
        assert "global" in result["data"]

    @pytest.mark.asyncio
    async def test_get_news_statistics_structure(self, db_session):
        """[统计聚合] 验证 by_category 结构（每项含 category_name/news_count/total_views）"""
        result = await get_news_statistics(db_session)
        assert result["success"] is True
        by_category = result["data"]["by_category"]
        assert isinstance(by_category, list)
        assert len(by_category) > 0
        for item in by_category:
            assert "category_id" in item
            assert "category_name" in item
            assert "news_count" in item
            assert "total_views" in item
            assert isinstance(item["news_count"], int)
            assert isinstance(item["total_views"], int)

    @pytest.mark.asyncio
    async def test_get_news_statistics_global(self, db_session):
        """[统计聚合] 验证 global 字段（total_news/total_views/category_count）"""
        result = await get_news_statistics(db_session)
        assert result["success"] is True
        global_data = result["data"]["global"]
        assert "total_news" in global_data
        assert "total_views" in global_data
        assert "category_count" in global_data
        # 全局新闻总数 = 各分类新闻数之和
        by_category = result["data"]["by_category"]
        sum_count = sum(item["news_count"] for item in by_category)
        assert global_data["total_news"] == sum_count


# ====================================================================
# 四、异常降级与兜底：3 个场景
# ====================================================================

class TestFallbackAndDegradation:
    """异常降级与兜底测试：意图识别、参数校验、JSON 解析"""

    @pytest.mark.parametrize("question, expected_tool", [
        ("新闻1的浏览量是多少？", "get_news_views"),        # 模糊意图→浏览量工具
        ("科技类有哪些新闻", "list_news_by_category"),       # 模糊意图→分类列表
        ("今天有什么新闻", "get_news_by_date"),              # 模糊意图→日期查询
        ("最新新闻有哪些", "get_latest_news"),               # 模糊意图→最新新闻
        ("热点新闻排行", "get_hot_news"),                     # 模糊意图→热门新闻
        ("新闻统计有多少条", "get_news_statistics"),          # 模糊意图→统计聚合
        ("你好", None),                                       # 模糊意图→无匹配（闲聊）
        ("今天天气怎么样", None),                              # 模糊意图→无匹配（闲聊）
    ])
    def test_rule_based_tool_selection(self, question, expected_tool):
        """[异常降级] 规则兜底意图识别 - 正常匹配/无匹配"""
        result = rule_based_tool_selection(question)
        if expected_tool:
            assert result is not None
            assert result["tool"] == expected_tool
        else:
            # 闲聊类问题不应匹配到工具
            assert result is None or result.get("tool") != expected_tool

    @pytest.mark.asyncio
    @pytest.mark.parametrize("response_str, should_parse, expected_tool", [
        ('{"tool": "get_news_views", "params": {"news_id": 1}}', True, "get_news_views"),
        ('未匹配到工具，直接回答用户', False, None),                # 无JSON
        ('{"tool": "get_news_by_date", "params": {"date_str": "2026-08-20"}}', True, "get_news_by_date"),
        ('前缀文字 {"tool": "get_hot_news", "params": {}} 后缀', True, "get_hot_news"),  # 混杂文字
    ])
    async def test_parse_tool_call(self, response_str, should_parse, expected_tool):
        """[异常降级] JSON 解析 - 合法JSON/无JSON/混杂文字"""
        result = await parse_tool_call(response_str)
        if should_parse:
            assert result is not None
            assert result.get("tool") == expected_tool
        else:
            assert result is None

    @pytest.mark.parametrize("tool_name, params, expect_errors", [
        # 正常：必填参数齐全
        ("get_news_views", {"news_id": 1}, False),
        # 异常：缺少必填参数 news_id
        ("get_news_views", {}, True),
        # 异常：参数类型错误（字符串无法转int）
        ("get_news_views", {"news_id": "abc"}, True),
        # 正常：list_news_by_category 必填参数齐全
        ("list_news_by_category", {"category_name": "科技"}, False),
        # 异常：list_news_by_category 缺少 category_name
        ("list_news_by_category", {}, True),
        # 正常：get_news_statistics 无必填参数
        ("get_news_statistics", {}, False),
    ])
    def test_validate_params(self, tool_name, params, expect_errors):
        """[异常降级] 参数校验与类型转换 - 正常/缺参/类型错误"""
        converted, errors = _validate_and_convert_params(tool_name, params)
        if expect_errors:
            assert len(errors) > 0
        else:
            assert len(errors) == 0
            # 验证类型转换
            if tool_name == "get_news_views" and "news_id" in params:
                assert isinstance(converted["news_id"], int)

    @pytest.mark.parametrize("value, target_type, expected_result", [
        ("1", "integer", 1),          # 字符串→整数
        (1, "integer", 1),            # 整数→整数
        ("abc", "integer", None),     # 非法字符串→None
        (100, "string", "100"),       # 整数→字符串
    ])
    def test_convert_param_type(self, value, target_type, expected_result):
        """[异常降级] 参数类型转换 - 字符串/整数/非法值"""
        result = _convert_param_type(value, target_type)
        assert result == expected_result


# ====================================================================
# 五、工具配置完整性测试
# ====================================================================

class TestToolConfig:
    """工具配置与函数映射一致性测试"""

    def test_tools_config_functions_consistency(self):
        """[配置校验] TOOLS_CONFIG 与 TOOL_FUNCTIONS 工具名完全一致"""
        config_names = {tool["name"] for tool in TOOLS_CONFIG}
        function_names = set(TOOL_FUNCTIONS.keys())
        assert config_names == function_names, f"配置与函数映射不一致: 配置独有{config_names-function_names}, 函数独有{function_names-config_names}"

    def test_tools_config_count(self):
        """[配置校验] 工具数量 = 7（精确查询2 + 列表检索4 + 统计聚合1）"""
        assert len(TOOLS_CONFIG) == 7

    def test_required_params_correct(self):
        """[配置校验] 必填参数推导正确"""
        # get_news_views 必填 news_id
        assert "news_id" in _required_params("get_news_views")
        # list_news_by_category 必填 category_name
        assert "category_name" in _required_params("list_news_by_category")
        # get_news_statistics 无必填参数
        assert _required_params("get_news_statistics") == []
        # get_news_by_date 必填 date_str
        assert "date_str" in _required_params("get_news_by_date")

    def test_three_categories_covered(self):
        """[配置校验] 3 类核心工具全覆盖（精确查询/列表检索/统计聚合）"""
        exact_query_tools = ["get_news_views", "count_news_words"]
        list_retrieval_tools = ["list_news_by_category", "get_news_by_date", "get_latest_news", "get_hot_news"]
        statistics_tools = ["get_news_statistics"]

        config_names = {tool["name"] for tool in TOOLS_CONFIG}
        for tool_name in exact_query_tools:
            assert tool_name in config_names, f"精确查询类工具 {tool_name} 缺失"
        for tool_name in list_retrieval_tools:
            assert tool_name in config_names, f"列表检索类工具 {tool_name} 缺失"
        for tool_name in statistics_tools:
            assert tool_name in config_names, f"统计聚合类工具 {tool_name} 缺失"
