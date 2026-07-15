import json
import redis
import secrets
from presidio_anonymizer.operators import Operator, OperatorType

redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

class RedisVaultOperator(Operator):
    def operate(self, text: str, params: dict = None) -> str:
        params = params or {}
        entity_type = params.get("entity_type", "UNKNOWN")
        token_id = secrets.token_hex(3)
        token = f"<{entity_type}_{token_id}>" 
        
        vault_payload = {
            "original_text": text,
            "entity_type": entity_type
        }
        
        # Save to Redis and increment metrics
        redis_client.set(token, json.dumps(vault_payload))
        redis_client.hincrby("metrics:detected_entities", entity_type, 1)
        
        return token

    def validate(self, params: dict = None) -> None:
        pass

    def operator_name(self) -> str:
        return "redis_vault"

    def operator_type(self) -> OperatorType:
        return OperatorType.Anonymize
    

# 3. Operator for Retrieving PII (Deanonymization)
class RedisUnvaultOperator(Operator):
    def operate(self, text: str, params: dict = None) -> str:
        # 'text' is the token (e.g., <TOKEN_1234>)
        vault_payload_str = redis_client.get(text)
        
        if vault_payload_str:
            vault_payload = json.loads(vault_payload_str)
            return vault_payload["original_text"]
        
        # Fallback if token is missing
        return text 

    def validate(self, params: dict = None) -> None:
        pass

    def operator_name(self) -> str:
        return "redis_unvault"

    def operator_type(self) -> OperatorType:
        return OperatorType.Deanonymize