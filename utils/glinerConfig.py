import os
import onnxruntime as ort
from typing import Dict, List, Optional
from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.predefined_recognizers import GLiNERRecognizer
from utils.null_nlp_engine import NullNlpEngine
from utils.gliner2Recognizer import GLiNER2Recognizer

def create_gliner_analyzer(entity_mapping: Dict[str, str]):
    resolved_model_name = os.getenv("GLINER1_MODEL_PATH", "rpeel/glitext-pii-edge")

    # Optimize ONNX Runtime for CPU usage to prevent thread context-switching overhead
    session_options = ort.SessionOptions()
    session_options.intra_op_num_threads = 2
    session_options.inter_op_num_threads = 2
    session_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

    gliner_recognizer = GLiNERRecognizer(
        model_name=resolved_model_name,
        entity_mapping=entity_mapping,
        flat_ner=False,
        multi_label=True,
        map_location="cpu",
        load_onnx_model=True,
        onnx_model_file="model.onnx",
        threshold=0.5,
        session_options=session_options,
    )

    analyzer_engine = AnalyzerEngine(
        nlp_engine=NullNlpEngine()
    )

    for recognizer in analyzer_engine.registry.recognizers.copy():
        analyzer_engine.registry.remove_recognizer(recognizer.name)

    analyzer_engine.registry.add_recognizer(gliner_recognizer)
    
    return analyzer_engine

def create_gliner2_analyzer(entity_mapping: Dict[str, str], load_onnx_model: bool = True):
    local_path = os.getenv("GLINER2_MODEL_PATH", "/app/gliner2-PII")
    
    if os.path.exists(local_path) and os.listdir(local_path):
        resolved_model_name = local_path
    else:
        resolved_model_name = "fastino/gliner2-privacy-filter-PII-multi"

    session_options = ort.SessionOptions()
    session_options.intra_op_num_threads = 2
    session_options.inter_op_num_threads = 1
    session_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL

    gliner2_recognizer = GLiNER2Recognizer(
        model_name=resolved_model_name, 
        entity_mapping=entity_mapping, 
        threshold=0.5,
        map_location="cpu",
        load_onnx_model=load_onnx_model,
    )

    analyzer_engine = AnalyzerEngine(nlp_engine=NullNlpEngine())

    for recognizer in analyzer_engine.registry.recognizers.copy():
        analyzer_engine.registry.remove_recognizer(recognizer.name)

    analyzer_engine.registry.add_recognizer(gliner2_recognizer)
    
    return analyzer_engine

def update_analyzer_mappings(analyzer_engine: AnalyzerEngine, entity_mapping: Dict[str, str], extra_entities: List[str] = None):
    """
    Dynamically updates the entity mappings of the registered GLiNER/GLiNER2 recognizers
    inside a Presidio AnalyzerEngine, without reloading the core models.
    """
    for recognizer in analyzer_engine.registry.recognizers:
        if recognizer.name in ("GLiNERRecognizer", "GLiNER2Recognizer"):
            recognizer.model_to_presidio_entity_mapping = entity_mapping
            recognizer.gliner_labels = list(entity_mapping.keys())
            
            supported = list(set(entity_mapping.values()))
            if extra_entities:
                supported = list(set(supported + extra_entities))
            recognizer.supported_entities = supported