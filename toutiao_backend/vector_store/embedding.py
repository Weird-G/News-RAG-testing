import os
import logging
import asyncio
from typing import List
from langchain_core.embeddings import Embeddings

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

logger = logging.getLogger(__name__)

_embedding_model = None


def _get_model():
    global _embedding_model
    if _embedding_model is None:
        from fastembed import TextEmbedding
        logger.info("正在加载 BGE 中文嵌入模型（首次加载会自动下载）...")
        _embedding_model = TextEmbedding(model_name="BAAI/bge-small-zh-v1.5")
        logger.info("BGE 模型加载完成")
    return _embedding_model


class BGEEmbedding(Embeddings):
    """BGE 本地中文嵌入模型（fastembed + ONNX，无 torch 依赖）"""

    def __init__(self):
        _get_model()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        model = _get_model()
        embeddings = list(model.embed(texts))
        return [emb.tolist() if hasattr(emb, 'tolist') else emb for emb in embeddings]

    def embed_query(self, text: str) -> List[float]:
        model = _get_model()
        embeddings = list(model.query_embed(text))
        if embeddings:
            emb = embeddings[0]
            return emb.tolist() if hasattr(emb, 'tolist') else emb
        return []

    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed_documents, texts)

    async def aembed_query(self, text: str) -> List[float]:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed_query, text)


_embedding = BGEEmbedding()


def encode(texts: List[str]) -> List[List[float]]:
    return _embedding.embed_documents(texts)


def encode_single(text: str) -> List[float]:
    return _embedding.embed_query(text)


async def aencode(texts: List[str]) -> List[List[float]]:
    return await _embedding.aembed_documents(texts)


async def aencode_single(text: str) -> List[float]:
    return await _embedding.aembed_query(text)