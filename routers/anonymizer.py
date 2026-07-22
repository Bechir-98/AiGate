import asyncio
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, HTTPException, status
from presidio_anonymizer import AnonymizerEngine
from presidio_analyzer import RecognizerResult
from presidio_anonymizer.entities import OperatorConfig

from config import settings
from models.models import AnonymizeRequest, DeanonymizeRequest, AnonymizedItem
from utils.vault import RedisVaultOperator

anonymizer = AnonymizerEngine()
anonymizer.add_anonymizer(RedisVaultOperator)

router = APIRouter(prefix="/anonymize")

_io_network_pool = ThreadPoolExecutor(max_workers=settings.ANONYMIZER_THREAD_POOL_SIZE, thread_name_prefix="anonymizer_io")


@router.post("", response_model=DeanonymizeRequest)
async def anonymize(req: AnonymizeRequest):
    analyzer_results = [
        RecognizerResult(entity_type=r.entity_type, start=r.start, end=r.end, score=r.score)
        for r in req.results
    ]

    loop = asyncio.get_running_loop()

    try:
        anonymized = await loop.run_in_executor(
            _io_network_pool,
            lambda: anonymizer.anonymize(
                text=req.text,
                analyzer_results=analyzer_results,
                operators={"DEFAULT": OperatorConfig("redis_vault")}
            )
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Vault anonymization failed: {str(e)}"
        )

    mapped_items = [
        AnonymizedItem(
            start=item.start,
            end=item.end,
            entity_type=item.entity_type,
            operator=item.operator
        )
        for item in anonymized.items
    ]

    return DeanonymizeRequest(anonymized_text=anonymized.text, items=mapped_items)