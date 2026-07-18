import os
import uuid
import json
from fastapi import APIRouter, Request, Depends, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from models.models import Input, LLMDeanonymizeRequest, GatewayResponse
from routers.scanner import scan_spacy, scan_gliner, scan_gliner2
from routers.anonymizer import anonymize
from routers.deanonymizer import deanonymizer_llm
from openai import AsyncOpenAI
from dotenv import load_dotenv
from services.config_service import get_active_scanner

load_dotenv()
router = APIRouter(prefix="/gateway")

LITELLM_API_URL = os.getenv("LITELLM_API_URL", "http://localhost:4000/v1")

# The Async OpenAI client pointing directly to your LiteLLM container
client = AsyncOpenAI(
    base_url=LITELLM_API_URL,
    api_key="litellm-doesnt-need-a-key-here"
)

# HELPER FUNCTION: Get and save tokenized history asynchronously
async def get_chat_history(redis_client, session_id: str) -> list:
    history_key = f"session:{session_id}:history"
    data = await redis_client.get(history_key)  
    if data:
        # If Redis returns bytes, decode it. If it's already a string, use it directly.
        if isinstance(data, bytes):
            data = data.decode("utf-8")
        return json.loads(data)
    return []

async def save_chat_history(redis_client, session_id: str, history: list):
    history_key = f"session:{session_id}:history"
    # Sliding window: keep only the last 10 messages (5 turns) to save LLM tokens and costs
    trimmed_history = history[-10:]
    # Save with a 30-minute expiration (1800 seconds)
    await redis_client.setex(history_key, 1800, json.dumps(trimmed_history))


@router.post("/chat", response_model=GatewayResponse)
async def chat_with_llm(
    request: Request, 
    input_data: Input, 
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db)
):
    redis_client = request.app.state.redis
    
    # 1. Manage Session Identity
    session_id = input_data.session_id or f"sess_{uuid.uuid4().hex[:12]}"

    # 2. Identify scanner and anonymize prompt
    active_scanner = await get_active_scanner(db, redis_client)
    
    if active_scanner == "gliner1":
        scan_result = await scan_gliner(request, input_data, background_tasks, db)
    elif active_scanner == "gliner2":
        scan_result = await scan_gliner2(request, input_data, background_tasks, db)
    else:
        scan_result = await scan_spacy(request, input_data, background_tasks, db)
    
    anonymize_result = await anonymize(scan_result)
    safe_prompt = anonymize_result.anonymized_text

    # 3. Retrieve Tokenized History (Pure Async)
    history = await get_chat_history(redis_client, session_id)

    # 4. Construct LiteLLM request context
    messages = [
        {
            "role": "system",
            "content": (
                "You are a helpful assistant. To protect user privacy, some sensitive data "
                "in the prompt has been replaced with tokens like <PERSON_xxxxxx> or <ORGANIZATION_xxxxxx>. "
                "Treat these tokens as if they are the actual, valid names of people or companies. "
                "Do not mention that details are missing, do not complain about placeholders, "
                "and do not try to guess the original values. Just write your response naturally, "
                "using the tokens exactly as they are."
            )
        }
    ]
    
    # Append the history logs + the current anonymized user prompt
    messages.extend(history)
    messages.append({"role": "user", "content": safe_prompt})

    # 5. Send payload to LiteLLM
    response = await client.chat.completions.create(
        model="gateway-chat",
        messages=messages
    )
    llm_response_raw = response.choices[0].message.content

    # 6. Save new messages back to the safe log (anonymized prompt + raw LLM response)
    history.append({"role": "user", "content": safe_prompt})
    history.append({"role": "assistant", "content": llm_response_raw})
    await save_chat_history(redis_client, session_id, history)

    # 7. Deanonymize the response specifically for the user's return payload
    llm_req = LLMDeanonymizeRequest(text=llm_response_raw)
    deanonymize_result = await deanonymizer_llm(llm_req)    
    
    return GatewayResponse(
        original_prompt=input_data.content,
        safe_prompt=safe_prompt,
        llm_response_raw=llm_response_raw,
        final_response=deanonymize_result["deanonymized_text"],
        session_id=session_id
    )