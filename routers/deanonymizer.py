import json
import re
from fastapi import APIRouter
from presidio_analyzer import RecognizerResult
from presidio_anonymizer import DeanonymizeEngine
from presidio_anonymizer.entities import OperatorConfig, OperatorResult
from utils.vault import redis_client, RedisVaultOperator, RedisUnvaultOperator
from models.models import DeanonymizeRequest, LLMDeanonymizeRequest

router = APIRouter(prefix="/deanonymize")
deanonymize_engine = DeanonymizeEngine()
deanonymize_engine.add_deanonymizer(RedisUnvaultOperator)

@router.post("/test")
async def deanonymizer_test(req: DeanonymizeRequest):
    operator_results = [
        OperatorResult(
            start=item.start,
            end=item.end,
            entity_type=item.entity_type
        )
        for item in req.items
    ]
    deanonymized = deanonymize_engine.deanonymize(
        text=req.anonymized_text,
        entities=operator_results,
        operators={"DEFAULT": OperatorConfig("redis_unvault")}
    )
    return {"deanonymized_text": deanonymized.text}

@router.post("")
async def deanonymizer_llm(req: LLMDeanonymizeRequest):
    token_pattern = re.compile(r"(?:<|&lt;)[A-Za-z_]+_[a-f0-9]{6}(?:>|&gt;)", re.IGNORECASE)

    def replace_token(match):
        raw_match = match.group(0)
        
        token = raw_match.replace("&lt;", "<").replace("&gt;", ">").replace("&LT;", "<").replace("&GT;", ">")
        
        vault_payload_str = redis_client.get(token)
        
        if vault_payload_str:
            redis_client.expire(token, 1800)
            
            vault_payload = json.loads(vault_payload_str)
            return vault_payload["original_text"]
        
        return raw_match

    deanonymized_text = token_pattern.sub(replace_token, req.text)
    
    return {"deanonymized_text": deanonymized_text}