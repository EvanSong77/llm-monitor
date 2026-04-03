"""Application entry point."""

import logging
from pathlib import Path

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from llm_monitor.api import router
from llm_monitor.core.config import settings
from llm_monitor.services.metrics_query import query_service
from llm_monitor.services.vllm_collector import collector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Static path
static_path = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info(f"Starting {settings.app_name} v{settings.app_version}")

    # Initialize services
    es_available = False
    try:
        logger.info("Initializing vLLM collector...")
        await collector.initialize()
        if collector.es_client and collector.es_client.ping():
            es_available = True
            logger.info("Elasticsearch connection successful")
        else:
            logger.warning("Elasticsearch not available - monitoring features will be limited")

        logger.info("Initializing query service...")
        await query_service.initialize()
        
        # Connect query service to collector's cache for instant access
        query_service.set_cache(collector.cache)

        # Only start metrics collection if ES is available
        if es_available:
            logger.info("Starting metrics collection...")
            collector.start()
        else:
            logger.info("Metrics collection disabled - Elasticsearch not available")

        logger.info("All services initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}", exc_info=True)
        logger.warning("Application will start with limited functionality")

    # Store ES availability in app state for frontend to check
    app.state.es_available = es_available

    yield

    # Shutdown
    logger.info("Stopping metrics collection...")
    await collector.close()
    logger.info("Shutting down...")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="vLLM instance monitoring and observability platform",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API router
app.include_router(router, prefix="/api/v1")


@app.get("/")
async def root():
    """Serve the main dashboard."""
    static_file = static_path / "index.html"
    if static_file.exists():
        return FileResponse(str(static_file))
    return {"message": "vLLM Monitor API", "docs": "/docs"}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    es_available = getattr(app.state, "es_available", False)
    return {
        "status": "healthy",
        "version": settings.app_version,
        "elasticsearch": "available" if es_available else "unavailable"
    }


# Mount static files (must be after route definitions)
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")
