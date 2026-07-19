import asyncio
import json
import re
import logging
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, Request, HTTPException, status
from pydantic import BaseModel
from presidio_anonymizer import DeanonymizeEngine
from presidio_anonymizer.entities import OperatorConfig, OperatorResult

from utils.vault import RedisUnvaultOperator
from models.models import DeanonymizeRequest, LLMDeanonymizeRequest

logger = logging.getLogger("gateway_deanonymizer")
router = APIRouter(prefix="/deanonymize", tags=["Deanonymization Engine"])

# Initialize structural engine and wire synchronous un-vaulting routines
deanonymize_engine = DeanonymizeEngine()
deanonymize_engine.add_deanonymizer(RedisUnvaultOperator)

# Pre-compiled regular expression checking for angle bracket variations and HTML encodings
TOKEN_PATTERN = re.compile(r"(?:<|&lt;)[A-Za-z_]+_[a-f0-9]{6}(?:>|&gt;)", re.IGNORECASE)

# Dedicated thread pool for synchronous span-based Presidio lookups
_io_unvault_pool = ThreadPoolExecutor(max_workers=16, thread_name_prefix="unvault_span_io")


# ==========================================
# OUTBOUND PYDANTIC RESPONSES
# ==========================================
class DeanonymizeResponse(BaseModel):
    deanonymized_text: str


# ==========================================
# RE-IDENTIFICATION LOGIC
# ==========================================

async def deanonymize_text(text: str, redis_client) -> str:
    """
    Parses unstructured strings for security vault tokens, pulls their
    real values via an optimized Redis pipeline transaction, and returns
    reconstructed natural language.
    """
    raw_tokens = TOKEN_PATTERN.findall(text)
    if not raw_tokens:
        return text

    def normalize(t: str) -> str:
        """Standardizes bracket characters, making lookups case-agnostic to HTML entities."""
        return t.replace("&lt;", "<").replace("&gt;", ">").replace("&LT;", "<").replace("&GT;", ">")

    # De-duplicate raw tokens preserving their discovery order
    unique_raw = list(dict.fromkeys(raw_tokens))
    
    # Map raw discovered tokens to their pure normalized lookups
    normalized_to_raw = {normalize(token): token for token in unique_raw}
    unique_normalized = list(normalized_to_raw.keys())

    try:
        # Execute batch lookup and sliding window TTL renewals in one trip
        pipe = redis_client.pipeline()
        for token in unique_normalized:
            pipe.get(token)
            pipe.expire(token, 1800)  # Reset expiry to 30 minutes
        pipeline_results = await pipe.execute()
    except Exception as e:
        logger.error(f"Redis pipeline transaction aborted: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Vault communication failure during data reconstruction."
        )

    token_map: dict[str, str] = {}
    
    for i, norm_token in enumerate(unique_normalized):
        get_result = pipeline_results[i * 2]
        raw_source = normalized_to_raw[norm_token]
        
        if not get_result:
            # Token missing from cache (expired TTL or altered state)
            logger.warning(f"Security token {norm_token} was not found in the vault store (possible expiration).")
            continue
            
        try:
            payload = json.loads(get_result)
            original = payload["original_text"]
            
            # Seed the map with every single potential variation the regex could catch
            token_map[raw_source] = original
            token_map[norm_token] = original
            # Also cover variations with basic character casings
            token_map[raw_source.lower()] = original
            token_map[raw_source.upper()] = original
            
        except (json.JSONDecodeError, KeyError, TypeError) as parse_err:
            logger.error(f"Failed parsing cache payload for token {norm_token}: {parse_err}")
            continue

    def replace_token(match: re.Match) -> str:
        matched_str = match.group(0)
        # Attempt direct match, normalized check, or fall back gracefully to the token string
        return token_map.get(matched_str, 
               token_map.get(normalize(matched_str), 
               token_map.get(matched_str.lower(), matched_str)))

    return TOKEN_PATTERN.sub(replace_token, text)


# ==========================================
# ENDPOINTS
# ==========================================

@router.post("/test", response_model=DeanonymizeResponse)
async def deanonymizer_test(req: DeanonymizeRequest):
    """Structured deanonymization using Presidio's engine (for span verification)."""
    operator_results = [
        OperatorResult(start=item.start, end=item.end, entity_type=item.entity_type)
        for item in req.items
    ]
    
    loop = asyncio.get_event_loop()
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
        logger.error(f"Synchronous span deanonymization engine failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal text span reconstruction engine failed."
        )


@router.post("", response_model=DeanonymizeResponse)
async def deanonymizer_llm_route(req: LLMDeanonymizeRequest, request: Request):
    """
    Asynchronously reconstructs unstructured text fields returned by LLM instances.
    Safely reads entries through non-blocking batch cache retrieval.
    """
    result = await deanonymize_text(req.text, request.app.state.redis)
    return DeanonymizeResponse(deanonymized_text=result)