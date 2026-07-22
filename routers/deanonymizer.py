import asyncio
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, Request, HTTPException, status
from pydantic import BaseModel
from presidio_anonymizer import DeanonymizeEngine
from presidio_anonymizer.entities import OperatorConfig, OperatorResult

from config import settings, VAULT_TOKEN_PATTERN
from utils.vault import RedisUnvaultOperator
from models.models import DeanonymizeRequest, LLMDeanonymizeRequest

logger = logging.getLogger("gateway_deanonymizer")
router = APIRouter(prefix="/deanonymize", tags=["Deanonymization Engine"])

deanonymize_engine = DeanonymizeEngine()
deanonymize_engine.add_deanonymizer(RedisUnvaultOperator)

_io_unvault_pool = ThreadPoolExecutor(max_workers=settings.DEANONYMIZER_THREAD_POOL_SIZE, thread_name_prefix="unvault_span_io")


class DeanonymizeResponse(BaseModel):
    deanonymized_text: str


async def deanonymize_text(text: str, redis_client) -> str:
    """
    Scans unstructured text for vault tokens, resolves them via a batched
    Redis pipeline, and returns the reconstructed string.
    """
    raw_tokens = VAULT_TOKEN_PATTERN.findall(text)
    if not raw_tokens:
        return text

    def normalize(t: str) -> str:
        return t.replace("&lt;", "<").replace("&gt;", ">").replace("&LT;", "<").replace("&GT;", ">")

    unique_raw = list(dict.fromkeys(raw_tokens))
    normalized_to_raw = {normalize(token): token for token in unique_raw}
    unique_normalized = list(normalized_to_raw.keys())

    try:
        pipe = redis_client.pipeline()
        for token in unique_normalized:
            pipe.get(token)
            pipe.expire(token, settings.VAULT_TTL)
        pipeline_results = await pipe.execute()
    except Exception as e:
        logger.error(f"Redis pipeline aborted: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Vault communication failure during data reconstruction."
        )

    token_map: dict[str, str] = {}

    for i, norm_token in enumerate(unique_normalized):
        get_result = pipeline_results[i * 2]
        raw_source = normalized_to_raw[norm_token]

        if not get_result:
            logger.warning(f"Token {norm_token} not found in vault (possible expiration).")
            continue

        try:
            payload = json.loads(get_result)
            original = payload["original_text"]

            token_map[raw_source] = original
            token_map[norm_token] = original
            token_map[raw_source.lower()] = original
            token_map[raw_source.upper()] = original

        except (json.JSONDecodeError, KeyError, TypeError) as parse_err:
            logger.error(f"Failed parsing vault payload for token {norm_token}: {parse_err}")
            continue

    def replace_token(match) -> str:
        matched_str = match.group(0)
        return token_map.get(matched_str,
               token_map.get(normalize(matched_str),
               token_map.get(matched_str.lower(), matched_str)))

    return VAULT_TOKEN_PATTERN.sub(replace_token, text)


@router.post("/test", response_model=DeanonymizeResponse)
async def deanonymizer_test(req: DeanonymizeRequest):
    operator_results = [
        OperatorResult(start=item.start, end=item.end, entity_type=item.entity_type)
        for item in req.items
    ]

    loop = asyncio.get_running_loop()
    try:
        deanonymized = await loop.run_in_executor(
            _io_unvault_pool,
            lambda: deanonymize_engine.deanonymize(
                text=req.anonymized_text,
                entities=operator_results,
                operators={"DEFAULT": OperatorConfig("redis_unvault")}
            )
        )
        return DeanonymizeResponse(deanonymized_text=deanonymized.text)
    except Exception as e:
        logger.error(f"Span deanonymization failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Span-based text reconstruction failed."
        )


@router.post("", response_model=DeanonymizeResponse)
async def deanonymizer_llm_route(req: LLMDeanonymizeRequest, request: Request):
    result = await deanonymize_text(req.text, request.app.state.redis)
    return DeanonymizeResponse(deanonymized_text=result)