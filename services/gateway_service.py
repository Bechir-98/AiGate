import os
import uuid
import json
import httpx
import logging
from fastapi import Request, BackgroundTasks, HTTPException, status
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings, VAULT_TOKEN_PATTERN
from models.models import Input, GatewayResponse
from routers.config import get_active_scanners
from routers.deanonymizer import deanonymize_text
from scanners.pipeline import security_pipeline
from scanners.scanner import ScannerStage

logger = logging.getLogger("gateway_service")

client = AsyncOpenAI(
    base_url=settings.LITELLM_API_URL,
    api_key=settings.LITELLM_API_KEY,
    timeout=httpx.Timeout(settings.LITELLM_TIMEOUT, connect=settings.LITELLM_CONNECT_TIMEOUT),
    max_retries=settings.LITELLM_MAX_RETRIES,
)


async def _refresh_history_token_ttls(redis_client, history: list) -> None:
    tokens: set[str] = set()
    for msg in history:
        tokens.update(VAULT_TOKEN_PATTERN.findall(msg.get("content", "")))

    if tokens:
        try:
            pipe = redis_client.pipeline()
            for token in tokens:
                pipe.expire(token, settings.VAULT_TTL)
            await pipe.execute()
        except Exception as e:
            logger.warning(f"Failed to refresh history TTLs: {e}")


async def get_chat_history(redis_client, session_id: str) -> list:
    history_key = f"session:{session_id}:history"
    data = await redis_client.get(history_key)
    return json.loads(data) if data else []


async def save_chat_history(redis_client, session_id: str, history: list):
    history_key = f"session:{session_id}:history"
    trimmed_history = history[-10:]
    await _refresh_history_token_ttls(redis_client, trimmed_history)
    await redis_client.setex(history_key, settings.VAULT_TTL, json.dumps(trimmed_history))


async def process_gateway_chat(
    request: Request,
    input_data: Input,
    background_tasks: BackgroundTasks,
    db: AsyncSession
) -> GatewayResponse:
    """
    Runs the full pipeline: input scanning, PII anonymization, LLM proxy,
    output guardrails, and deanonymization.
    """
    redis_client = request.app.state.redis
    session_id = input_data.session_id or f"sess_{uuid.uuid4().hex[:12]}"

    active_scanners = await get_active_scanners(db, redis_client)

    try:
        safe_prompt, input_telemetry = await security_pipeline.execute_stage(
            text=input_data.content,
            stage=ScannerStage.INPUT,
            active_scanners=active_scanners,
            db=db,
            background_tasks=background_tasks,
            app_state=request.app.state,
            entities=getattr(input_data, "entities", None)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Input pipeline fault: {e}")
        raise HTTPException(status_code=500, detail="Input scanning phase failed.")

    history = await get_chat_history(redis_client, session_id)

    messages = [
        {
            "role": "system",
            "content": "You are a helpful assistant. Always respond naturally and completely."
        }
    ]
    messages.extend(history)
    messages.append({"role": "user", "content": safe_prompt})

    try:
        response = await client.chat.completions.create(
            model="gateway-chat",
            messages=messages
        )
        if not response.choices:
            raise ValueError("Upstream model returned an empty choice array.")
        llm_response_raw = response.choices[0].message.content or ""
    except Exception as exc:
        logger.error(f"Upstream execution fault: {exc}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"LiteLLM request failed: {exc}"
        )

    try:
        checked_response, output_telemetry = await security_pipeline.execute_stage(
            text=llm_response_raw,
            stage=ScannerStage.OUTPUT,
            active_scanners=active_scanners,
            db=db,
            background_tasks=background_tasks,
            app_state=request.app.state
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Output pipeline fault: {e}")
        raise HTTPException(status_code=500, detail="Output security validation failed.")

    history.append({"role": "user", "content": safe_prompt})
    history.append({"role": "assistant", "content": llm_response_raw})
    await save_chat_history(redis_client, session_id, history)

    try:
        final_response = await deanonymize_text(checked_response, redis_client)
    except Exception as e:
        logger.error(f"Deanonymization fault: {e}")
        raise HTTPException(status_code=500, detail="Final text reconstruction failed.")

    return GatewayResponse(
        original_prompt=input_data.content,
        safe_prompt=safe_prompt,
        llm_response_raw=llm_response_raw,
        final_response=final_response,
        session_id=session_id
    )