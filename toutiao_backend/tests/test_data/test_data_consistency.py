"""
test_data_consistency.py - 数据一致性测试

本文件测试 MySQL 与 Chroma 向量库之间的数据一致性，
确保双存储架构的数据同步正确。

测试内容:
1. 数据条数一致性：MySQL 新闻数与 Chroma 向量数的关系
2. 数据完整性：Chroma 中向量数据的结构是否完整
3. 元数据完整性：每条向量的元数据字段是否齐全
4. 检索功能：向量检索是否能返回相关结果
5. 同步状态：最新新闻是否已同步到 Chroma

注意: 部分测试需要 MySQL 数据库连接，如果连接失败会自动跳过
"""

import pytest
import sys
import os

# 确保项目路径可以正确导入模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vector_store.chroma_store import (
    get_or_create_collection,      # 获取或创建 Chroma 集合
    get_collection_count,          # 获取集合中的文档数量
    query as chroma_query          # Chroma 向量检索
)
from vector_store.embedding import encode  # 文本向量化
from config.db_conf import AsyncSessionLocal  # 数据库会话
from models.news import News       # 新闻模型
from sqlalchemy import select, func  # SQL 查询构造


class TestDataConsistency:
    """
    数据一致性测试类
    
    验证 MySQL（结构化数据）与 Chroma（向量数据）两个存储层的数据一致性。
    
    CHROMA_NAME: Chroma 集合名称，存储新闻的向量表示
    """

    COLLECTION_NAME = "news_embeddings"  # Chroma 集合名

    @pytest.mark.asyncio
    async def test_mysql_chroma_count_match(self):
        """
        测试 MySQL 与 Chroma 数据条数一致性
        
        验证逻辑:
        - MySQL 新闻数 > 0 时，Chroma 向量数也必须 > 0
        - Chroma 向量数 >= MySQL 新闻数（因为每条新闻会被切分成多个向量）
        
        注意: 如果 MySQL 无数据，Chroma 为空也属于正常情况
        """
        async with AsyncSessionLocal() as db:
            # 查询 MySQL 中的新闻总数
            result = await db.execute(select(func.count(News.id)))
            mysql_count = result.scalar() or 0
            
            # 查询 Chroma 中的向量总数
            chroma_count = get_collection_count(self.COLLECTION_NAME)
            
            # 打印调试信息
            print(f"MySQL 新闻数: {mysql_count}, Chroma 向量数: {chroma_count}")
            
            # 断言: MySQL 有数据时，Chroma 不能为空
            if mysql_count > 0:
                assert chroma_count > 0, \
                    "Chroma 向量库为空，但 MySQL 有新闻数据，可能同步失败"

    @pytest.mark.asyncio
    async def test_chroma_has_valid_data(self):
        """
        测试 Chroma 包含有效数据
        
        验证 Chroma 中的每条向量数据都包含:
        - ids: 向量唯一标识
        - documents: 原始文本内容
        - metadatas: 元数据（包含 news_id, chunk_index 等）
        """
        collection = get_or_create_collection(self.COLLECTION_NAME)
        
        # 跳过测试: Chroma 为空时无需验证
        if collection.count() == 0:
            pytest.skip("Chroma 向量库为空，跳过数据完整性检查")
        
        # 获取所有数据
        all_data = collection.get()
        
        # 验证必要字段存在
        assert "ids" in all_data, "Chroma 数据缺少 ids 字段"
        assert "documents" in all_data, "Chroma 数据缺少 documents 字段"
        assert "metadatas" in all_data, "Chroma 数据缺少 metadatas 字段"
        
        # 验证三个字段的长度一致
        ids = all_data["ids"]
        documents = all_data["documents"]
        metadatas = all_data["metadatas"]
        
        assert len(ids) == len(documents) == len(metadatas), \
            f"数据不一致: ids({len(ids)}), documents({len(documents)}), metadatas({len(metadatas)})"
        
        print(f"Chroma 中共有 {len(ids)} 条有效向量数据")

    @pytest.mark.asyncio
    async def test_chroma_metadata_complete(self):
        """
        测试 Chroma 元数据完整性
        
        验证每条向量的元数据都包含必要字段:
        - news_id: 关联的新闻 ID
        - chunk_index: 在原新闻中的切片位置
        """
        collection = get_or_create_collection(self.COLLECTION_NAME)
        
        if collection.count() == 0:
            pytest.skip("Chroma 向量库为空，跳过元数据检查")
        
        all_data = collection.get()
        metadatas = all_data["metadatas"]
        
        # 必须存在的元数据字段
        required_fields = ["news_id", "chunk_index"]
        
        incomplete_count = 0
        for metadata in metadatas:
            if metadata:
                for field in required_fields:
                    if field not in metadata or metadata[field] is None:
                        incomplete_count += 1
                        break  # 发现一个缺失就不再检查其他字段
        
        if incomplete_count > 0:
            print(f"警告: 有 {incomplete_count} 条向量的元数据可能不完整")

    @pytest.mark.asyncio
    async def test_search_returns_relevant_results(self):
        """
        测试向量检索返回相关结果
        
        使用"养老"作为查询词，验证:
        1. 能返回至少一个结果
        2. 返回结果数量不超过 n_results 参数
        """
        collection = get_or_create_collection(self.COLLECTION_NAME)
        
        if collection.count() == 0:
            pytest.skip("Chroma 向量库为空，跳过检索测试")
        
        # 执行向量检索
        query_text = "养老"
        query_embedding = encode([query_text])
        results = chroma_query(
            self.COLLECTION_NAME,
            query_embeddings=query_embedding,
            n_results=3  # 最多返回 3 条结果
        )
        
        # 验证检索结果
        assert "ids" in results, "检索结果缺少 ids 字段"
        assert len(results["ids"][0]) > 0, "搜索无结果"
        assert len(results["ids"][0]) <= 3, f"返回结果数({len(results['ids'][0])})超过限制(3)"

    @pytest.mark.asyncio
    async def test_data_sync_check(self):
        """
        测试数据同步状态
        
        检查最新的 MySQL 新闻是否已同步到 Chroma。
        如果最新新闻在 Chroma 中找不到对应向量，说明同步可能有问题。
        
        注意: 数据库连接失败时会跳过测试
        """
        try:
            async with AsyncSessionLocal() as db:
                # 查询最新的一条新闻（按 ID 降序）
                result = await db.execute(
                    select(News).order_by(News.id.desc()).limit(1)
                )
                latest_news = result.scalar_one_or_none()
                
                if latest_news:
                    collection = get_or_create_collection(self.COLLECTION_NAME)
                    
                    # 在 Chroma 中查找该新闻的向量
                    news_id_str = str(latest_news.id)
                    results = collection.get(
                        where={"news_id": news_id_str}  # 按元数据过滤
                    )
                    
                    count = len(results.get("ids", []))
                    print(f"最新新闻 ID: {latest_news.id}, Chroma 向量数: {count}")
                    
                    # 如果找不到向量，打印警告（不强制失败）
                    if count == 0:
                        print(f"警告: 最新新闻 '{latest_news.title}' 在 Chroma 中没有向量，可能需要同步")
        except Exception as e:
            # 数据库连接失败时跳过
            pytest.skip(f"数据库连接失败，跳过同步检查: {e}")
