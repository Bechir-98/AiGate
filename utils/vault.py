import json
import secrets
import logging
import redis
import os
from presidio_anonymizer.operators import Operator, OperatorType

# Configure logger for this service
logger = logging.getLogger("vault_utils")

# Use a connection pool for better performance in concurrent threads
# and avoid dotenv loading here (let the app init handle config)
_redis_client = None

def get_redis_client() -> redis.Redis:
    global _redis_client
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
            # Store with 30min TTL (Matches your Deanonymizer logic)
            client = get_redis_client()
            client.set(token, json.dumps(vault_payload), ex=1800)
            client.hincrby("metrics:detected_entities", entity_type, 1)
        except redis.RedisError as e:
            logger.error(f"Redis Vault Anonymization failed: {e}")
            # Fallback: if vault fails, we cannot mask the PII safely. 
            # In a security proxy, it is safer to fail the request than leak data.
            raise ConnectionError("Security Vault is offline. Cannot process PII.") from e
            
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
            logger.error(f"Redis Vault Retrieval failed for token {text}: {e}")
            # If we fail to retrieve, returning the raw token is safer than crashing,
            # but in production you might want to flag this as a critical audit event.
            return text
        
        return text 

    def validate(self, params: dict = None) -> None:
        pass

    def operator_name(self) -> str:
        return "redis_unvault"

    def operator_type(self) -> OperatorType:
        return OperatorType.Deanonymize