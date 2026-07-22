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


class MappingCreate(BaseModel):
    gliner_label: str = Field(..., min_length=1)

class MappingResponse(BaseModel):
    id: int
    gliner_label: str
    presidio_label: str
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

class MappingUpdate(BaseModel):
    gliner_label: Optional[str] = Field(None, min_length=1)
    is_active: Optional[bool] = None


def generate_presidio_label(gliner_label: str) -> str:
    label = gliner_label.strip().upper()
    return re.sub(r'[\s\-]+', '_', label)


async def safe_invalidate_cache(request: Request):
    try:
        redis_client = request.app.state.redis
        await redis_client.delete("gliner_entity_mapping")
        logger.info("Mapping cache invalidated.")
    except Exception as e:
        logger.error(f"Cache invalidation failed: {e}")


@router.get("/", response_model=List[MappingResponse])
async def list_mappings(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DBEntityMapping).order_by(DBEntityMapping.id.asc()))
    return result.scalars().all()


@router.post("/", response_model=MappingResponse, status_code=status.HTTP_201_CREATED)
async def create_mapping(
    mapping_in: MappingCreate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    gliner_label_original = mapping_in.gliner_label.strip()
    gliner_label_lower = gliner_label_original.lower()

    result = await db.execute(
        select(DBEntityMapping).where(func.lower(DBEntityMapping.gliner_label) == gliner_label_lower)
    )
    if result.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="A mapping with this GLiNER label already exists."
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

    await safe_invalidate_cache(request)
    return new_mapping


@router.patch("/{mapping_id}", response_model=MappingResponse)
async def update_mapping(
    mapping_id: int,
    mapping_in: MappingUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    result = await db.execute(select(DBEntityMapping).where(DBEntityMapping.id == mapping_id))
    mapping = result.scalars().first()

    if not mapping:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mapping not found.")

    if mapping_in.gliner_label is not None:
        gliner_label_original = mapping_in.gliner_label.strip()
        gliner_label_lower = gliner_label_original.lower()

        check_exist = await db.execute(
            select(DBEntityMapping).where(
                (func.lower(DBEntityMapping.gliner_label) == gliner_label_lower) &
                (DBEntityMapping.id != mapping_id)
            )
        )
        if check_exist.scalars().first():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This label is already in use by another entry."
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
    result = await db.execute(select(DBEntityMapping).where(DBEntityMapping.id == mapping_id))
    mapping = result.scalars().first()

    if not mapping:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mapping not found.")

    await db.delete(mapping)
    await db.commit()

    await safe_invalidate_cache(request)
    return {"status": "success", "message": f"Mapping '{mapping.gliner_label}' deleted."}