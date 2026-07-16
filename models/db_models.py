from sqlalchemy import Column, Integer, String, Boolean
from database import Base

class DBEntityMapping(Base):
    __tablename__ = "entity_mappings"
    id = Column(Integer, primary_key=True, index=True)
    gliner_label = Column(String, unique=True, index=True, nullable=False)
    presidio_label = Column(String, nullable=False)                        
    is_active = Column(Boolean, default=True)                              

class AppConfig(Base):
    __tablename__ = "app_config"
    
    key = Column(String, primary_key=True, index=True) #active_scanner
    value = Column(String, nullable=False)
