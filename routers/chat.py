from fastapi import APIRouter, Request, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from database import get_db
from models.models import Input,LLMDeanonymizeRequest,GatewayResponse
from routers.scanner import scan_spacy, scan_gliner,scan_gliner2
from routers.anonymizer import anonymize
from routers.deanonymizer import deanonymizer_llm
from openai import OpenAI 
from dotenv import load_dotenv
from utils.config_service import get_active_scanner
import os
load_dotenv()
router = APIRouter(prefix="/gateway")
client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=os.getenv("GROQ_API_KEY")
)

@router.post("/chat")
async def chat_with_llm(
    request: Request, 
    input_data: Input, 
    db: AsyncSession = Depends(get_db)
):
    redis_client = request.app.state.redis
    active_scanner = await get_active_scanner(db, redis_client)
    

    if active_scanner == "gliner1":
        scan_result = await scan_gliner(request, input_data, db)
    elif active_scanner == "gliner2":
        scan_result = await scan_gliner2(request, input_data, db)
    else:
        scan_result = await scan_spacy(request, input_data)
    
    anonymize_result = await anonymize(scan_result)
    safe_prompt =anonymize_result.anonymized_text
    
    safe_prompt=anonymize_result.anonymized_text

    response=client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {"role": "user", "content": safe_prompt}
        ]
    )
    
    llm_response_text = response.choices[0].message.content

    llm_req = LLMDeanonymizeRequest(text=llm_response_text)
    deanonymize_result = await deanonymizer_llm(llm_req)    
    return GatewayResponse(
        original_prompt=input_data.content,
        safe_prompt=safe_prompt,
        llm_response_raw=llm_response_text,
        final_response=deanonymize_result["deanonymized_text"]
    )