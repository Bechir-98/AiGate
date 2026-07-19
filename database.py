from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from typing import AsyncGenerator
from config import settings

engine = create_async_engine(
    settings.async_database_url,
    echo=(settings.FASTAPI_ENV == "development"), 
    pool_size=10, 
    max_overflow=20, 
    pool_timeout=30, 
    pool_pre_ping=True, 
)

async_sessionmaker_local = async_sessionmaker(
    bind=engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

class Base(DeclarativeBase):
    pass

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_sessionmaker_local() as session:
        yield session