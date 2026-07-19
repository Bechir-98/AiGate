import asyncio
from database import engine, Base
from models.db_models import DBEntityMapping, AppConfig, DetectionAudit

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print("Database tables created successfully")

if __name__ == "__main__":
    asyncio.run(init_db())