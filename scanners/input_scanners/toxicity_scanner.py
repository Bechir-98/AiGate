import torch
from typing import Any
from config import settings
from scanners.scanner import BaseScanner, ScannerStage, ScanResult

class ToxicityScanner(BaseScanner):
    name = "ToxicityScanner"

    def __init__(self, pipeline: Any, stage: ScannerStage = ScannerStage.OUTPUT, threshold: float = settings.TOXICITY_THRESHOLD):
        self.pipe = pipeline
        self.stage = stage
        self.threshold = threshold

    def scan(self, text: str, **kwargs: Any) -> ScanResult:
        with torch.inference_mode():
            results = self.pipe(text, top_k=None)

        if isinstance(results[0], list):
            results = results[0]

        violations = [
            f"{res['label']} ({res['score']:.2f})"
            for res in results
            if res['score'] >= self.threshold and res['label'] != "non-toxic"
        ]

        if violations:
            return ScanResult(
                scanner_name=self.name,
                passed=False,
                reason=f"Policy Violation: Toxic content detected [{', '.join(violations)}].",
                metadata={"violations": violations}
            )

        return ScanResult(
            scanner_name=self.name,
            passed=True
        )