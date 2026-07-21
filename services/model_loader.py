import os
import logging
from typing import Optional
from huggingface_hub import login
from transformers import pipeline as hf_pipeline, AutoTokenizer, AutoModelForSequenceClassification
from optimum.onnxruntime import ORTModelForSequenceClassification

logger = logging.getLogger("model_loader")

def load_text_classification_pipeline(
    model_id: str, 
    hf_token: Optional[str] = None,
    is_gated: bool = False
):
    """
    Factory function that dynamically loads PyTorch or ONNX models based on model ID,
    handling authentication and pipeline setup.
    """
    if hf_token:
        logger.info(f"Hugging Face token detected (Starts with: {hf_token[:4]}). Authenticating...")
        login(token=hf_token)
    elif is_gated:
        logger.error(f"CRITICAL: Model {model_id} requires HF_TOKEN, but none was provided!")
        raise ValueError(f"Cannot load gated model {model_id} without an HF_TOKEN.")

    logger.info(f"Downloading/fetching tokenizer for {model_id}...")
    tokenizer = AutoTokenizer.from_pretrained(model_id, token=hf_token)

    # Dynamic ONNX vs PyTorch loading
    model_id_lower = model_id.lower()
    if "onnx" in model_id_lower or "xenova" in model_id_lower:
        logger.info(f"Initializing ONNX runtime model for CPU inference: {model_id}")
        model = ORTModelForSequenceClassification.from_pretrained(
            model_id,
            token=hf_token
        )
    else:
        logger.info(f"Initializing standard PyTorch model: {model_id}")
        model = AutoModelForSequenceClassification.from_pretrained(
            model_id,
            token=hf_token
        )

    return hf_pipeline(
        "text-classification", 
        model=model, 
        tokenizer=tokenizer,
        device=-1
    )