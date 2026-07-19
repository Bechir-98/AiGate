import asyncio
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, HTTPException, status
from presidio_anonymizer import AnonymizerEngine
from presidio_analyzer import RecognizerResult
from presidio_anonymizer.entities import OperatorConfig

from models.models import AnonymizeRequest, DeanonymizeRequest, AnonymizedItem
from utils.vault import RedisVaultOperator

# Instantiate global anonymization engine and wire up custom storage hooks
anonymizer = AnonymizerEngine()
anonymizer.add_anonymizer(RedisVaultOperator)

router = APIRouter(prefix="/anonymize")

# Dedicated high-capacity thread pool optimized for network I/O operations.
# Network waits don't consume CPU, so we can safely maintain a larger worker count.
_io_network_pool = ThreadPoolExecutor(max_workers=32, thread_name_prefix="anonymizer_io")


@router.post("", response_model=DeanonymizeRequest)
async def anonymize(req: AnonymizeRequest):
    """
    Transforms PII inside raw text with secure vault references.
    Offloads synchronous execution and network I/O safely to an isolated thread pool.
    """
    # 1. Map incoming validation models into Presidio engine types
    analyzer_results = [
        RecognizerResult(entity_type=r.entity_type, start=r.start, end=r.end, score=r.score)
        for r in req.results
    ]

    loop = asyncio.get_event_loop()
    
    try:
        # 2. Execute I/O-bound tokenization within our isolated pool
        anonymized = await loop.run_in_executor(
            _io_network_pool,
            lambda: anonymizer.anonymize(
                text=req.text,
                analyzer_results=analyzer_results,
                operators={"DEFAULT": OperatorConfig("redis_vault")}
            )
        )
    except Exception as e:
        # 3. Guard against Redis connection drops or processing faults
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Vault Anonymization Layer failed: {str(e)}"
        )

    # 4. Format structural maps showing exactly what was swapped
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