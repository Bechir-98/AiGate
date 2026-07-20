from fastapi import APIRouter, Request, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.models import AnonymizeRequest, Input
from scanners.input_scanners.pii_scanner import SpacyScanner, Gliner1Scanner, Gliner2Scanner

router = APIRouter(prefix="/scan", tags=["Scanner"])

@router.post("/spacy", response_model=AnonymizeRequest)
async def scan_spacy(
    request: Request,
    input_data: Input,
    background_tasks: BackgroundTasks
):
    scanner = SpacyScanner(analyzer=request.app.state.spacy_analyzer)
    return await scanner.scan_text(
        content=input_data.content,
        background_tasks=background_tasks
    )


@router.post("/gliner1", response_model=AnonymizeRequest)
async def scan_gliner1(
    request: Request,
    input_data: Input,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    scanner = Gliner1Scanner(analyzer=request.app.state.gliner_analyzer)
    return await scanner.scan_text(
        content=input_data.content,
        entities=input_data.entities,
        app_state=request.app.state,
        db=db,
        background_tasks=background_tasks
    )


@router.post("/gliner2", response_model=AnonymizeRequest)
async def scan_gliner2(
    request: Request,
    input_data: Input,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    scanner = Gliner2Scanner(analyzer=request.app.state.gliner2_analyzer)
    return await scanner.scan_text(
        content=input_data.content,
        entities=input_data.entities,
        app_state=request.app.state,
        db=db,
        background_tasks=background_tasks
    )