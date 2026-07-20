import asyncio
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Callable, Any
from fastapi import BackgroundTasks, HTTPException
from presidio_analyzer import RecognizerResult
from presidio_anonymizer import AnonymizerEngine
from presidio_anonymizer.entities import OperatorConfig
from sqlalchemy.ext.asyncio import AsyncSession

from models.models import AnonymizeRequest, PIIScanResult
from services.mapping_service import get_active_mapping
from utils.glinerConfig import update_analyzer_mappings
from utils.vault import RedisVaultOperator
from services.audit_service import audit_detected_labels
from scanners.scanner import BaseScanner, ScannerStage, ScanResult

_anonymizer_engine = AnonymizerEngine()
_anonymizer_engine.add_anonymizer(RedisVaultOperator)
_anonymize_thread_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="pii_anon")


class PiiScannerService:
    """Handles thread pool execution, analyzer state sync, and audit logging."""
    
    def __init__(self, max_workers: int = 8):
        self._thread_pool = ThreadPoolExecutor(max_workers=max_workers)
        self._analyzer_lock = asyncio.Lock()
        self._cached_state_hash: str = ""

    async def sync_analyzers(
        self, 
        app_state: Any, 
        db: AsyncSession
    ) -> None:
        """Safely mutates shared GLiNER analyzer state using locking and hashing."""
        redis_client = app_state.redis
        mapping = await get_active_mapping(db, redis_client)

        state_data = json.dumps(mapping, sort_keys=True)
        new_hash = hashlib.md5(state_data.encode()).hexdigest()

        if new_hash == self._cached_state_hash:
            return

        async with self._analyzer_lock:
            if new_hash == self._cached_state_hash:
                return

            update_analyzer_mappings(app_state.gliner_analyzer, mapping)
            update_analyzer_mappings(app_state.gliner2_analyzer, mapping)
            self._cached_state_hash = new_hash

    async def execute_inference(
        self,
        inference_func: Callable[[], Any],
        content: str,
        background_tasks: BackgroundTasks
    ) -> AnonymizeRequest:
        """Offloads AI inference to the thread pool and records audit telemetry."""
        loop = asyncio.get_event_loop()
        
        try:
            result = await loop.run_in_executor(self._thread_pool, inference_func)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"AI Inference Engine failed: {str(e)}")

        scan_results = [
            PIIScanResult(entity_type=r.entity_type, start=r.start, end=r.end, score=r.score)
            for r in result
        ]
        
        detected_labels = [r.entity_type for r in scan_results]
        if detected_labels:
            background_tasks.add_task(audit_detected_labels, detected_labels)

        return AnonymizeRequest(text=content, results=scan_results)


pii_service = PiiScannerService()


class PiiScanner(BaseScanner):
    """Base PII Scanner class."""
    name = "PiiScanner"
    stage = ScannerStage.INPUT

    async def scan(self, text: str, **kwargs: Any) -> ScanResult:
        return ScanResult(scanner_name=self.name, passed=True)


class SpacyScanner(PiiScanner):
    name = "SpacyScanner"

    def __init__(self, analyzer: Any):
        self.analyzer = analyzer

    async def scan(self, text: str, **kwargs: Any) -> ScanResult:
        background_tasks: BackgroundTasks = kwargs.get("background_tasks")
        if background_tasks is None:
            from fastapi import BackgroundTasks
            background_tasks = BackgroundTasks()

        req = await pii_service.execute_inference(
            inference_func=lambda: self.analyzer.analyze(text=text, language="en"),
            content=text,
            background_tasks=background_tasks
        )
        return await _anonymize_scan_result(req)

    async def scan_text(self, content: str, background_tasks: BackgroundTasks) -> AnonymizeRequest:
        return await pii_service.execute_inference(
            inference_func=lambda: self.analyzer.analyze(text=content, language="en"),
            content=content,
            background_tasks=background_tasks
        )


class Gliner1Scanner(PiiScanner):
    name = "Gliner1Scanner"

    def __init__(self, analyzer: Any):
        self.analyzer = analyzer

    async def scan(self, text: str, **kwargs: Any) -> ScanResult:
        background_tasks: BackgroundTasks = kwargs.get("background_tasks")
        if background_tasks is None:
            from fastapi import BackgroundTasks
            background_tasks = BackgroundTasks()
        app_state = kwargs.get("app_state")
        db = kwargs.get("db")
        entities = kwargs.get("entities")

        if app_state and db:
            await pii_service.sync_analyzers(app_state, db)

        req = await pii_service.execute_inference(
            inference_func=lambda: self.analyzer.analyze(text=text, language="en", entities=entities),
            content=text,
            background_tasks=background_tasks
        )
        return await _anonymize_scan_result(req)

    async def scan_text(
        self, 
        content: str, 
        entities: Optional[List[str]], 
        app_state: Any, 
        db: AsyncSession, 
        background_tasks: BackgroundTasks
    ) -> AnonymizeRequest:
        await pii_service.sync_analyzers(app_state, db)
        return await pii_service.execute_inference(
            inference_func=lambda: self.analyzer.analyze(text=content, language="en", entities=entities),
            content=content,
            background_tasks=background_tasks
        )


class Gliner2Scanner(PiiScanner):
    name = "Gliner2Scanner"

    def __init__(self, analyzer: Any):
        self.analyzer = analyzer

    async def scan(self, text: str, **kwargs: Any) -> ScanResult:
        background_tasks: BackgroundTasks = kwargs.get("background_tasks")
        if background_tasks is None:
            from fastapi import BackgroundTasks
            background_tasks = BackgroundTasks()
        app_state = kwargs.get("app_state")
        db = kwargs.get("db")
        entities = kwargs.get("entities")

        if app_state and db:
            await pii_service.sync_analyzers(app_state, db)

        req = await pii_service.execute_inference(
            inference_func=lambda: self.analyzer.analyze(text=text, language="en", entities=entities),
            content=text,
            background_tasks=background_tasks
        )
        return await _anonymize_scan_result(req)

    async def scan_text(
        self, 
        content: str, 
        entities: Optional[List[str]], 
        app_state: Any, 
        db: AsyncSession, 
        background_tasks: BackgroundTasks
    ) -> AnonymizeRequest:
        await pii_service.sync_analyzers(app_state, db)
        return await pii_service.execute_inference(
            inference_func=lambda: self.analyzer.analyze(text=content, language="en", entities=entities),
            content=content,
            background_tasks=background_tasks
        )


async def _anonymize_scan_result(req: AnonymizeRequest) -> ScanResult:
    """Converts PII detection results into a ScanResult with vault-tokenized text."""
    if not req.results:
        return ScanResult(
            scanner_name="PiiScanner",
            passed=True,
            sanitized_text=req.text,
            metadata={"detected_labels": []}
        )

    analyzer_results = [
        RecognizerResult(entity_type=r.entity_type, start=r.start, end=r.end, score=r.score)
        for r in req.results
    ]

    loop = asyncio.get_event_loop()
    try:
        anonymized = await loop.run_in_executor(
            _anonymize_thread_pool,
            lambda: _anonymizer_engine.anonymize(
                text=req.text,
                analyzer_results=analyzer_results,
                operators={"DEFAULT": OperatorConfig("redis_vault")}
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PII Anonymization failed: {str(e)}")

    detected_labels = list({r.entity_type for r in req.results})
    return ScanResult(
        scanner_name="PiiScanner",
        passed=True,
        sanitized_text=anonymized.text,
        metadata={"detected_labels": detected_labels}
    )