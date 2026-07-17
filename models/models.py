from pydantic import BaseModel
from typing import List, Optional

class Input(BaseModel):
    content: str
    entities: Optional[List[str]] = None
    session_id: Optional[str] = None

class ScanResult(BaseModel):
    entity_type: str
    start: int
    end: int
    score: float

class AnonymizeRequest(BaseModel):
    text: str
    results: list[ScanResult]

class AnonymizedItem(BaseModel):
    start: int
    end: int
    entity_type: str
    operator :str

class DeanonymizeRequest(BaseModel):
    anonymized_text: str
    items: Optional[list] = None

class LLMDeanonymizeRequest(BaseModel):
    text: str

class EntityMapping(BaseModel):
    gliner_label:str
    presidio_label:str
    
class GatewayResponse(BaseModel):
    original_prompt: str
    safe_prompt: str
    llm_response_raw: str
    final_response: str
