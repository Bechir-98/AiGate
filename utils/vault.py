import json
import secrets
import logging
import threading
import redis
import os
from presidio_anonymizer.operators import Operator, OperatorType

logger = logging.getLogger("vault_utils")

_redis_client = None
_redis_lock = threading.Lock()

def get_redis_client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        with _redis_lock:
            if _redis_client is None:
                from config import settings
                redis_url = getattr(settings, "REDIS_URL", os.getenv("REDIS_URL", "redis://localhost:6379/0"))
                pool = redis.ConnectionPool.from_url(redis_url, decode_responses=True)
                _redis_client = redis.Redis(connection_pool=pool)
    return _redis_client

class RedisVaultOperator(Operator):
    """Anonymizes PII by swapping text for a secure Redis token."""

    def operate(self, text: str, params: dict = None) -> str:
        params = params or {}
        entity_type = params.get("entity_type", "UNKNOWN")
        token_id = secrets.token_hex(3)
        token = f"<{entity_type}_{token_id}>"

        vault_payload = {
            "original_text": text,
            "entity_type": entity_type
        }

        try:
            client = get_redis_client()
            from config import settings as _settings
            client.set(token, json.dumps(vault_payload), ex=_settings.VAULT_TTL)
            client.hincrby("metrics:detected_entities", entity_type, 1)
        except redis.RedisError as e:
            logger.error(f"Redis vault anonymization failed: {e}")
            raise ConnectionError("Security vault is offline. Cannot process PII.") from e

        return token

    def validate(self, params: dict = None) -> None:
        pass

    def operator_name(self) -> str:
        return "redis_vault"

    def operator_type(self) -> OperatorType:
        return OperatorType.Anonymize


class RedisUnvaultOperator(Operator):
    """Reconstructs PII by retrieving the original value from Redis."""

    def operate(self, text: str, params: dict = None) -> str:
        try:
            client = get_redis_client()
            vault_payload_str = client.get(text)
            if vault_payload_str:
                vault_payload = json.loads(vault_payload_str)
                return vault_payload["original_text"]
        except (redis.RedisError, json.JSONDecodeError) as e:
            logger.error(f"Redis vault retrieval failed for token {text}: {e}")
            return text

        return text

    def validate(self, params: dict = None) -> None:
        pass

    def operator_name(self) -> str:
        return "redis_unvault"

    def operator_type(self) -> OperatorType:
        return OperatorType.Deanonymize