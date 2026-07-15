from fastapi import APIRouter
from presidio_analyzer import AnalyzerEngine
from utils.glinerConfig import create_gliner_analyzer, create_gliner2_analyzer
from utils.models import AnonymizeRequest, ScanResult,Input
router = APIRouter(prefix="/scan")

spacy_analyzer = AnalyzerEngine()
gliner_analyzer = create_gliner_analyzer()
gliner2_analyzer = create_gliner2_analyzer()


@router.post("/spacy",response_model=AnonymizeRequest)
async def scan_spacy(text: Input):
    result = spacy_analyzer.analyze(
        text=text.content,
        language="en"
    )
    result = [ScanResult(entity_type=r.entity_type, start=r.start, end=r.end, score=r.score ) for r in result]
    return AnonymizeRequest(text=text,results=result)

@router.post("/gliner1",response_model=AnonymizeRequest)
async def scan_gliner(text: Input):
    result = gliner_analyzer.analyze(
        text=text.content,
        language="en"
    )
    result = [ScanResult(entity_type=r.entity_type, start=r.start, end=r.end, score=r.score) for r in result]
    return AnonymizeRequest(text=text,results=result)
    
@router.post("/gliner2",response_model=AnonymizeRequest)
async def scan_gliner2(text: Input):
    result = gliner2_analyzer.analyze(
        text=text.content,
        language="en"
    )
    result = [ScanResult(entity_type=r.entity_type, start=r.start, end=r.end, score=r.score) for r in result]
    return AnonymizeRequest(text=text,results=result)
