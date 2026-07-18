from sqlalchemy import Column, Integer, String, Boolean, DateTime 
from database import Base
from datetime import datetime, timezone

class DBEntityMapping(Base):
    __tablename__ = "entity_mappings"
    id = Column(Integer, primary_key=True, index=True)
    gliner_label = Column(String, unique=True, index=True, nullable=False)
    presidio_label = Column(String, nullable=False)                        
    is_active = Column(Boolean, default=True)                              

class AppConfig(Base):
    __tablename__ = "app_config"
    key = Column(String, primary_key=True, index=True)
    value = Column(String, nullable=False)

class DetectionAudit(Base):
    __tablename__ = "detection_audit"
    id = Column(Integer, primary_key=True, index=True)
    label = Column(String, index=True, nullable=False) 
    count = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)