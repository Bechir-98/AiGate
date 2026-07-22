from typing import Optional
from pydantic import BaseModel, Field


class Input(BaseModel):
    content: str = Field(..., min_length=1, max_length=32000)
    entities: Optional[list[str]] = None
    session_id: Optional[str] = None


class PIIScanResult(BaseModel):
    entity_type: str
    start: int = Field(..., ge=0)
    end: int = Field(..., ge=0)
    score: float = Field(..., ge=0.0, le=1.0)


class AnonymizeRequest(BaseModel):
    text: str
    results: list[PIIScanResult] = Field(default_factory=list)


class AnonymizedItem(BaseModel):
    start: int = Field(..., ge=0)
    end: int = Field(..., ge=0)
    entity_type: str
    operator: str


class DeanonymizeRequest(BaseModel):
    anonymized_text: str
    items: list[AnonymizedItem] = Field(default_factory=list)


class LLMDeanonymizeRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=32000)


class EntityMapping(BaseModel):
    gliner_label: str
    presidio_label: str


class GatewayResponse(BaseModel):
    original_prompt: str
    safe_prompt: str
    llm_response_raw: str
    final_response: str
    session_id: str