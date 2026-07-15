from pathlib import Path
from typing import Dict, List, Optional
import logging

from presidio_analyzer import LocalRecognizer, RecognizerResult, AnalysisExplanation

logger = logging.getLogger("presidio-analyzer")


class GLiNER2Recognizer(LocalRecognizer):
    """GLiNER2 model based entity recognizer supporting both PyTorch and ONNX runtimes.

    Pour le mode ONNX (load_onnx_model=True), model_name peut être :
      - un chemin local vers un dossier déjà exporté (contenant gliner2_config.json
        + les 4 fichiers .onnx : encoder, classifier, span_rep, count_embed)
      - un repo_id HuggingFace Hub déjà pré-exporté dans ce même format
        (ex: "lmo3/gliner2-large-v1-onnx", "lmo3/gliner2-multi-v1-onnx")

    Note: certains repos HF nommés "*-onnx" utilisent un format d'export différent
    (fichier .onnx monolithique unique, pas de gliner2_config.json) et ne sont PAS
    compatibles avec ce chemin — il faut alors les exporter soi-même via
    `make onnx-export MODEL=<repo_pytorch>` depuis lmoe/gliner2-onnx.
    """

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

        # Contrôle du threading ONNX Runtime — évite l'oversubscription CPU
        # quand plusieurs analyzers (spacy, gliner1, gliner2) tournent dans le
        # même process. La lib gliner2_onnx n'expose pas session_options
        # nativement, donc on patch _load_model pour l'injecter.
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
        """Load the GLiNER2 model dynamically depending on load_onnx_model flag."""
        if self.load_onnx_model:
            self._load_onnx()
        else:
            self._load_pytorch()

    def _load_onnx(self) -> None:
        try:
            from gliner2_onnx import GLiNER2ONNXRuntime
        except ImportError as e:
            raise ImportError(
                "gliner2-onnx is not installed. Please install it using: pip install gliner2-onnx"
            ) from e

        import onnxruntime as ort

        # Map devices to ONNX execution providers
        providers = ["CPUExecutionProvider"]
        if "cuda" in self.map_location.lower():
            providers = ["CUDAExecutionProvider"] + providers

        session_options = ort.SessionOptions()
        session_options.intra_op_num_threads = self.intra_op_num_threads
        session_options.inter_op_num_threads = self.inter_op_num_threads
        session_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL

        # Patch _load_model pour injecter session_options — la lib ne
        # l'expose pas dans son API publique (from_pretrained / __init__).
        # Le patch est posé sur la classe AVANT instanciation, donc il
        # s'applique peu importe le chemin emprunté ensuite (local ou HF).
        def patched_load_model(self_runtime, path, providers):
            if not path.exists():
                from gliner2_onnx.exceptions import ModelNotFoundError
                raise ModelNotFoundError(f"Model not found: {path}")
            return ort.InferenceSession(
                str(path), sess_options=session_options, providers=providers
            )

        GLiNER2ONNXRuntime._load_model = patched_load_model

        if Path(self.model_name).is_dir():
            # Dossier local déjà exporté
            logger.info(f"Loading GLiNER2 ONNX model from local folder: {self.model_name}...")
            self.model = GLiNER2ONNXRuntime(self.model_name)
        else:
            # Repo HF Hub — doit être pré-exporté au format gliner2_onnx
            # (gliner2_config.json + 4 fichiers .onnx). Voir docstring de la classe.
            logger.info(f"Downloading GLiNER2 ONNX model from HF Hub: {self.model_name}...")
            self.model = GLiNER2ONNXRuntime.from_pretrained(
                self.model_name,
                providers=providers,
                precision=self.model_kwargs.get("precision", "fp32"),
                revision=self.model_kwargs.get("revision"),
            )

    def _load_pytorch(self) -> None:
        import torch

        # Aligne le threading PyTorch sur les mêmes contraintes que l'ONNX
        # (intra_op_num_threads) — par défaut PyTorch utilise tous les cores
        # physiques dispo, ce qui fausse toute comparaison de latence avec
        # les runtimes ONNX bridés et peut créer de l'oversubscription CPU
        # si plusieurs analyzers tournent dans le même process.
        torch.set_num_threads(self.intra_op_num_threads)

        try:
            from gliner2 import GLiNER2
        except ImportError as e:
            raise ImportError(
                "gliner2 is not installed. Please install it using: pip install gliner2"
            ) from e

        logger.info(f"Loading GLiNER2 PyTorch model from {self.model_name}...")
        # On ne propage pas les kwargs spécifiques à l'ONNX (precision, revision)
        # vers GLiNER2.from_pretrained pour éviter les collisions de signature.
        pytorch_kwargs = {
            k: v for k, v in self.model_kwargs.items()
            if k not in ("precision",)
        }
        self.model = GLiNER2.from_pretrained(self.model_name, **pytorch_kwargs)
        self.model.to(self.map_location)

    def _extract_entities(self, text: str, labels: List[str]):
        """Appelle le backend chargé et normalise le résultat en tuples
        (label, start, end, score), quel que soit le format de retour natif.

        - gliner2_onnx.GLiNER2ONNXRuntime.extract_entities(text=..., labels=..., threshold=...)
          -> list[Entity] (attributs .label, .start, .end, .score)
        - gliner2.GLiNER2.extract_entities(text, labels, threshold=..., include_spans=True,
          include_confidence=True) (positionnel !)
          -> {'entities': {label: [{'text':..., 'start':..., 'end':..., 'confidence':...}, ...]}}
        """
        if self.load_onnx_model:
            predictions = self.model.extract_entities(
                text=text,
                labels=labels,
                threshold=self.threshold,
            )
            for pred in predictions:
                if isinstance(pred, dict):
                    yield (
                        pred.get("label"),
                        pred.get("start", 0),
                        pred.get("end", 0),
                        pred.get("score", 1.0),
                    )
                else:
                    yield (
                        getattr(pred, "label", ""),
                        getattr(pred, "start", 0),
                        getattr(pred, "end", 0),
                        getattr(pred, "score", 1.0),
                    )
        else:
            result = self.model.extract_entities(
                text,
                labels,
                threshold=self.threshold,
                include_confidence=True,
                include_spans=True,
            )
            entities_by_label = result.get("entities", {})
            for label, spans in entities_by_label.items():
                for span in spans:
                    # Selon include_spans/include_confidence, span peut être
                    # une simple string (pas de start/end) — on protège les deux cas.
                    if isinstance(span, dict):
                        start = span.get("start", 0)
                        end = span.get("end", 0)
                        score = span.get("confidence", 1.0)
                    else:
                        # Fallback improbable ici puisqu'on force include_spans=True,
                        # mais on garde une sécurité si l'API change de comportement.
                        start = text.find(str(span))
                        start = start if start != -1 else 0
                        end = start + len(str(span))
                        score = 1.0
                    yield (label, start, end, score)

    def analyze(
        self,
        text: str,
        entities: List[str],
        nlp_artifacts=None,
    ) -> List[RecognizerResult]:
        """Analyze text using GLiNER2."""
        labels = self.__create_input_labels(entities)
        normalized_predictions = self._extract_entities(text, labels)

        results = []
        for p_label, p_start, p_end, p_score in normalized_predictions:
            presidio_entity = self.model_to_presidio_entity_mapping.get(p_label, p_label)

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