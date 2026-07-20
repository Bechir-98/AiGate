import logging
import asyncio
import inspect
from typing import List, Dict, Any
from fastapi import HTTPException
from scanners.scanner import BaseScanner, ScannerStage, ScanResult, request_entities_var

logger = logging.getLogger("security_pipeline")


class ScannerPipeline:
    """
    Central pipeline orchestrator for security and PII scanners.
    
    Responsibilities:
    - Registers scanner instances into an ordered chain.
    - Dynamically filters scanners based on current active DB/Redis configuration.
    - Propagates text transformations (e.g., anonymized prompts) downstream.
    - Captures audit telemetry and handles policy enforcement (400 blocks).
    """

    def __init__(self):
        self._scanners: List[BaseScanner] = []

    def register(self, scanner: BaseScanner) -> None:
        """
        Registers a scanner instance into the pipeline execution sequence.
        Replaces any previously registered scanner with the same name.
        """
        self._scanners = [s for s in self._scanners if s.name != scanner.name]
        self._scanners.append(scanner)
        logger.info(f"Pipeline registered scanner: [{scanner.name}] (Stage: {scanner.stage.value})")

    def get_registered_scanners(self) -> List[str]:
        """Returns the list of names of all registered scanners."""
        return [s.name for s in self._scanners]

    async def execute_stage(
        self,
        text: str,
        stage: ScannerStage,
        active_scanners: List[str],
        **kwargs: Any
    ) -> tuple[str, List[Dict[str, Any]]]:
        """
        Executes all active scanners assigned to the specified stage in registration order.

        :param text: Input/output string to be analyzed and potentially sanitized.
        :param stage: ScannerStage.INPUT or ScannerStage.OUTPUT.
        :param active_scanners: List of scanner names currently enabled via DB/Redis config.
        :param kwargs: Dynamic context passed to scanners (db, background_tasks, app_state, entities, etc.).
        :return: Tuple containing (final_sanitized_text, aggregated_audit_telemetry).
        """
        current_text = text
        audit_telemetry: List[Dict[str, Any]] = []

        # Bind the dynamic request-specific entities
        entities = kwargs.get("entities")
        token = request_entities_var.set(entities)

        try:
            # Normalize active scanners list to lowercase for case-insensitive matching
            normalized_active = [s.lower().strip() for s in active_scanners]

            for scanner in self._scanners:
                # 1. Skip scanners that do not match the target stage
                if scanner.stage != stage:
                    continue

                # 2. Case-insensitive name matching (e.g., "PromptGuard" matches "prompt_guard")
                scanner_name_normalized = scanner.name.lower().replace("_", "").replace("scanner", "")
                active_normalized = [s.replace("_", "").replace("scanner", "") for s in normalized_active]

                if scanner_name_normalized not in active_normalized and scanner.name.lower() not in normalized_active:
                    logger.debug(f"Skipping inactive scanner: [{scanner.name}]")
                    continue

                # 3. Skip manually disabled scanner instances
                if not getattr(scanner, "is_active", True):
                    continue

                logger.debug(f"Executing scanner [{scanner.name}] on stage [{stage.value}]")

                try:
                    # 4. Safely handle both async and sync CPU-heavy scan methods
                    if inspect.iscoroutinefunction(scanner.scan):
                        result: ScanResult = await scanner.scan(current_text, **kwargs)
                    else:
                        result: ScanResult = await asyncio.to_thread(scanner.scan, current_text, **kwargs)

                except HTTPException:
                    # Re-raise deliberate HTTP exceptions without wrapping them into a 500 error
                    raise
                except Exception as e:
                    logger.error(f"Execution failure in scanner [{scanner.name}]: {e}")
                    raise HTTPException(
                        status_code=500,
                        detail=f"Security scanning engine failed at [{scanner.name}]: {str(e)}"
                    )

                # 5. Enforce Security Policy Violation (Hard Block)
                if not result.passed:
                    logger.warning(f"Request BLOCKED by scanner [{scanner.name}]: {result.reason}")
                    raise HTTPException(
                        status_code=400,
                        detail=f"Security Policy Violation [{scanner.name}]: {result.reason}"
                    )

                # 6. Collect audit telemetry metadata
                if result.metadata:
                    audit_telemetry.append({
                        "scanner": scanner.name,
                        "stage": stage.value,
                        "metadata": result.metadata
                    })

                # 7. Apply text sanitization (e.g., PII anonymization) downstream
                if result.sanitized_text is not None:
                    current_text = result.sanitized_text

            return current_text, audit_telemetry
        finally:
            request_entities_var.reset(token)


# Global singleton instance imported across main.py and routers
security_pipeline = ScannerPipeline()