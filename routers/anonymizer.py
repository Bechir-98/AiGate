from presidio_anonymizer import AnonymizerEngine
from fastapi import APIRouter
from presidio_analyzer import RecognizerResult
from utils.models import AnonymizeRequest,DeanonymizeRequest,AnonymizedItem
from utils.vault import RedisVaultOperator
from presidio_anonymizer.entities import OperatorConfig

anonymizer = AnonymizerEngine()
anonymizer.add_anonymizer(RedisVaultOperator)

router = APIRouter(prefix="/anonymize")
@router.post("")
async def anonymize (req:AnonymizeRequest):
    analyzer_results = [
        RecognizerResult(entity_type=r.entity_type, start=r.start, end=r.end, score=r.score)
        for r in req.results
    ]
    anonymized= anonymizer.anonymize(
        text=req.text.content,
        analyzer_results=analyzer_results,
        operators={"DEFAULT": OperatorConfig("redis_vault")})
    #map to match 
    mapped_items = [
        AnonymizedItem(
            start=item.start,
            end=item.end,
            entity_type=item.entity_type,
            operator=item.operator
        )
        for item in anonymized.items
    ]
    deanonymize_request = DeanonymizeRequest(anonymized_text=anonymized.text,items=mapped_items)
    return deanonymize_request
    
