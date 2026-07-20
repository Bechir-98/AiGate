import torch
from typing import Any
from scanners.scanner import BaseScanner, ScannerStage, ScanResult

class PromptGuardScanner(BaseScanner):
    name = "PromptGuard"
    stage = ScannerStage.INPUT

    def __init__(self, pipeline: Any, threshold: float = 0.75):
        """
        Initializes the scanner with the pre-loaded HuggingFace pipeline.
        :param threshold: Confidence score required to block the prompt (0.0 to 1.0).
        """
        self.pipe = pipeline
        self.threshold = threshold

    def scan(self, text: str, **kwargs: Any) -> ScanResult:
        # torch.inference_mode() disables gradient calculations, making CPU inference much faster
        with torch.inference_mode():
            # The pipeline returns the highest scoring label, e.g., [{'label': 'INJECTION', 'score': 0.99}]
            result = self.pipe(text)[0]
        
        label = result["label"].upper()
        score = result["score"]

        # Prompt Guard outputs 3 classes. Depending on the exact tokenizer config, 
        # they might map to "INJECTION", "JAILBREAK", or raw "LABEL_1", "LABEL_2".
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