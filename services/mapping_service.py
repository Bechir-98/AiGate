import json
import logging
from typing import Dict
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from redis.asyncio import Redis

from models.db_models import DBEntityMapping

logger = logging.getLogger("mapping_service")

REDIS_MAPPING_KEY = "gliner_entity_mapping"
CACHE_TTL_SECONDS = 3600


async def get_active_mapping(db: AsyncSession, redis_client: Redis) -> dict[str, str]:
    """
    Retrieves the dictionary of active PII scanning labels.
    Uses Redis as a high-speed primary layer, with safe fallbacks to PostgreSQL.
    """
    # 1. Try Redis first (with Soft Fail protection)
    try:
        cached_mapping = await redis_client.get(REDIS_MAPPING_KEY)
        if cached_mapping:
            return json.loads(cached_mapping)
    except Exception as e:
        # If Redis is unreachable, log the warning but DO NOT crash.
        # Let the code naturally fall through to Step 2.
        logger.warning(f"Redis cache read failed, falling back to database: {e}")

    # 2. Cache miss or Redis failure: Query Postgres
    try:
        # SQLAlchemy 2.0 natively evaluates boolean columns without '== True'
        result = await db.execute(
            select(DBEntityMapping).where(DBEntityMapping.is_active)
        )
        rows = result.scalars().all()
    except Exception as e:
        logger.error(f"Critical database failure while fetching entity mappings: {e}")
        # If the database is also down, we must raise an error.
        raise

    # 3. Build the mapping dictionary
    mapping = {row.gliner_label: row.presidio_label for row in rows}

    # 4. Asynchronously attempt to heal the cache
    try:
        await redis_client.set(REDIS_MAPPING_KEY, json.dumps(mapping), ex=CACHE_TTL_SECONDS)
    except Exception as e:
        # If Redis is read-only or unreachable, we just skip caching. 
        # The app will keep working, just slightly slower.
        logger.warning(f"Failed to populate Redis mapping cache: {e}")

    return mapping