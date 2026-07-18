import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
import redis.asyncio as aioredis
from dotenv import load_dotenv

# Imports de la base de données
from database import engine, Base, async_sessionmaker_local

# Imports des routeurs
from routers.scanner import router as scan_router
from routers.anonymizer import router as anonymizer_router
from routers.deanonymizer import router as deanonymizer_router
from routers.mappings import router as mappings_router
from routers.chat import router as chat_router
from routers.config import router as config_router

from presidio_analyzer import AnalyzerEngine
from services.mapping_service import get_active_mapping
from utils.glinerConfig import create_gliner_analyzer, create_gliner2_analyzer

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
REDIS_URL = os.getenv("REDIS_URL")


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
    redis_client = aioredis.from_url(REDIS_URL, encoding="utf-8", decode_responses=True)
    
    async with async_sessionmaker_local() as db_session:
        mapping = await get_active_mapping(db_session, redis_client)
        
        print("Chargement de l'Analyzer SpaCy...")
        spacy_analyzer = AnalyzerEngine()

        print("Chargement des modèles GLiNER (ONNX)...")
        gliner_analyzer = create_gliner_analyzer(entity_mapping=mapping)
        gliner2_analyzer = create_gliner2_analyzer(entity_mapping=mapping)
        
        
        app.state.redis = redis_client
        app.state.spacy_analyzer = spacy_analyzer
        app.state.gliner_analyzer = gliner_analyzer
        app.state.gliner2_analyzer = gliner2_analyzer
        print("Tous les modèles sont chargés et l'API est prête !")

    yield
    
    await redis_client.close()


app = FastAPI(lifespan=lifespan)

@app.get("/")
async def root():
    return {"message": "Hello World"}

app.include_router(scan_router)
app.include_router(anonymizer_router)
app.include_router(deanonymizer_router)
app.include_router(mappings_router)
app.include_router(chat_router)
app.include_router(config_router)