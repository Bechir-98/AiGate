import asyncio
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Callable, Any
from fastapi import APIRouter, Request, Depends, BackgroundTasks, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.models import AnonymizeRequest, ScanResult, Input
from services.mapping_service import get_active_mapping
from utils.glinerConfig import update_analyzer_mappings
from services.audit_service import audit_detected_labels

router = APIRouter(prefix="/scan")

# --- Concurrency Management ---
_analyzer_lock = asyncio.Lock()
_cached_state_hash: str = ""

# --- Thread Management ---
_ai_thread_pool = ThreadPoolExecutor(max_workers=8)


async def sync_analyzers(request: Request, db: AsyncSession, entities: Optional[List[str]] = None):
    """Safely mutates shared analyzer state using deterministic hashing and locking."""
    global _cached_state_hash

    redis_client = request.app.state.redis
    mapping = await get_active_mapping(db, redis_client)

    state_data = json.dumps(mapping, sort_keys=True) + json.dumps(sorted(entities or []))
    new_hash = hashlib.md5(state_data.encode()).hexdigest()

    if new_hash == _cached_state_hash:
        return

    async with _analyzer_lock:
        if new_hash == _cached_state_hash:
            return

        update_analyzer_mappings(request.app.state.gliner_analyzer, mapping, entities)
        update_analyzer_mappings(request.app.state.gliner2_analyzer, mapping, entities)
        _cached_state_hash = new_hash


async def execute_scan(
    inference_func: Callable[[], Any],
    content: str,
    background_tasks: BackgroundTasks
) -> AnonymizeRequest:
    """
    Centralized helper function to offload AI inference to a dedicated thread pool,
    format the results, and trigger background auditing.
    """
    loop = asyncio.get_event_loop()
    
    try:
        result = await loop.run_in_executor(_ai_thread_pool, inference_func)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI Inference Engine failed: {str(e)}")

    scan_results = [
        ScanResult(entity_type=r.entity_type, start=r.start, end=r.end, score=r.score)
        for r in result
    ]
    
    detected_labels = [r.entity_type for r in scan_results]
    
    if detected_labels:
        background_tasks.add_task(audit_detected_labels, detected_labels)

    return AnonymizeRequest(text=content, results=scan_results)


@router.post("/spacy", response_model=AnonymizeRequest)
async def scan_spacy(
    request: Request,
    input_data: Input,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    spacy_analyzer = request.app.state.spacy_analyzer
    return await execute_scan(
        inference_func=lambda: spacy_analyzer.analyze(text=input_data.content, language="en"),
        content=input_data.content,
        background_tasks=background_tasks
    )


@router.post("/gliner1", response_model=AnonymizeRequest)
async def scan_gliner(
    request: Request,
    input_data: Input,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    await sync_analyzers(request, db, input_data.entities)
    gliner_analyzer = request.app.state.gliner_analyzer
    return await execute_scan(
        inference_func=lambda: gliner_analyzer.analyze(
            text=input_data.content,
            language="en",
            entities=input_data.entities
        ),
        content=input_data.content,
        background_tasks=background_tasks
    )


@router.post("/gliner2", response_model=AnonymizeRequest)
async def scan_gliner2(
    request: Request,
    input_data: Input,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    await sync_analyzers(request, db, input_data.entities)
    gliner2_analyzer = request.app.state.gliner2_analyzer
    return await execute_scan(
        inference_func=lambda: gliner2_analyzer.analyze(
            text=input_data.content,
            language="en",
            entities=input_data.entities
        ),
        content=input_data.content,
        background_tasks=background_tasks
    )