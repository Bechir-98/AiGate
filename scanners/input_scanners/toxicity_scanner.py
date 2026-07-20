import torch
from typing import Any
from scanners.scanner import BaseScanner, ScannerStage, ScanResult

class ToxicityScanner(BaseScanner):
    name = "ToxicityScanner"
    
    def __init__(self, pipeline: Any, stage: ScannerStage = ScannerStage.OUTPUT, threshold: float = 0.50):
        """
        Initializes the toxicity scanner.
        :param pipeline: The loaded HuggingFace pipeline.
        :param stage: Can be set to INPUT or OUTPUT depending on where you want to scan.
        :param threshold: Confidence score required to flag the text as toxic.
        """
        self.pipe = pipeline
        self.stage = stage
        self.threshold = threshold

    def scan(self, text: str, **kwargs: Any) -> ScanResult:
        with torch.inference_mode():
            # toxic-bert usually returns a list of scores for all labels if configured with top_k=None
            # Example output: [{'label': 'toxic', 'score': 0.9}, {'label': 'insult', 'score': 0.1}...]
            results = self.pipe(text, top_k=None)
        
        # If pipeline returns a nested list (e.g., [[{...}, {...}]]), extract the inner list
        if isinstance(results[0], list):
            results = results[0]

        # Filter out labels that exceed our toxicity threshold
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