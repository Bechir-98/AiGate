import re
import uuid
import json
import logging
from typing import Any
from scanners.scanner import BaseScanner, ScannerStage, ScanResult
from services.regex_service import get_active_patterns

logger = logging.getLogger("custom_regex_scanner")

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

        # 1. Fetch active patterns from Redis/DB
        patterns = await get_active_patterns(db, redis_client)
        if not patterns:
            return ScanResult(scanner_name=self.name, passed=True)

        matches_to_process = []

        # 2. Find all matches across active patterns
        for p in patterns:
            try:
                compiled = re.compile(p["pattern"])
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

        # 3. Sort matches by starting index (reverse) to replace safely without offset drift
        matches_to_process.sort(key=lambda x: x["start"], reverse=True)

        # Filter out overlapping matches (left-to-right, keep earliest)
        non_overlapping = []
        last_end = 0
        for m in sorted(matches_to_process, key=lambda x: (x["start"], -len(x["original_text"]))):
            if m["start"] >= last_end:
                non_overlapping.append(m)
                last_end = m["end"]

        # Sort again by start reverse for token replacement
        non_overlapping.sort(key=lambda x: x["start"], reverse=True)

        sanitized_text = text
        detected_entities = []
        pipeline_redis_pairs = {}

        # 4. Generate vault tokens and construct replacement string
        for m in non_overlapping:
            start, end = m["start"], m["end"]
            orig = m["original_text"]
            entity = m["entity_type"]

            hex_id = uuid.uuid4().hex[:6]
            token = f"<{entity}_{hex_id}>"

            sanitized_text = sanitized_text[:start] + token + sanitized_text[end:]
            pipeline_redis_pairs[token] = orig
            detected_entities.append(entity)

        # 5. Persist tokens to Redis (TTL 1800s = 30 minutes)
        if pipeline_redis_pairs:
            try:
                pipe = redis_client.pipeline()
                for t_key, orig_val in pipeline_redis_pairs.items():
                    pipe.setex(t_key, 1800, json.dumps({"original_text": orig_val}))
                await pipe.execute()
            except Exception as e:
                logger.error(f"Failed to store custom regex vault tokens in Redis: {e}")

        return ScanResult(
            scanner_name=self.name,
            passed=True,
            sanitized_text=sanitized_text if sanitized_text != text else None,
            metadata={"detected_entities": detected_entities}
        )