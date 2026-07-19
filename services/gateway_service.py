import os
import re
import uuid
import json
import httpx
import logging
from fastapi import Request, BackgroundTasks, HTTPException, status
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from models.models import Input, GatewayResponse
from routers.scanner import scan_spacy, scan_gliner, scan_gliner2
from routers.anonymizer import anonymize
from routers.deanonymizer import deanonymize_text
from services.config_service import get_active_scanner

logger = logging.getLogger("gateway_service")

# ==========================================
# INFRASTRUCTURE & LLM DRIVERS
# ==========================================

LITELLM_API_URL = os.getenv("LITELLM_API_URL", "http://litellm:4000/v1")

client = AsyncOpenAI(
    base_url=LITELLM_API_URL,
    api_key="litellm-doesnt-need-a-key-here",
    timeout=httpx.Timeout(60.0, connect=5.0),
    max_retries=2,
)

_VAULT_TOKEN_PATTERN = re.compile(r"<[A-Za-z_]+_[a-f0-9]{6}>", re.IGNORECASE)


# ==========================================
# MEMORY MANAGEMENT HELPERS
# ==========================================

async def _refresh_history_token_ttls(redis_client, history: list) -> None:
    """Slides all vault token TTLs forward to keep mappings alive during long sessions."""
    tokens: set[str] = set()
    for msg in history:
        tokens.update(_VAULT_TOKEN_PATTERN.findall(msg.get("content", "")))
        
    if tokens:
        try:
            pipe = redis_client.pipeline()
            for token in tokens:
                pipe.expire(token, 1800)
            await pipe.execute()
        except Exception as e:
            logger.warning(f"Failed to refresh history TTLs: {e}. Tokens may prematurely expire.")


async def get_chat_history(redis_client, session_id: str) -> list:
    history_key = f"session:{session_id}:history"
    data = await redis_client.get(history_key)
    return json.loads(data) if data else []


async def save_chat_history(redis_client, session_id: str, history: list):
    history_key = f"session:{session_id}:history"
    trimmed_history = history[-10:]
    await _refresh_history_token_ttls(redis_client, trimmed_history)
    await redis_client.setex(history_key, 1800, json.dumps(trimmed_history))


# ==========================================
# CORE SERVICE LOGIC
# ==========================================

async def process_gateway_chat(
    request: Request,
    input_data: Input,
    background_tasks: BackgroundTasks,
    db: AsyncSession
) -> GatewayResponse:
    """
    Executes the full anonymization, LLM proxy, and deanonymization lifecycle.
    """
    redis_client = request.app.state.redis
    session_id = input_data.session_id or f"sess_{uuid.uuid4().hex[:12]}"

    # 1. Dynamic Engine Routing & Scanning Phase
    active_scanner = await get_active_scanner(db, redis_client)

    try:
        if active_scanner == "gliner1":
            scan_result_payload = await scan_gliner(request, input_data, background_tasks, db)
        elif active_scanner == "gliner2":
            scan_result_payload = await scan_gliner2(request, input_data, background_tasks, db)
        else:
            scan_result_payload = await scan_spacy(request, input_data, background_tasks, db)
    except Exception as e:
        logger.error(f"Scanning engine fault: {e}")
        raise HTTPException(status_code=500, detail="Data scanning phase failed.")

    # 2. Vault Tokenization Phase
    try:
        anonymize_result = await anonymize(scan_result_payload)
        safe_prompt = anonymize_result.anonymized_text
    except Exception as e:
        logger.error(f"Anonymization fault: {e}")
        raise HTTPException(status_code=500, detail="Data tokenization phase failed.")

    # 3. Contextual History Loading
    history = await get_chat_history(redis_client, session_id)

    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful assistant. To protect user privacy, sensitive data "
                "in the prompt has been replaced with tokens like <PERSON_xxxxxx>. "
                "Treat these tokens as if they are the actual, valid names of people or companies. "
                "Do not mention that details are missing, do not complain about placeholders, "
                "and do not try to guess the original values. Just write your response naturally, "
                "using the tokens exactly as they are."
            )
        }
    ]
    messages.extend(history)
    messages.append({"role": "user", "content": safe_prompt})

    # 4. Upstream LiteLLM Execution Phase
    try:
        response = await client.chat.completions.create(
            model="gateway-chat",
            messages=messages
        )
        if not response.choices:
            raise ValueError("Upstream model returned an empty response array.")
        llm_response_raw = response.choices[0].message.content or ""
    except Exception as exc:
        logger.error(f"Upstream execution fault: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, 
            detail=f"LiteLLM Network request failed: {exc}"
        )

    # 5. Secure History Persistence
    history.append({"role": "user", "content": safe_prompt})
    history.append({"role": "assistant", "content": llm_response_raw})
    await save_chat_history(redis_client, session_id, history)

    # 6. Reverse De-Anonymization Phase
    try:
        final_response = await deanonymize_text(llm_response_raw, redis_client)
    except Exception as e:
        logger.error(f"Reconstruction fault: {e}")
        raise HTTPException(status_code=500, detail="Final text reconstruction phase failed.")

    return GatewayResponse(
        original_prompt=input_data.content,
        safe_prompt=safe_prompt,
        llm_response_raw=llm_response_raw,
        final_response=final_response,
        session_id=session_id
    )