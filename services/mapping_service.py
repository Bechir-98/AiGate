import json
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from redis.asyncio import Redis

from models.db_models import DBEntityMapping

logger = logging.getLogger("mapping_service")

REDIS_MAPPING_KEY = "gliner_entity_mapping"
CACHE_TTL_SECONDS = 3600


async def get_active_mapping(db: AsyncSession, redis_client: Redis) -> dict[str, str]:
    try:
        cached_mapping = await redis_client.get(REDIS_MAPPING_KEY)
        if cached_mapping:
            return json.loads(cached_mapping)
    except Exception as e:
        logger.warning(f"Redis cache read failed, falling back to database: {e}")

    try:
        result = await db.execute(
            select(DBEntityMapping).where(DBEntityMapping.is_active)
        )
        rows = result.scalars().all()
    except Exception as e:
        logger.error(f"Database failure while fetching entity mappings: {e}")
        raise

    mapping = {row.gliner_label: row.presidio_label for row in rows}

    try:
        await redis_client.set(REDIS_MAPPING_KEY, json.dumps(mapping), ex=CACHE_TTL_SECONDS)
    except Exception as e:
        logger.warning(f"Failed to populate Redis mapping cache: {e}")

    return mapping