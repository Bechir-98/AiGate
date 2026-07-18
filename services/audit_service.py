from collections import Counter
from models.db_models import DetectionAudit
from database import async_sessionmaker_local

async def audit_detected_labels(labels: list[str]):
    if not labels:
        return

    label_counts = Counter(labels)
    
    async with async_sessionmaker_local() as db: 
        records = [
            DetectionAudit(label=label, count=count) 
            for label, count in label_counts.items()
        ]
        db.add_all(records)
        await db.commit()