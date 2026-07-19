import logging
from collections import Counter

from models.db_models import DetectionAudit
from database import async_sessionmaker_local

logger = logging.getLogger("audit_service")

async def audit_detected_labels(labels: list[str]) -> None:
    """
    Background worker that aggregates and logs PII detection frequencies.
    Runs entirely off the main event loop to prevent slowing down user responses.
    """
    # Defensive check in case an empty list is accidentally passed down
    if not labels:
        return

    # Instantly aggregate occurrences (e.g., ['NAME', 'NAME', 'EMAIL'] -> {'NAME': 2, 'EMAIL': 1})
    label_counts = Counter(labels)
    
    try:
        # Open a fresh, independent database session specifically for this background task
        async with async_sessionmaker_local() as db: 
            records = [
                DetectionAudit(label=label, count=count) 
                for label, count in label_counts.items()
            ]
            
            # Batch insert all records in a single SQL transaction
            db.add_all(records)
            await db.commit()
            
    except Exception as e:
        # Catch and neatly log failures. Since this is a background task, 
        # we DO NOT raise an HTTP exception (the user is already gone).
        logger.error(f"Background Telemetry Failure: Could not save audit logs to database - {e}")