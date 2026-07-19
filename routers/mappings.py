import re
import logging
import asyncio
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from pydantic import BaseModel, ConfigDict, Field

from database import get_db
from models.db_models import DBEntityMapping

logger = logging.getLogger("gateway_mappings")
router = APIRouter(prefix="/mappings", tags=["Entity Mappings"])

# ==========================================
# 1. SANITIZED PYDANTIC MODELS
# ==========================================

class MappingCreate(BaseModel):
    # Enforces that labels cannot be empty strings or just empty spaces
    gliner_label: str = Field(..., min_length=1, description="The natural label used by GLiNER models")

class MappingResponse(BaseModel):
    id: int
    gliner_label: str
    presidio_label: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

class MappingUpdate(BaseModel):
    gliner_label: Optional[str] = Field(None, min_length=1)
    is_active: Optional[bool] = None

# ==========================================
# 2. HELPER UTILITIES
# ==========================================

def generate_presidio_label(gliner_label: str) -> str:
    """Transforms 'Credit Card' or 'passport-id' into clean 'CREDIT_CARD' or 'PASSPORT_ID'."""
    label = gliner_label.strip().upper()
    return re.sub(r'[\s\-]+', '_', label)


async def safe_invalidate_cache(request: Request):
    """
    Safely clears the Redis cache. Wraps network operations in a try-except 
    block to avoid breaking database commits if the cache experiences a blip.
    """
    try:
        redis_client = request.app.state.redis
        await redis_client.delete("gliner_entity_mapping")
        logger.info("Configuration cache successfully invalidated in Redis.")
    except Exception as e:
        # Log the failure but don't crash the route—the database is already secure
        logger.error(f"Cache invalidation failed down-line: {e}. Stale data may persist until manual flush.")

# ==========================================
# 3. CRITICAL OPERATIONAL ROUTES
# ==========================================

@router.get("/", response_model=List[MappingResponse])
async def list_mappings(db: AsyncSession = Depends(get_db)):
    """Retrieves all active and inactive entities ordered deterministically by ID."""
    result = await db.execute(select(DBEntityMapping).order_by(DBEntityMapping.id.asc()))
    return result.scalars().all()


@router.post("/", response_model=MappingResponse, status_code=status.HTTP_201_CREATED)
async def create_mapping(
    mapping_in: MappingCreate, 
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Registers a new custom scanning entity and autogenerates its Presidio mapping."""
    gliner_label_original = mapping_in.gliner_label.strip()
    gliner_label_lower = gliner_label_original.lower()
    
    # Case-insensitive structural validation check
    result = await db.execute(
        select(DBEntityMapping).where(func.lower(DBEntityMapping.gliner_label) == gliner_label_lower)
    )
    if result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="A mapping rule with this GLiNER label already exists."
        )

    auto_presidio_label = generate_presidio_label(gliner_label_original)

    new_mapping = DBEntityMapping(
        gliner_label=gliner_label_original,
        presidio_label=auto_presidio_label,
        is_active=True
    )
    
    db.add(new_mapping)
    await db.commit()
    await db.refresh(new_mapping)
    
    # Fire cache removal safely
    await safe_invalidate_cache(request)
    return new_mapping


@router.patch("/{mapping_id}", response_model=MappingResponse)
async def update_mapping(
    mapping_id: int, 
    mapping_in: MappingUpdate, 
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Modifies label details or toggles scanning states for an existing entity."""
    result = await db.execute(select(DBEntityMapping).where(DBEntityMapping.id == mapping_id))
    mapping = result.scalars().first()
    
    if not mapping:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target mapping record not found.")

    if mapping_in.gliner_label is not None:
        gliner_label_original = mapping_in.gliner_label.strip()
        gliner_label_lower = gliner_label_original.lower()
        
        # Enforce uniqueness rule across all OTHER rows
        check_exist = await db.execute(
            select(DBEntityMapping).where(
                (func.lower(DBEntityMapping.gliner_label) == gliner_label_lower) & 
                (DBEntityMapping.id != mapping_id)
            )
        )
        if check_exist.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="This target label is already occupied by another entry."
            )
            
        mapping.gliner_label = gliner_label_original
        mapping.presidio_label = generate_presidio_label(gliner_label_original)

    if mapping_in.is_active is not None:
        mapping.is_active = mapping_in.is_active

    await db.commit()
    await db.refresh(mapping)
    await safe_invalidate_cache(request)

    return mapping


@router.delete("/{mapping_id}")
async def delete_mapping(
    mapping_id: int, 
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """Permanently drops an entry from the tracking ecosystem."""
    result = await db.execute(select(DBEntityMapping).where(DBEntityMapping.id == mapping_id))
    mapping = result.scalars().first()
    
    if not mapping:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target mapping record not found.")

    await db.delete(mapping)
    await db.commit()

    await safe_invalidate_cache(request)
    return {"status": "success", "message": f"Entity mapping rule '{mapping.gliner_label}' successfully purged."}