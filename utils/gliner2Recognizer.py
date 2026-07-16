import re
from pathlib import Path
from typing import Dict, List, Optional
import logging
from presidio_analyzer import LocalRecognizer, RecognizerResult, AnalysisExplanation
logger = logging.getLogger("presidio-analyzer")


def optimize_gliner_label(raw_label: str) -> str:
    """
    Cleans up any user input to be optimized for GLiNER's text encoder.
    Example: 
      'MAC_ADDRESS' -> 'Mac Address'
      'social-security-number' -> 'Social Security Number'
      'id' -> 'Id'
    """
    # Replace underscores and hyphens with spaces
    clean_str = re.sub(r'[-_]', ' ', raw_label)
    # Remove extra spaces
    clean_str = re.sub(r'\s+', ' ', clean_str).strip()
    # Convert to Title Case
    return clean_str.title()


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
        model_name: str = "gliner2-PII",
        threshold: float = 0.50,
        map_location: Optional[str] = None,
        load_onnx_model: bool = True,
        intra_op_num_threads: int = 2,
        inter_op_num_threads: int = 1,
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

        self.intra_op_num_threads = intra_op_num_threads
        self.inter_op_num_threads = inter_op_num_threads

        super().__init__(
            supported_entities=supported_entities,
            name=name,
            supported_language=supported_language,
            version=version,
            context=context,
        )

        self.gliner_labels = list(self.model_to_presidio_entity_mapping.keys())

    def load(self) -> None:
        if self.load_onnx_model:
            self._load_onnx()
        else:
            self._load_pytorch()

    def _load_onnx(self) -> None:
        try:
            from gliner2_onnx import GLiNER2ONNXRuntime
        except ImportError as e:
            raise ImportError("gliner2-onnx is not installed.") from e

        import onnxruntime as ort

        providers = ["CPUExecutionProvider"]
        if "cuda" in self.map_location.lower():
            providers = ["CUDAExecutionProvider"] + providers

        session_options = ort.SessionOptions()
        session_options.intra_op_num_threads = self.intra_op_num_threads
        session_options.inter_op_num_threads = self.inter_op_num_threads
        session_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL

        def patched_load_model(self_runtime, path, providers):
            if not path.exists():
                from gliner2_onnx.exceptions import ModelNotFoundError
                raise ModelNotFoundError(f"Model not found: {path}")
            return ort.InferenceSession(str(path), sess_options=session_options, providers=providers)

        GLiNER2ONNXRuntime._load_model = patched_load_model

        if Path(self.model_name).is_dir():
            logger.info(f"Loading GLiNER2 ONNX model from local folder: {self.model_name}...")
            self.model = GLiNER2ONNXRuntime(self.model_name)
        else:
            logger.info(f"Downloading GLiNER2 ONNX model from HF Hub: {self.model_name}...")
            self.model = GLiNER2ONNXRuntime.from_pretrained(
                self.model_name,
                providers=providers,
                precision=self.model_kwargs.get("precision", "fp32"),
                revision=self.model_kwargs.get("revision"),
            )

    def _load_pytorch(self) -> None:
        import torch
        torch.set_num_threads(self.intra_op_num_threads)

        try:
            from gliner2 import GLiNER2
        except ImportError as e:
            raise ImportError("gliner2 is not installed.") from e

        logger.info(f"Loading GLiNER2 PyTorch model from {self.model_name}...")
        pytorch_kwargs = {k: v for k, v in self.model_kwargs.items() if k not in ("precision",)}
        self.model = GLiNER2.from_pretrained(self.model_name, **pytorch_kwargs)
        self.model.to(self.map_location)

    def _extract_entities(self, text: str, labels: List[str]):
        if self.load_onnx_model:
            predictions = self.model.extract_entities(text=text, labels=labels, threshold=self.threshold)
            for pred in predictions:
                if isinstance(pred, dict):
                    yield (pred.get("label"), pred.get("start", 0), pred.get("end", 0), pred.get("score", 1.0))
                else:
                    yield (getattr(pred, "label", ""), getattr(pred, "start", 0), getattr(pred, "end", 0), getattr(pred, "score", 1.0))
        else:
            result = self.model.extract_entities(text, labels, threshold=self.threshold, include_confidence=True, include_spans=True)
            entities_by_label = result.get("entities", {})
            for label, spans in entities_by_label.items():
                for span in spans:
                    if isinstance(span, dict):
                        start = span.get("start", 0)
                        end = span.get("end", 0)
                        score = span.get("confidence", 1.0)
                    else:
                        start = text.find(str(span))
                        start = start if start != -1 else 0
                        end = start + len(str(span))
                        score = 1.0
                    yield (label, start, end, score)

    def analyze(self, text: str, entities: List[str], nlp_artifacts=None) -> List[RecognizerResult]:
        gliner_to_presidio_safe = {k.lower(): v for k, v in self.model_to_presidio_entity_mapping.items()}
        presidio_to_gliner_safe = {v.lower(): k for k, v in self.model_to_presidio_entity_mapping.items()}

        
        labels = list(self.gliner_labels)
        
        if entities:
            for requested_entity in entities:
                req_lower = requested_entity.lower()
                
                # If it's a known Presidio label mapping
                if req_lower in presidio_to_gliner_safe:
                    gliner_target = presidio_to_gliner_safe[req_lower]
                    if gliner_target not in labels:
                        labels.append(gliner_target)
                else:
                    optimized_label = optimize_gliner_label(requested_entity)
                    if optimized_label not in labels:
                        labels.append(optimized_label)
        
        
        normalized_predictions = self._extract_entities(text, labels)

        results = []
        for p_label, p_start, p_end, p_score in normalized_predictions:
            p_label_str = str(p_label)
            
            default_presidio_fallback = p_label_str.upper().replace(" ", "_").replace("-", "_")
            presidio_entity = gliner_to_presidio_safe.get(p_label_str.lower(), default_presidio_fallback)

            if entities:
                entities_lower = {e.lower() for e in entities}
                if (
                    presidio_entity.lower() not in entities_lower
                    and p_label_str.lower() not in entities_lower
                ):
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