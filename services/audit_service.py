import logging
from collections import Counter

from models.db_models import DetectionAudit
from database import async_sessionmaker_local

logger = logging.getLogger("audit_service")

async def audit_detected_labels(labels: list[str]) -> None:
    if not labels:
        return

    label_counts = Counter(labels)

    try:
        async with async_sessionmaker_local() as db:
            records = [
                DetectionAudit(label=label, count=count)
                for label, count in label_counts.items()
            ]
            db.add_all(records)
            await db.commit()
    except Exception as e:
        logger.error(f"Failed to save audit logs: {e}")