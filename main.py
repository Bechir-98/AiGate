import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as aioredis

from config import settings
from database import engine, Base, async_sessionmaker_local

from routers.scanner import router as scan_router
from routers.anonymizer import router as anonymizer_router
from routers.deanonymizer import router as deanonymizer_router
from routers.mappings import router as mappings_router
from routers.chat import router as chat_router
from routers.config import router as config_router

from presidio_analyzer import AnalyzerEngine
from services.mapping_service import get_active_mapping
from utils.glinerConfig import create_gliner_analyzer, create_gliner2_analyzer

# Configure runtime logging for container engines
logging.basicConfig(
    level=logging.INFO if settings.FASTAPI_ENV == "production" else logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("gateway_main")

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        logger.info("Verifying database schema compliance...")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    except Exception as e:
        logger.critical(f"Critical Database Setup Failure: {e}")
        raise e

    logger.info("Initializing Redis asynchronous communication channel...")
    redis_client = aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True
    )
    app.state.redis = redis_client

    try:
        async with async_sessionmaker_local() as db_session:
            logger.info("Fetching target extraction entity maps...")
            mapping = await get_active_mapping(db_session, redis_client)

            logger.info("Preloading Spacy/Presidio Natural Language Engine...")
            app.state.spacy_analyzer = AnalyzerEngine()

            logger.info("Preloading GLiNER Edge and Deep Context models into system RAM...")
            app.state.gliner_analyzer = create_gliner_analyzer(entity_mapping=mapping)
            app.state.gliner2_analyzer = create_gliner2_analyzer(entity_mapping=mapping)

        logger.info("Security mesh synchronization successful. Proxy Gateway ONLINE.")
    except Exception as e:
        logger.critical(f"Fatal Startup failure loading PII scanning structures: {e}")
        await redis_client.close()
        raise e

    yield

    logger.info("Commencing safe shutdown steps...")
    await redis_client.close()
    logger.info("Resource connection channels terminated cleanly.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    lifespan=lifespan
)

app.add_middleware(CORSMiddleware, **settings.cors_settings)

@app.get("/", tags=["Health"])
async def root():
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "environment": settings.FASTAPI_ENV
    }

# Register Endpoints
app.include_router(scan_router)
app.include_router(anonymizer_router)
app.include_router(deanonymizer_router)
app.include_router(mappings_router)
app.include_router(chat_router)
app.include_router(config_router)