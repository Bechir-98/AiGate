from typing import List, Optional
from fastapi import APIRouter, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from models.models import AnonymizeRequest, ScanResult, Input
from utils.mapping_service import get_active_mapping
from utils.glinerConfig import update_analyzer_mappings

router = APIRouter(prefix="/scan")

async def sync_analyzers(request: Request, db: AsyncSession, entities: List[str] = None):
    # Retrieve active mapping (cache-aside from Redis/Postgres)
    redis_client = request.app.state.redis
    mapping = await get_active_mapping(db, redis_client)
    
    # Synchronize registered recognizer attributes
    update_analyzer_mappings(request.app.state.gliner_analyzer, mapping, entities)
    update_analyzer_mappings(request.app.state.gliner2_analyzer, mapping, entities)


@router.post("/spacy", response_model=AnonymizeRequest)
async def scan_spacy(request: Request, input_data: Input):
    # Récupération de l'instance SpaCy depuis le lifespan
    spacy_analyzer = request.app.state.spacy_analyzer
    
    result = spacy_analyzer.analyze(
        text=input_data.content,
        language="en"
    )
    scan_results = [
        ScanResult(entity_type=r.entity_type, start=r.start, end=r.end, score=r.score) 
        for r in result
    ]
    return AnonymizeRequest(text=input_data.content, results=scan_results)


@router.post("/gliner1", response_model=AnonymizeRequest)
async def scan_gliner(request: Request, input_data: Input, db: AsyncSession = Depends(get_db)):
    await sync_analyzers(request, db, input_data.entities)
    # Récupération de l'instance GLiNER 1 depuis le lifespan
    gliner_analyzer = request.app.state.gliner_analyzer
    
    result = gliner_analyzer.analyze(
        text=input_data.content,
        language="en",
        entities=input_data.entities
    )
    scan_results = [
        ScanResult(entity_type=r.entity_type, start=r.start, end=r.end, score=r.score) 
        for r in result
    ]
    return AnonymizeRequest(text=input_data.content, results=scan_results)


@router.post("/gliner2", response_model=AnonymizeRequest)
async def scan_gliner2(request: Request, input_data: Input, db: AsyncSession = Depends(get_db)):
    await sync_analyzers(request, db, input_data.entities)
    # Récupération de l'instance GLiNER 2 depuis le lifespan
    gliner2_analyzer = request.app.state.gliner2_analyzer
    
    result = gliner2_analyzer.analyze(
        text=input_data.content,
        language="en",
        entities=input_data.entities
    )
    scan_results = [
        ScanResult(entity_type=r.entity_type, start=r.start, end=r.end, score=r.score) 
        for r in result
    ]
    return AnonymizeRequest(text=input_data.content, results=scan_results)