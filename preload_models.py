import os
from pathlib import Path
from huggingface_hub import snapshot_download

def preload_models():
    gliner1 = os.getenv("GLINER1_MODEL_PATH", "rpeel/glitext-pii-edge")
    print(f"Checking cache for GLiNER 1: {gliner1}")
    try:
        if not os.path.exists(gliner1):
            snapshot_download(repo_id=gliner1)
    except Exception as e:
        print(f"GLiNER 1 check skipped/failed: {e}")

    gliner2_path = os.getenv("GLINER2_MODEL_PATH", "/app/gliner2-PII")
    if not (Path(gliner2_path).exists() and any(Path(gliner2_path).iterdir())):
        fallback_repo = "fastino/gliner2-privacy-filter-PII-multi"
        print(f"Fetching fallback GLiNER 2 from HF Hub: {fallback_repo}")
        try:
            snapshot_download(repo_id=fallback_repo)
        except Exception as e:
            print(f"GLiNER 2 download failed: {e}")

    for env_var in ["PROMPT_GUARD_MODEL_ID", "TOXIC_BERT_MODEL_ID"]:
        model_id = os.getenv(env_var)
        if model_id:
            print(f"Checking cache for model ({env_var}): {model_id}")
            try:
                snapshot_download(repo_id=model_id, token=os.getenv("HF_TOKEN"))
            except Exception as e:
                print(f"Preload failed for {model_id}: {e}")

    print("Model synchronization checklist complete.")

if __name__ == "__main__":
    preload_models()
