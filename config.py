from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # --- Framework Environment ---
    FASTAPI_ENV: str = "development"
    PROJECT_NAME: str = "LLM Security & Anonymization Gateway"
    VERSION: str = "1.0.0"
    
    # --- CORS Configuration ---
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
            "allow_credentials": True,
            "allow_methods": ["*"],
            "allow_headers": ["*"],
        }
    
    # --- Infrastructure URLs ---
    DATABASE_URL: str
    REDIS_URL: str
    LITELLM_API_URL: str = "http://litellm:4000/v1"
    
    @property
    def async_database_url(self) -> str:
        """Converts protocol to asyncpg for SQLAlchemy compatibility."""
        if self.DATABASE_URL.startswith("postgresql://"):
            return self.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
        return self.DATABASE_URL
    
    # --- AI Engine Model Paths ---
    GLINER1_MODEL_PATH: str = "rpeel/glitext-pii-edge"
    GLINER2_MODEL_PATH: str = "/app/gliner2-PII"
    PROMPT_GUARD_MODEL_ID: str = "gravitee-io/Llama-Prompt-Guard-2-86M-onnx"
    #PROMPT_GUARD_MODEL_ID: str = "meta-llama/Llama-Prompt-Guard-2-86M"
    TOXIC_BERT_MODEL_ID: str = "unitary/toxic-bert"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()