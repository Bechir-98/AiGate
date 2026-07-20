from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel
from database import get_db
from models.db_models import AppConfig
import json

router = APIRouter(prefix="/config", tags=["Configuration"])

VALID_SCANNERS = {"spacy", "gliner1", "gliner2", "prompt_guard", "toxicity", "custom_regex"}

class ScannerChoice(BaseModel):
    active_scanners: list[str]

async def set_active_scanners(db: AsyncSession, redis_client, scanners: list[str]):
    """Saves the active scanner list to PostgreSQL and updates Redis cache."""
    cache_key = "config:active_scanners"
    json_val = json.dumps(scanners)
    
    # 1. Save to Database
    result = await db.execute(select(AppConfig).where(AppConfig.key == "active_scanners"))
    config_entry = result.scalars().first()
    
    if config_entry:
        config_entry.value = json_val
    else:
        new_entry = AppConfig(key="active_scanners", value=json_val)
        db.add(new_entry)
        
    await db.commit()
    
    # 2. Update Redis Cache
    await redis_client.setex(cache_key, 300, json_val)

async def get_active_scanners(db: AsyncSession, redis_client) -> list[str]:
    """Fetches the active scanner list from Redis, falling back to PostgreSQL."""
    cache_key = "config:active_scanners"
    
    # 1. Try Redis Cache
    cached = await redis_client.get(cache_key)
    if cached:
        return json.loads(cached if isinstance(cached, str) else cached.decode("utf-8"))
        
    # 2. Cache Miss: Fetch from PostgreSQL
    result = await db.execute(select(AppConfig).where(AppConfig.key == "active_scanners"))
    config = result.scalars().first()
    
    if config and config.value:
        active_scanners = json.loads(config.value)
    else:
        # Default fallback if nothing is configured
        active_scanners = ["spacy"] 
        
    # 3. Save to Redis
    await redis_client.setex(cache_key, 300, json.dumps(active_scanners))
    return active_scanners

@router.post("/scanners")
async def update_scanners(
    choice: ScannerChoice, 
    request: Request, 
    db: AsyncSession = Depends(get_db)
):
    # Validate requested scanners against allowed set
    invalid = set(choice.active_scanners) - VALID_SCANNERS
    if invalid:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid scanners provided: {invalid}. Allowed: {VALID_SCANNERS}"
        )
        
    redis_client = request.app.state.redis
    await set_active_scanners(db, redis_client, choice.active_scanners)
    
    return {"message": "Global scanners updated successfully", "active_scanners": choice.active_scanners}

@router.get("/scanners")
async def get_scanners(
    request: Request, 
    db: AsyncSession = Depends(get_db)
):
    redis_client = request.app.state.redis
    active_scanners = await get_active_scanners(db, redis_client)
    return {"active_scanners": active_scanners}


async def get_active_entities(db: AsyncSession, redis_client) -> list[str]:
    cache_key = "config:active_entities"
    
    cached_entities = await redis_client.get(cache_key)
    if cached_entities:
        return json.loads(cached_entities if isinstance(cached_entities, str) else cached_entities.decode("utf-8"))
        
    result = await db.execute(select(AppConfig).where(AppConfig.key == "active_entities"))
    config = result.scalars().first()
    
    if config and config.value:
        active_entities = json.loads(config.value)
    else:
        active_entities = ["PERSON", "ORGANIZATION", "LOCATION", "EMAIL"]
    
    await redis_client.setex(cache_key, 300, json.dumps(active_entities))
    return active_entities