import re
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from database import get_db
from models.db_models import DBCustomRegexPattern
from scanners.input_scanners.regex_scanner import clear_compiled_regex_cache

logger = logging.getLogger("gateway_regex_patterns")
router = APIRouter(prefix="/regex-patterns", tags=["Custom Regex Patterns"])


class RegexPatternCreate(BaseModel):
    name: str = Field(..., min_length=1)
    pattern: str = Field(..., min_length=1)
    entity_type: str = Field(..., min_length=1)
    score: float = Field(default=0.85, ge=0.0, le=1.0)

    @field_validator("pattern")
    @classmethod
    def validate_regex(cls, v: str) -> str:
        try:
            re.compile(v)
        except re.error as e:
            raise ValueError(f"Invalid regular expression: {e}")
        return v

    @field_validator("entity_type")
    @classmethod
    def normalize_entity_type(cls, v: str) -> str:
        return re.sub(r"[\s\-]+", "_", v.strip().upper())


class RegexPatternUpdate(BaseModel):
    pattern: Optional[str] = Field(None, min_length=1)
    score: Optional[float] = Field(None, ge=0.0, le=1.0)
    is_active: Optional[bool] = None

    @field_validator("pattern")
    @classmethod
    def validate_regex(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            try:
                re.compile(v)
            except re.error as e:
                raise ValueError(f"Invalid regular expression: {e}")
        return v


class RegexPatternResponse(BaseModel):
    id: int
    name: str
    pattern: str
    entity_type: str
    score: float
    is_active: bool

    model_config = {"from_attributes": True}


async def _invalidate_cache(request: Request) -> None:
    try:
        await request.app.state.redis.delete("custom_regex_patterns")
        clear_compiled_regex_cache()
    except Exception as e:
        logger.warning(f"Failed to invalidate custom regex cache: {e}")


@router.get("/", response_model=List[RegexPatternResponse])
async def list_patterns(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(DBCustomRegexPattern).order_by(DBCustomRegexPattern.id.asc())
    )
    return result.scalars().all()


@router.post("/", response_model=RegexPatternResponse, status_code=status.HTTP_201_CREATED)
async def create_pattern(
    payload: RegexPatternCreate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    name_lower = payload.name.strip().lower()

    existing = await db.execute(
        select(DBCustomRegexPattern).where(
            func.lower(DBCustomRegexPattern.name) == name_lower
        )
    )
    if existing.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A pattern named '{payload.name}' already exists."
        )

    new_pattern = DBCustomRegexPattern(
        name=payload.name.strip(),
        pattern=payload.pattern,
        entity_type=payload.entity_type,
        score=payload.score,
        is_active=True,
    )
    db.add(new_pattern)
    await db.commit()
    await db.refresh(new_pattern)

    await _invalidate_cache(request)
    logger.info(f"Custom regex pattern created: [{new_pattern.name}]")
    return new_pattern


@router.patch("/{pattern_id}", response_model=RegexPatternResponse)
async def update_pattern(
    pattern_id: int,
    payload: RegexPatternUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DBCustomRegexPattern).where(DBCustomRegexPattern.id == pattern_id)
    )
    record = result.scalars().first()

    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pattern not found.")

    if payload.pattern is not None:
        record.pattern = payload.pattern
    if payload.score is not None:
        record.score = payload.score
    if payload.is_active is not None:
        record.is_active = payload.is_active

    await db.commit()
    await db.refresh(record)

    await _invalidate_cache(request)
    logger.info(f"Custom regex pattern updated: [{record.name}] active={record.is_active}")
    return record


@router.delete("/{pattern_id}", status_code=status.HTTP_200_OK)
async def delete_pattern(
    pattern_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DBCustomRegexPattern).where(DBCustomRegexPattern.id == pattern_id)
    )
    record = result.scalars().first()

    if not record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pattern not found.")

    name = record.name
    await db.delete(record)
    await db.commit()

    await _invalidate_cache(request)
    logger.info(f"Custom regex pattern deleted: [{name}]")
    return {"status": "success", "message": f"Pattern '{name}' removed."}