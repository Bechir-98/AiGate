from fastapi import APIRouter
from presidio_analyzer import AnalyzerEngine
from enum import Enum
from pydantic import BaseModel
from utils.glinerConfig import create_gliner_analyzer, create_gliner2_analyzer

router = APIRouter(prefix="/scan")

class Toscan(BaseModel):
    content: str
    type: int | None = None

class Result(BaseModel):
    entity_type: str
    start: int
    end: int
    score: float

spacy_analyzer = AnalyzerEngine()
gliner_analyzer = create_gliner_analyzer()
gliner2_analyzer = create_gliner2_analyzer()

@router.post("/spacy")
async def scan_spacy(text: Toscan):
    result = spacy_analyzer.analyze(
        text=text.content,
        language="en"
    )
    result = [Result(entity_type=r.entity_type, start=r.start, end=r.end, score=r.score) for r in result]
    return result

@router.post("/gliner1")
async def scan_gliner(text: Toscan):
    result = gliner_analyzer.analyze(
        text=text.content,
        language="en"
    )
    result = [Result(entity_type=r.entity_type, start=r.start, end=r.end, score=r.score) for r in result]
    return result
    
@router.post("/gliner2")
async def scan_gliner2(text: Toscan):
    result = gliner2_analyzer.analyze(
        text=text.content,
        language="en"
    )
    result = [Result(entity_type=r.entity_type, start=r.start, end=r.end, score=r.score) for r in result]
    return result