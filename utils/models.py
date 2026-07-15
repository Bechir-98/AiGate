from pydantic import BaseModel

class Input(BaseModel):
    content: str
    scan_type: int | None = None

class ScanResult(BaseModel):
    entity_type: str
    start: int
    end: int
    score: float

class AnonymizeRequest(BaseModel):
    text: Input
    results: list[ScanResult]

class AnonymizedItem(BaseModel):
    start: int
    end: int
    entity_type: str
    operator :str

class DeanonymizeRequest(BaseModel):
    anonymized_text: str
    items: list[AnonymizedItem]