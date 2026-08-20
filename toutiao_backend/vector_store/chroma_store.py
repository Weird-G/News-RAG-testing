import os
import chromadb
from chromadb.config import Settings
from typing import List, Dict, Any
from vector_store.embedding import encode, aencode

CHROMA_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "chroma_data")

os.makedirs(CHROMA_DATA_DIR, exist_ok=True)

client = chromadb.PersistentClient(
    path=CHROMA_DATA_DIR,
    settings=Settings(
        anonymized_telemetry=False,
        allow_reset=True
    )
)


def get_or_create_collection(collection_name: str = "news_embeddings"):
    # 使用 cosine 距离度量：retrieve_relevant_news 的 min_distance 阈值（0~2）
    # 是按 cosine distance 设计的。Chroma 默认 L2，会导致同语义结果距离偏大、
    # 被阈值误滤，检索召回失效。新建 collection 时必须指定 hnsw:space=cosine。
    return client.get_or_create_collection(
        name=collection_name,
        metadata={"hnsw:space": "cosine"}
    )


def add_documents(
    collection_name: str,
    documents: List[str],
    metadatas: List[Dict[str, Any]],
    ids: List[str]
):
    collection = get_or_create_collection(collection_name)
    
    embeddings = encode(documents)
    
    for i in range(0, len(documents), 10):
        batch_docs = documents[i:i+10]
        batch_metas = metadatas[i:i+10]
        batch_ids = ids[i:i+10]
        batch_embs = embeddings[i:i+10]
        
        collection.add(
            documents=batch_docs,
            metadatas=batch_metas,
            ids=batch_ids,
            embeddings=batch_embs
        )


async def add_documents_async(
    collection_name: str,
    documents: List[str],
    metadatas: List[Dict[str, Any]],
    ids: List[str]
):
    collection = get_or_create_collection(collection_name)
    
    embeddings = await aencode(documents)
    
    for i in range(0, len(documents), 10):
        batch_docs = documents[i:i+10]
        batch_metas = metadatas[i:i+10]
        batch_ids = ids[i:i+10]
        batch_embs = embeddings[i:i+10]
        
        collection.add(
            documents=batch_docs,
            metadatas=batch_metas,
            ids=batch_ids,
            embeddings=batch_embs
        )


def query(
    collection_name: str,
    query_embeddings: List[List[float]],
    n_results: int = 3
) -> Dict[str, Any]:
    collection = get_or_create_collection(collection_name)
    return collection.query(
        query_embeddings=query_embeddings,
        n_results=n_results
    )


def get_collection_count(collection_name: str) -> int:
    collection = get_or_create_collection(collection_name)
    return collection.count()


def clear_collection(collection_name: str):
    collection = get_or_create_collection(collection_name)
    ids = collection.get()["ids"]
    if ids:
        for i in range(0, len(ids), 10):
            batch_ids = ids[i:i+10]
            collection.delete(ids=batch_ids)


def get_collection(collection_name: str):
    try:
        return client.get_collection(name=collection_name)
    except Exception:
        return None