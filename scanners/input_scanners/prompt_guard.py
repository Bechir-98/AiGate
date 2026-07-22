import torch
from typing import Any
from config import settings
from scanners.scanner import BaseScanner, ScannerStage, ScanResult

class PromptGuardScanner(BaseScanner):
    name = "PromptGuard"
    stage = ScannerStage.INPUT

    def __init__(self, pipeline: Any, threshold: float = settings.PROMPT_GUARD_THRESHOLD):
        self.pipe = pipeline
        self.threshold = threshold

    def scan(self, text: str, **kwargs: Any) -> ScanResult:
        with torch.inference_mode():
            result = self.pipe(text)[0]

        label = result["label"].upper()
        score = result["score"]

        is_malicious = label in ["INJECTION", "JAILBREAK", "MALICIOUS", "LABEL_1", "LABEL_2"]

        if is_malicious and score >= self.threshold:
            return ScanResult(
                scanner_name=self.name,
                passed=False,
                reason=f"Security Policy Violation: {label} attack detected.",
                metadata={"label": label, "score": score}
            )

        return ScanResult(
            scanner_name=self.name,
            passed=True,
            metadata={"label": label, "score": score}
        )