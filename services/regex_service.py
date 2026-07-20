import json
import logging
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from models.db_models import DBCustomRegexPattern

logger = logging.getLogger("regex_service")

REDIS_CUSTOM_REGEX_KEY = "custom_regex_patterns"
CACHE_TTL = 3600


async def get_active_patterns(db: AsyncSession, redis_client) -> List[Dict[str, Any]]:
    """
    Returns all active custom regex patterns.
    Uses Redis as a fast primary layer, with PostgreSQL as fallback.
    """
    # 1. Try Redis first
    try:
        cached = await redis_client.get(REDIS_CUSTOM_REGEX_KEY)
        if cached:
            return json.loads(cached)
    except Exception as e:
        logger.warning(f"Redis read failed for custom regex patterns, falling back to DB: {e}")

    # 2. DB Fallback
    result = await db.execute(
        select(DBCustomRegexPattern).where(DBCustomRegexPattern.is_active == True)
    )
    rows = result.scalars().all()
    patterns = [
        {
            "id": r.id,
            "name": r.name,
            "pattern": r.pattern,
            "entity_type": r.entity_type,
            "score": r.score
        }
        for r in rows
    ]

    # 3. Populate cache
    try:
        await redis_client.set(REDIS_CUSTOM_REGEX_KEY, json.dumps(patterns), ex=CACHE_TTL)
    except Exception as e:
        logger.warning(f"Failed to populate Redis cache for custom regex patterns: {e}")

    return patterns