from datetime import datetime, timezone
from sqlalchemy import String, Boolean, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column
from database import Base

class DBEntityMapping(Base):
    """
    Manages custom PII classification entity mappings.
    Bridges natural language labels to structural storage formats.
    """
    __tablename__ = "entity_mappings"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    gliner_label: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    presidio_label: Mapped[str] = mapped_column(String, nullable=False)                                      
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)                            


class AppConfig(Base):
    """
    Stores key-value pairs for dynamic gateway configuration rules.
    """
    __tablename__ = "app_config"
    
    key: Mapped[str] = mapped_column(String, primary_key=True, index=True)
    value: Mapped[str] = mapped_column(String, nullable=False)


class DetectionAudit(Base):
    """
    Logs frequency telemetry on caught PII types for analysis dashboards.
    """
    __tablename__ = "detection_audit"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    label: Mapped[str] = mapped_column(String, index=True, nullable=False) 
    count: Mapped[int] = mapped_column(Integer, nullable=False)
    
    # Enforces database-level timezone retention (TIMESTAMPTZ)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc), 
        nullable=False
    )