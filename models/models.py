from typing import Optional
from pydantic import BaseModel, Field

# ==========================================
# 1. INBOUND INTAKE SCHEMAS
# ==========================================

class Input(BaseModel):
    """Initial user payload entering the gateway pipeline."""
    content: str = Field(..., min_length=1, description="The raw prompt text to process")
    entities: Optional[list[str]] = Field(None, description="Optional subset of PII entities to scan for")
    session_id: Optional[str] = Field(None, description="Tracking context for deanonymization lookup states")


# ==========================================
# 2. SCANNING & ANONYMIZATION PIPELINE SCHEMAS
# ==========================================

class ScanResult(BaseModel):
    """Structural boundary footprint of a discovered piece of PII."""
    entity_type: str = Field(..., description="The classification label (e.g., PHONE_NUMBER)")
    start: int = Field(..., ge=0, description="Character start index offset")
    end: int = Field(..., ge=0, description="Character end index offset")
    score: float = Field(..., ge=0.0, le=1.0, description="Model classification confidence weight")


class AnonymizeRequest(BaseModel):
    """
    Bridges the scanning and anonymization engines. 
    Serves as the output of the scanner and the input to the anonymizer.
    """
    text: str = Field(..., description="The original raw text string")
    results: list[ScanResult] = Field(default_factory=list, description="Collection of identified PII spans")


class AnonymizedItem(BaseModel):
    """Tracking blueprint for an individual token swapped inside the text vault."""
    start: int = Field(..., ge=0)
    end: int = Field(..., ge=0)
    entity_type: str
    operator: str = Field(..., description="The execution engine key used (e.g., redis_vault)")


class DeanonymizeRequest(BaseModel):
    """
    The complete blueprint needed to reverse tokenization.
    Contains the masked text and the map array used to track vault offsets.
    """
    anonymized_text: str = Field(..., description="The text string containing secure tokens")
    # FIX: Heavily typed list enforcement replacing the generic list
    items: list[AnonymizedItem] = Field(default_factory=list, description="Strict structural map of swapped tokens")


# ==========================================
# 3. UPSTREAM LLM & OUTBOUND SCHEMAS
# ==========================================

class LLMDeanonymizeRequest(BaseModel):
    """Raw unstructured text coming back from an upstream LLM instance."""
    text: str = Field(..., min_length=1, description="The tokenized text response from the model")


class EntityMapping(BaseModel):
    """Simple configuration layout matching model structures."""
    gliner_label: str
    presidio_label: str


class GatewayResponse(BaseModel):
    """The final payload returned to the client at the end of the gateway loop."""
    original_prompt: str
    safe_prompt: str
    llm_response_raw: str
    final_response: str
    session_id: str