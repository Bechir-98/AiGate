from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from models.db_models import AppConfig

async def get_active_scanner(db: AsyncSession, redis_client) -> str:
    cache_key = "config:active_scanner"
    
    cached_scanner = await redis_client.get(cache_key)
    if cached_scanner:
        if isinstance(cached_scanner, str):
            return cached_scanner
        return cached_scanner.decode("utf-8")
        
    result = await db.execute(
        select(AppConfig).where(AppConfig.key == "active_scanner")
    )
    config = result.scalars().first()
    active_scanner = config.value if config else "spacy"
    
    await redis_client.setex(cache_key, 300, active_scanner)
    
    return active_scanner

async def set_active_scanner(db: AsyncSession, redis_client, scanner_name: str):
    result = await db.execute(select(AppConfig).where(AppConfig.key == "active_scanner"))
    config = result.scalars().first()
    
    if config:
        config.value = scanner_name
    else:
        config = AppConfig(key="active_scanner", value=scanner_name)
        db.add(config)
        
    await db.commit()
    # Use setex to match the 300s TTL from get_active_scanner — plain set() would cache forever
    await redis_client.setex("config:active_scanner", 300, scanner_name)