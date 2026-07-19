from fastapi import APIRouter, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel
from database import get_db
from models.db_models import AppConfig
from services.config_service import get_active_scanner, set_active_scanner
import json

router = APIRouter(prefix="/config")

class ScannerChoice(BaseModel):
    scanner_name: str 

@router.post("/scanner")
async def update_scanner(
    choice: ScannerChoice, 
    request: Request, 
    db: AsyncSession = Depends(get_db)
):
    redis_client = request.app.state.redis
    
    if choice.scanner_name not in ["spacy", "gliner1", "gliner2"]:
        return {"error": "Invalid scanner name. Choose spacy, gliner1, or gliner2."}
        
    await set_active_scanner(db, redis_client, choice.scanner_name)
    
    return {"message": f"Global scanner updated to {choice.scanner_name}"}

@router.get("/scanner")
async def get_scanner(
    request: Request, 
    db: AsyncSession = Depends(get_db)
):
    redis_client = request.app.state.redis
    active_scanner = await get_active_scanner(db, redis_client)
    
    return {"active_scanner": active_scanner}

async def get_active_entities(db: AsyncSession, redis_client) -> list:
    cache_key = "config:active_entities"
    
    # 1. Try fetching from Redis Cache
    cached_entities = await redis_client.get(cache_key)
    if cached_entities:
        if isinstance(cached_entities, bytes):
            cached_entities = cached_entities.decode("utf-8")
        return json.loads(cached_entities)
        
    # 2. Cache Miss: Fetch from Postgres
    result = await db.execute(
        select(AppConfig).where(AppConfig.key == "active_entities")
    )
    config = result.scalars().first()
    
    # Parse the DB string (e.g., '["PERSON", "EMAIL"]') into a Python list
    if config and config.value:
        active_entities = json.loads(config.value)
    else:
        # Absolute fallback if the database is empty
        active_entities = ["PERSON", "ORGANIZATION", "LOCATION", "EMAIL"]
    
    # 3. Save to Redis with a 5-minute (300s) TTL
    await redis_client.setex(cache_key, 300, json.dumps(active_entities))
    
    return active_entities