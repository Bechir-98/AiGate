import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from redis.asyncio import Redis
from models.entity_mapping import DBEntityMapping

REDIS_MAPPING_KEY = "gliner_entity_mapping"
CACHE_TTL_SECONDS = 3600

async def get_active_mapping(db: AsyncSession, redis_client: Redis) -> dict:
    
    # 1. Try Redis first
    cached_mapping = await redis_client.get(REDIS_MAPPING_KEY)
    if cached_mapping:
        return json.loads(cached_mapping)

    # 2. Cache miss: Query Postgres
    result = await db.execute(
        select(DBEntityMapping).where(DBEntityMapping.is_active == True)
    )
    rows = result.scalars().all()

    # 3. Build the dictionary
    mapping = {row.gliner_label: row.presidio_label for row in rows}

    # 4. Save to Redis for subsequent requests
    await redis_client.set(REDIS_MAPPING_KEY, json.dumps(mapping), ex=CACHE_TTL_SECONDS)

    return mapping