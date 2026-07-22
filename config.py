import re
from typing import List, Union, Optional
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    FASTAPI_ENV: str = "development"
    PROJECT_NAME: str = "LLM Security & Anonymization Gateway"
    VERSION: str = "1.0.0"

    API_KEY: Optional[str] = None
    HF_TOKEN: Optional[str] = None
    LITELLM_API_KEY: str = "litellm"
    LITELLM_TIMEOUT: int = 60
    LITELLM_CONNECT_TIMEOUT: int = 5
    LITELLM_MAX_RETRIES: int = 2
    VAULT_TTL: int = 1800
    CONFIG_CACHE_TTL: int = 300
    PII_THREAD_POOL_SIZE: int = 8
    ANONYMIZER_THREAD_POOL_SIZE: int = 32
    DEANONYMIZER_THREAD_POOL_SIZE: int = 16
    PROMPT_GUARD_THRESHOLD: float = 0.75
    TOXICITY_THRESHOLD: float = 0.50
    GLINER_INTRA_OP_THREADS: int = 2
    GLINER_INTER_OP_THREADS: int = 2

    ALLOWED_ORIGINS: Union[str, List[str]] = "*"

    @field_validator("ALLOWED_ORIGINS", mode="before")
    @classmethod
    def parse_allowed_origins(cls, value: Union[str, List[str]]) -> List[str]:
        if isinstance(value, str):
            if value == "*":
                return ["*"]
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @property
    def cors_settings(self) -> dict:
        return {
            "allow_origins": self.ALLOWED_ORIGINS,
            "allow_credentials": self.ALLOWED_ORIGINS != ["*"],
            "allow_methods": ["*"],
            "allow_headers": ["*"],
        }

    DATABASE_URL: str
    REDIS_URL: str
    LITELLM_API_URL: str = "http://litellm:4000/v1"

    @property
    def async_database_url(self) -> str:
        if self.DATABASE_URL.startswith("postgresql+asyncpg://"):
            return self.DATABASE_URL
        if self.DATABASE_URL.startswith("postgresql://"):
            return self.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
        return self.DATABASE_URL

    GLINER1_MODEL_PATH: str = "rpeel/glitext-pii-edge"
    GLINER2_MODEL_PATH: str = "fastino/gliner2-privacy-filter-PII-multi"
    PROMPT_GUARD_MODEL_ID: str = "gravitee-io/Llama-Prompt-Guard-2-86M-onnx"
    TOXIC_BERT_MODEL_ID: str = "Xenova/toxic-bert"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()

VAULT_TOKEN_PATTERN = re.compile(r"(?:<|&lt;)[A-Za-z_]+_[a-f0-9]{6}(?:>|&gt;)", re.IGNORECASE)