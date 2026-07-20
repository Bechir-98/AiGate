from abc import ABC, abstractmethod
from enum import Enum
from pydantic import BaseModel
from typing import Optional, Any
import contextvars

request_entities_var: contextvars.ContextVar[Optional[list[str]]] = contextvars.ContextVar(
    "request_entities", 
    default=None
)

class ScannerStage(str, Enum):
    INPUT = "input"
    OUTPUT = "output"

class ScanResult(BaseModel):
    scanner_name: str
    passed: bool
    sanitized_text: Optional[str] = None
    reason: Optional[str] = None
    metadata: dict[str, Any] = {}

class BaseScanner(ABC):
    name: str
    stage: ScannerStage
    is_active: bool = True

    @abstractmethod
    async def scan(self, text: str, **kwargs: Any) -> ScanResult:
        """Core scanning logic implemented by concrete scanners."""
        pass