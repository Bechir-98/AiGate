import re
import uuid
import json
import logging
from typing import Any, Dict
from config import settings
from scanners.scanner import BaseScanner, ScannerStage, ScanResult
from services.regex_service import get_active_patterns

logger = logging.getLogger("custom_regex_scanner")

_compiled_regex_cache: Dict[str, re.Pattern] = {}

def _get_compiled_pattern(pattern_str: str) -> re.Pattern:
    if pattern_str not in _compiled_regex_cache:
        _compiled_regex_cache[pattern_str] = re.compile(pattern_str)
    return _compiled_regex_cache[pattern_str]

def clear_compiled_regex_cache() -> None:
    _compiled_regex_cache.clear()

class CustomRegexScanner(BaseScanner):
    name = "custom_regex"
    stage = ScannerStage.INPUT

    async def scan(self, text: str, **kwargs: Any) -> ScanResult:
        db = kwargs.get("db")
        app_state = kwargs.get("app_state")

        if not db or not app_state or not hasattr(app_state, "redis"):
            logger.warning("Missing db or redis client in scanner kwargs. Skipping CustomRegexScanner.")
            return ScanResult(scanner_name=self.name, passed=True)

        redis_client = app_state.redis

        patterns = await get_active_patterns(db, redis_client)
        if not patterns:
            return ScanResult(scanner_name=self.name, passed=True)

        matches_to_process = []

        for p in patterns:
            try:
                compiled = _get_compiled_pattern(p["pattern"])
                for match in compiled.finditer(text):
                    matches_to_process.append({
                        "start": match.start(),
                        "end": match.end(),
                        "original_text": match.group(0),
                        "entity_type": p["entity_type"].upper().replace(" ", "_")
                    })
            except re.error as e:
                logger.error(f"Invalid regex rule [{p['name']}]: {e}")
                continue

        if not matches_to_process:
            return ScanResult(scanner_name=self.name, passed=True)

        non_overlapping = []
        last_end = 0
        for m in sorted(matches_to_process, key=lambda x: (x["start"], -len(x["original_text"]))):
            if m["start"] >= last_end:
                non_overlapping.append(m)
                last_end = m["end"]

        parts = []
        last_idx = 0
        detected_entities = []
        pipeline_redis_pairs = {}

        for m in non_overlapping:
            start, end = m["start"], m["end"]
            orig = m["original_text"]
            entity = m["entity_type"]

            hex_id = uuid.uuid4().hex[:6]
            token = f"<{entity}_{hex_id}>"

            parts.append(text[last_idx:start])
            parts.append(token)
            last_idx = end

            pipeline_redis_pairs[token] = orig
            detected_entities.append(entity)

        parts.append(text[last_idx:])
        sanitized_text = "".join(parts)

        if pipeline_redis_pairs:
            try:
                pipe = redis_client.pipeline()
                for t_key, orig_val in pipeline_redis_pairs.items():
                    pipe.setex(t_key, settings.VAULT_TTL, json.dumps({"original_text": orig_val}))
                await pipe.execute()
            except Exception as e:
                logger.error(f"Failed to store custom regex vault tokens in Redis: {e}")

        return ScanResult(
            scanner_name=self.name,
            passed=True,
            sanitized_text=sanitized_text if sanitized_text != text else None,
            metadata={"detected_entities": detected_entities}
        )