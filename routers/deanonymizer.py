from fastapi import APIRouter
from presidio_analyzer import RecognizerResult
from presidio_anonymizer import DeanonymizeEngine
from presidio_anonymizer.entities import OperatorConfig, OperatorResult
from utils.vault import redis_client, RedisVaultOperator, RedisUnvaultOperator
from models.models import DeanonymizeRequest

router = APIRouter(prefix="/deanonymize")
deanonymize_engine = DeanonymizeEngine()
deanonymize_engine.add_deanonymizer(RedisUnvaultOperator)

@router.post("")
async def deanonymizer(req: DeanonymizeRequest):
    operator_results = [
        OperatorResult(
            start=item.start,
            end=item.end,
            entity_type=item.entity_type
        )
        for item in req.items
    ]
    deanonymized = deanonymize_engine.deanonymize(text=req.anonymized_text,entities=operator_results,operators={"DEFAULT": OperatorConfig("redis_unvault")})
    return {"deanonymized_text": deanonymized.text}