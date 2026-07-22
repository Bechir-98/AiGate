import logging
import asyncio
import inspect
from typing import List, Dict, Any
from fastapi import HTTPException
from scanners.scanner import BaseScanner, ScannerStage, ScanResult, request_entities_var

logger = logging.getLogger("security_pipeline")


class ScannerPipeline:
    def __init__(self):
        self._scanners: List[BaseScanner] = []

    def register(self, scanner: BaseScanner) -> None:
        self._scanners = [s for s in self._scanners if s.name != scanner.name]
        self._scanners.append(scanner)
        logger.info(f"Registered scanner: [{scanner.name}] (stage: {scanner.stage.value})")

    def get_registered_scanners(self) -> List[str]:
        return [s.name for s in self._scanners]

    async def execute_stage(
        self,
        text: str,
        stage: ScannerStage,
        active_scanners: List[str],
        **kwargs: Any
    ) -> tuple[str, List[Dict[str, Any]]]:
        current_text = text
        audit_telemetry: List[Dict[str, Any]] = []

        entities = kwargs.get("entities")
        token = request_entities_var.set(entities)

        try:
            normalized_active = {
                s.lower().strip().replace("_", "").replace("scanner", ""): True
                for s in active_scanners
            }
            raw_normalized_active = {s.lower().strip(): True for s in active_scanners}

            for scanner in self._scanners:
                if scanner.stage != stage:
                    continue

                scanner_key = scanner.name.lower().strip().replace("_", "").replace("scanner", "")
                raw_scanner_key = scanner.name.lower().strip()

                is_active = (scanner_key in normalized_active) or (raw_scanner_key in raw_normalized_active)

                if not is_active:
                    logger.debug(f"Skipping inactive scanner: [{scanner.name}]")
                    continue

                if not getattr(scanner, "is_active", True):
                    continue

                logger.debug(f"Executing scanner [{scanner.name}] on stage [{stage.value}]")

                try:
                    if inspect.iscoroutinefunction(scanner.scan):
                        result: ScanResult = await scanner.scan(current_text, **kwargs)
                    else:
                        result: ScanResult = await asyncio.to_thread(scanner.scan, current_text, **kwargs)

                except HTTPException:
                    raise
                except Exception as e:
                    logger.error(f"Scanner [{scanner.name}] failed: {e}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"Security scanning failed at [{scanner.name}]: {str(e)}"
                    )

                if not result.passed:
                    logger.warning(f"Request blocked by [{scanner.name}]: {result.reason}")
                    raise HTTPException(
                        status_code=400,
                        detail=f"Security Policy Violation [{scanner.name}]: {result.reason}"
                    )

                if result.metadata:
                    audit_telemetry.append({
                        "scanner": scanner.name,
                        "stage": stage.value,
                        "metadata": result.metadata
                    })

                if result.sanitized_text is not None:
                    current_text = result.sanitized_text

            return current_text, audit_telemetry
        finally:
            request_entities_var.reset(token)


security_pipeline = ScannerPipeline()