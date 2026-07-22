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

from config import settings
from models.models import AnonymizeRequest, PIIScanResult
from services.mapping_service import get_active_mapping
from utils.glinerConfig import update_analyzer_mappings
from utils.vault import RedisVaultOperator
from services.audit_service import audit_detected_labels
from scanners.scanner import BaseScanner, ScannerStage, ScanResult

_anonymizer_engine = AnonymizerEngine()
_anonymizer_engine.add_anonymizer(RedisVaultOperator)
_shared_pii_thread_pool = ThreadPoolExecutor(max_workers=settings.PII_THREAD_POOL_SIZE, thread_name_prefix="pii_worker")


class PiiScannerService:
    def __init__(self, thread_pool: ThreadPoolExecutor = _shared_pii_thread_pool):
        self._thread_pool = thread_pool
        self._analyzer_lock = asyncio.Lock()
        self._cached_state_hash: str = ""

    async def sync_analyzers(self, app_state: Any, db: AsyncSession) -> None:
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
        loop = asyncio.get_running_loop()

        try:
            result = await loop.run_in_executor(self._thread_pool, inference_func)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"AI inference failed: {str(e)}")

        scan_results = [
            PIIScanResult(entity_type=r.entity_type, start=r.start, end=r.end, score=r.score)
            for r in result
        ]

        detected_labels = [r.entity_type for r in scan_results]
        if detected_labels:
            background_tasks.add_task(audit_detected_labels, detected_labels)

        return AnonymizeRequest(text=content, results=scan_results)


pii_service = PiiScannerService()


async def _anonymize_scan_result(req: AnonymizeRequest, scanner_name: str = "PiiScanner") -> ScanResult:
    if not req.results:
        return ScanResult(
            scanner_name=scanner_name,
            passed=True,
            sanitized_text=req.text,
            metadata={"detected_labels": []}
        )

    analyzer_results = [
        RecognizerResult(entity_type=r.entity_type, start=r.start, end=r.end, score=r.score)
        for r in req.results
    ]

    loop = asyncio.get_running_loop()
    try:
        anonymized = await loop.run_in_executor(
            _shared_pii_thread_pool,
            lambda: _anonymizer_engine.anonymize(
                text=req.text,
                analyzer_results=analyzer_results,
                operators={"DEFAULT": OperatorConfig("redis_vault")}
            )
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PII anonymization failed: {str(e)}")

    detected_labels = list({r.entity_type for r in req.results})
    return ScanResult(
        scanner_name=scanner_name,
        passed=True,
        sanitized_text=anonymized.text,
        metadata={"detected_labels": detected_labels}
    )


class SpacyScanner(BaseScanner):
    name = "SpacyScanner"
    stage = ScannerStage.INPUT

    def __init__(self, analyzer: Any):
        self.analyzer = analyzer

    async def scan(self, text: str, **kwargs: Any) -> ScanResult:
        background_tasks = kwargs.get("background_tasks")
        if background_tasks is None:
            background_tasks = BackgroundTasks()

        req = await self.scan_text(text, background_tasks)
        return await _anonymize_scan_result(req, self.name)

    async def scan_text(self, content: str, background_tasks: BackgroundTasks) -> AnonymizeRequest:
        return await pii_service.execute_inference(
            inference_func=lambda: self.analyzer.analyze(text=content, language="en"),
            content=content,
            background_tasks=background_tasks
        )


class Gliner1Scanner(BaseScanner):
    name = "Gliner1Scanner"
    stage = ScannerStage.INPUT

    def __init__(self, analyzer: Any):
        self.analyzer = analyzer

    async def scan(self, text: str, **kwargs: Any) -> ScanResult:
        background_tasks = kwargs.get("background_tasks")
        if background_tasks is None:
            background_tasks = BackgroundTasks()

        app_state = kwargs.get("app_state")
        db = kwargs.get("db")
        entities = kwargs.get("entities")

        req = await self.scan_text(text, entities, app_state, db, background_tasks)
        return await _anonymize_scan_result(req, self.name)

    async def scan_text(
        self,
        content: str,
        entities: Optional[List[str]],
        app_state: Any,
        db: AsyncSession,
        background_tasks: BackgroundTasks
    ) -> AnonymizeRequest:
        if app_state and db:
            await pii_service.sync_analyzers(app_state, db)
        return await pii_service.execute_inference(
            inference_func=lambda: self.analyzer.analyze(text=content, language="en", entities=entities),
            content=content,
            background_tasks=background_tasks
        )


class Gliner2Scanner(BaseScanner):
    name = "Gliner2Scanner"
    stage = ScannerStage.INPUT

    def __init__(self, analyzer: Any):
        self.analyzer = analyzer

    async def scan(self, text: str, **kwargs: Any) -> ScanResult:
        background_tasks = kwargs.get("background_tasks")
        if background_tasks is None:
            background_tasks = BackgroundTasks()

        app_state = kwargs.get("app_state")
        db = kwargs.get("db")
        entities = kwargs.get("entities")

        req = await self.scan_text(text, entities, app_state, db, background_tasks)
        return await _anonymize_scan_result(req, self.name)

    async def scan_text(
        self,
        content: str,
        entities: Optional[List[str]],
        app_state: Any,
        db: AsyncSession,
        background_tasks: BackgroundTasks
    ) -> AnonymizeRequest:
        if app_state and db:
            await pii_service.sync_analyzers(app_state, db)
        return await pii_service.execute_inference(
            inference_func=lambda: self.analyzer.analyze(text=content, language="en", entities=entities),
            content=content,
            background_tasks=background_tasks
        )