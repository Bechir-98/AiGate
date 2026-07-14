from typing import Dict, List, Optional
import logging
from presidio_analyzer import LocalRecognizer, RecognizerResult, AnalysisExplanation

logger = logging.getLogger("presidio-analyzer")

class GLiNER2Recognizer(LocalRecognizer):
    """GLiNER2 model based entity recognizer supporting both PyTorch and ONNX runtimes."""

    def __init__(
        self,
        supported_entities: Optional[List[str]] = None,
        name: str = "GLiNER2Recognizer",
        supported_language: str = "en",
        version: str = "0.0.2",
        context: Optional[List[str]] = None,
        entity_mapping: Optional[Dict[str, str]] = None,
        model_name: str = "gliner2-PII",  # FIXED: Defaulting to your local directory
        threshold: float = 0.50,
        map_location: Optional[str] = None,
        load_onnx_model: bool = True,
        **model_kwargs,
    ):
        if entity_mapping:
            if supported_entities:
                raise ValueError("entity_mapping and supported_entities cannot be used together")
            self.model_to_presidio_entity_mapping = entity_mapping
        else:
            self.model_to_presidio_entity_mapping = {entity: entity for entity in (supported_entities or [])}

        supported_entities = list(set(self.model_to_presidio_entity_mapping.values()))
        self.model_name = model_name
        self.threshold = threshold
        self.map_location = map_location or "cpu"
        self.load_onnx_model = load_onnx_model
        self.model_kwargs = model_kwargs
        self.model = None

        super().__init__(
            supported_entities=supported_entities,
            name=name,
            supported_language=supported_language,
            version=version,
            context=context,
        )

        self.gliner_labels = list(self.model_to_presidio_entity_mapping.keys())

    def load(self) -> None:
        """Load the GLiNER2 model dynamically depending on load_onnx_model flag."""
        if self.load_onnx_model:
            try:
                from gliner2_onnx import GLiNER2ONNXRuntime
            except ImportError as e:
                raise ImportError(
                    "gliner2-onnx is not installed. Please install it using: pip install gliner2-onnx"
                ) from e

            # Map devices to ONNX execution providers
            providers = ["CPUExecutionProvider"]
            if "cuda" in self.map_location.lower():
                providers = ["CUDAExecutionProvider"] + providers

            logger.info(f"Loading GLiNER2 ONNX model from local folder: {self.model_name}...")
            
            # FIXED: Direct initialization to support the local folder!
            self.model = GLiNER2ONNXRuntime(
                self.model_name
            )
        else:
            try:
                from gliner2 import GLiNER2
            except ImportError as e:
                raise ImportError(
                    "gliner2 is not installed. Please install it using: pip install gliner2"
                ) from e

            logger.info(f"Loading GLiNER2 PyTorch model from {self.model_name}...")
            self.model = GLiNER2.from_pretrained(self.model_name, **self.model_kwargs)
            self.model.to(self.map_location)

    def analyze(
        self,
        text: str,
        entities: List[str],
        nlp_artifacts = None,
    ) -> List[RecognizerResult]:
        """Analyze text using GLiNER2."""
        labels = self.__create_input_labels(entities)

        # Use GLiNER2's extraction function
        gliner_predictions = self.model.extract_entities(
            text=text,
            labels=labels,
            threshold=self.threshold,
        )

        results = []
        for pred in gliner_predictions:
            # Handle both dict formats and objects with attributes
            if isinstance(pred, dict):
                p_label = pred.get("label")
                p_start = pred.get("start")
                p_end = pred.get("end")
                p_score = pred.get("score", 1.0)
            else:
                p_label = getattr(pred, "label", "")
                p_start = getattr(pred, "start", 0)
                p_end = getattr(pred, "end", 0)
                p_score = getattr(pred, "score", 1.0)

            presidio_entity = self.model_to_presidio_entity_mapping.get(p_label, p_label)

            # Filter out non-requested entities
            if entities and presidio_entity not in entities:
                continue

            analysis_explanation = AnalysisExplanation(
                recognizer=self.name,
                original_score=p_score,
                textual_explanation=f"Identified as {presidio_entity} by GLiNER2",
            )

            results.append(
                RecognizerResult(
                    entity_type=presidio_entity,
                    start=p_start,
                    end=p_end,
                    score=p_score,
                    analysis_explanation=analysis_explanation,
                )
            )

        return results

    def __create_input_labels(self, entities):
        labels = list(self.gliner_labels)
        for entity in entities:
            if (
                entity not in self.model_to_presidio_entity_mapping.values()
                and entity not in self.gliner_labels
            ):
                labels.append(entity)
        return labels