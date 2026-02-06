"""Main FastAPI application."""

from contextlib import asynccontextmanager
import time
from datetime import datetime, timezone
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from ..core.config import settings
from ..core.exceptions import BaseAPIException
from ..infrastructure.database.dynamodb_bridge import DynamoDBBridge
from ..domain.services.inference_profile_service import InferenceProfileService
# Import routers
from .routes import auth, usage, model_selection, provisioning, aggregates, inference_profiles

# Import dependencies
from . import dependencies


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    # Startup
    dependencies.db_bridge = DynamoDBBridge()

    # Initialize inference profile service
    dependencies.inference_profile_service = InferenceProfileService(dependencies.db_bridge)

    print(f"Starting {settings.app_name} v{settings.version}")

    yield

    # Shutdown
    print("Shutting down application")


# Create FastAPI application
app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,
    redoc_url="/redoc" if settings.debug else None
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request timing middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    """Add processing time header to responses."""
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response


# Exception handlers
@app.exception_handler(BaseAPIException)
async def api_exception_handler(request: Request, exc: BaseAPIException):
    """Handle custom API exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error_code,
            "message": exc.detail.get("message"),
            "details": exc.detail.get("details", {}),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    print(f"Unexpected error: {exc}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "INTERNAL_ERROR",
            "message": "An unexpected error occurred",
            "details": {},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    )


# Health check endpoint
@app.get("/health", status_code=200)
async def health_check():
    """Health check endpoint."""
    import time
    from fastapi.responses import JSONResponse

    # Measure database latency
    db_start = time.time()
    db_healthy = await dependencies.db_bridge.health_check() if dependencies.db_bridge else False
    db_latency_ms = int((time.time() - db_start) * 1000)

    # Build database status object
    if db_healthy:
        database_status = {
            "status": "connected",
            "latency_ms": db_latency_ms
        }
        overall_status = "healthy"
        status_code = 200
    else:
        database_status = {
            "status": "disconnected",
            "error": "Health check failed"
        }
        overall_status = "unhealthy"
        status_code = 503

    response = {
        "status": overall_status,
        "service": settings.app_name,
        "version": settings.version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": database_status
    }

    return JSONResponse(content=response, status_code=status_code)


# Include routers
app.include_router(
    auth.router,
    prefix="/auth",
    tags=["Authentication"]
)

app.include_router(
    provisioning.router,
    prefix=settings.api_prefix,
    tags=["Provisioning"]
)

app.include_router(
    model_selection.router,
    prefix=settings.api_prefix,
    tags=["Model Selection"]
)

app.include_router(
    usage.router,
    prefix=settings.api_prefix,
    tags=["Usage Submission"]
)

app.include_router(
    aggregates.router,
    prefix=settings.api_prefix,
    tags=["Aggregates"]
)

app.include_router(
    inference_profiles.router,
    prefix=settings.api_prefix,
    tags=["Inference Profiles"]
)


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": settings.app_name,
        "version": settings.version,
        "docs": "/docs" if settings.debug else "disabled",
        "health": "/health"
    }
