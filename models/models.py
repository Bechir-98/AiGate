from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone

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

class DetectionAudit(Base):
    __tablename__ = "detection_audit"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String, index=True, nullable=False) # Plus de unique=True ici !
    count = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)