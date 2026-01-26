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

# Import routers
from .routes import auth, costs, model_selection, provisioning, aggregates


# Global database bridge instance
db_bridge: DynamoDBBridge = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management."""
    global db_bridge

    # Startup
    db_bridge = DynamoDBBridge()
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
    allow_origins=["*"],  # Configure properly for production
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
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    db_healthy = await db_bridge.health_check() if db_bridge else False

    return {
        "status": "healthy" if db_healthy else "unhealthy",
        "service": settings.app_name,
        "version": settings.version,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": "connected" if db_healthy else "disconnected"
    }


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
    costs.router,
    prefix=settings.api_prefix,
    tags=["Cost Submission"]
)

app.include_router(
    aggregates.router,
    prefix=settings.api_prefix,
    tags=["Aggregates"]
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


def get_db_bridge() -> DynamoDBBridge:
    """Dependency to get database bridge."""
    return db_bridge
