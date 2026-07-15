from pydantic import BaseModel
from typing import List, Optional

class Input(BaseModel):
    content: str
    scan_type: int | None = None
    entities: Optional[List[str]] = None

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
    items: list[AnonymizedItem]

class EntityMapping(BaseModel):
    gliner_label:str
    presidio_label:str