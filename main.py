import logging
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import redis.asyncio as aioredis

from config import settings
from database import engine, Base, async_sessionmaker_local

# Routers
from routers.scanner import router as scan_router
from routers.anonymizer import router as anonymizer_router
from routers.deanonymizer import router as deanonymizer_router
from routers.mappings import router as mappings_router
from routers.chat import router as chat_router
from routers.config import router as config_router
from routers.regex_patterns import router as regex_patterns_router

# Services & PII Analyzers
from presidio_analyzer import AnalyzerEngine
from services.mapping_service import get_active_mapping
from services.model_loader import load_text_classification_pipeline
from utils.glinerConfig import create_gliner_analyzer, create_gliner2_analyzer

# Security Scanners Pipeline
from scanners.pipeline import security_pipeline
from scanners.input_scanners.prompt_guard import PromptGuardScanner
from scanners.input_scanners.toxicity_scanner import ToxicityScanner
from scanners.input_scanners.regex_scanner import CustomRegexScanner
from scanners.scanner import ScannerStage
from scanners.input_scanners.pii_scanner import SpacyScanner, Gliner1Scanner, Gliner2Scanner

if settings.HF_TOKEN:
    os.environ["HF_TOKEN"] = settings.HF_TOKEN

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

            # 1. Load PII Engines
            logger.info("Preloading Spacy/Presidio Natural Language Engine...")
            app.state.spacy_analyzer = AnalyzerEngine()

            logger.info("Preloading GLiNER Edge and Deep Context models...")
            app.state.gliner_analyzer = create_gliner_analyzer(entity_mapping=mapping)
            os.environ.setdefault("GLINER2_MODEL_PATH", settings.GLINER2_MODEL_PATH)
            app.state.gliner2_analyzer = create_gliner2_analyzer(entity_mapping=mapping)

            # 2. Load Security Guardrails using the Model Loader Service
            pg_pipe = load_text_classification_pipeline(
                model_id=settings.PROMPT_GUARD_MODEL_ID,
                hf_token=settings.HF_TOKEN,
                is_gated=("meta-llama" in settings.PROMPT_GUARD_MODEL_ID)
            )

            tox_pipe = load_text_classification_pipeline(
                model_id=settings.TOXIC_BERT_MODEL_ID,
                hf_token=settings.HF_TOKEN
            )

            # 3. Register Scanners to Pipeline
            logger.info("Registering all scanners into the Security Pipeline...")
            security_pipeline.register(PromptGuardScanner(pipeline=pg_pipe))
            security_pipeline.register(CustomRegexScanner())
            security_pipeline.register(SpacyScanner(analyzer=app.state.spacy_analyzer))
            security_pipeline.register(Gliner1Scanner(analyzer=app.state.gliner_analyzer))
            security_pipeline.register(Gliner2Scanner(analyzer=app.state.gliner2_analyzer))
            
            try:
                security_pipeline.register(ToxicityScanner(pipeline=tox_pipe, stage=ScannerStage.INPUT))
            except Exception as e:
                logger.warning(f"Toxicity scanner registration skipped: {e}")

        logger.info("Security mesh synchronization successful. Proxy Gateway ONLINE.")
    except Exception as e:
        logger.critical(f"Fatal Startup failure loading AI models: {e}")
        await redis_client.close()
        raise e

    yield

    logger.info("Commencing safe shutdown steps...")
    try:
        logger.info("Terminating global thread pools...")
        from scanners.input_scanners.pii_scanner import _anonymize_thread_pool, pii_service
        from routers.deanonymizer import _io_unvault_pool
        from routers.anonymizer import _io_network_pool
        
        _anonymize_thread_pool.shutdown(wait=True)
        pii_service._thread_pool.shutdown(wait=True)
        _io_unvault_pool.shutdown(wait=True)
        _io_network_pool.shutdown(wait=True)
    except Exception as shutdown_err:
        logger.warning(f"Error during thread pool shutdown: {shutdown_err}")

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
app.include_router(regex_patterns_router)