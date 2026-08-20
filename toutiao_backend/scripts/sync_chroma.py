import asyncio
from config.db_conf import get_db
from rag.rag_service import sync_news_to_vector_db

async def main():
    async with get_db() as db:
        count = await sync_news_to_vector_db(db)
        print(f"同步完成，{count} 个片段已写入 Chroma")

asyncio.run(main())
