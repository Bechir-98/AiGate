FROM python:3.10-slim

# Prevent Python from writing .pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV HF_HOME=/root/.cache/huggingface

# Set the working directory inside the container
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create HuggingFace cache directory with wide permissions to prevent host volume permission blocks
RUN mkdir -p /root/.cache/huggingface && chmod -R 777 /root/.cache/huggingface

# Copy only requirements first to leverage Docker layer cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m spacy download en_core_web_lg

# Copy the rest of your application code
COPY . .

# Inline creation of the preload engine script (Stored in root / to survive volume mounts)
RUN echo 'import os\n\
from pathlib import Path\n\
from huggingface_hub import snapshot_download\n\
\n\
# 1. Manage GLiNER 1\n\
gliner1 = os.getenv("GLINER1_MODEL_PATH", "rpeel/glitext-pii-edge")\n\
print(f"Checking cache for GLiNER 1: {gliner1}")\n\
try:\n\
    if not os.path.exists(gliner1):\n\
        snapshot_download(repo_id=gliner1)\n\
    else:\n\
        print(f"GLiNER 1 local folder found at {gliner1}")\n\
except Exception as e:\n\
    print(f"GLiNER 1 prefetch check skipped/failed: {e}")\n\
\n\
# 2. Manage GLiNER 2\n\
gliner2_path = os.getenv("GLINER2_MODEL_PATH", "/app/gliner2-PII")\n\
if Path(gliner2_path).exists() and any(Path(gliner2_path).iterdir()):\n\
    print(f"Local GLiNER 2 directory discovered at {gliner2_path}. Skipping download.")\n\
else:\n\
    fallback_repo = "fastino/gliner2-privacy-filter-PII-multi"\n\
    print(f"Local GLiNER 2 folder missing or empty. Fetching fallback from HF Hub: {fallback_repo}")\n\
    try:\n\
        snapshot_download(repo_id=fallback_repo)\n\
    except Exception as e:\n\
        print(f"GLiNER 2 download failed: {e}")\n\
print("Model synchronization checklist complete.")\n\
' > /preload_models.py

# Inline creation of the runtime entrypoint wrapper (Stored in root / to survive volume mounts)
RUN echo '#!/bin/sh\n\
python /preload_models.py\n\
exec "$@"\n\
' > /entrypoint.sh && chmod +x /entrypoint.sh

EXPOSE 8000

# Entrypoint runs model checks, CMD runs the web server if no compose command is provided
ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]