import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

# Add parent directory to sys.path if running directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import init_db, get_db
from app.schemas import HealthResponse
from app.routes.parking import router as parking_router
from app.routes.bookings import router as bookings_router
from app.routes.analytics import router as analytics_router
from app.routes.predictions import router as predictions_router, get_trained_model
from app.routes.iot import router as iot_router


# Initialize DB on load to guarantee SQLite tables exist immediately
init_db()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle events: initialize SQLite database, seed demo corridor data, and warm up ML model."""
    print("=================================================================")
    print("[ParkOS] Starting Intelligent Parking Guidance Backend API")
    print("=================================================================")
    # 1. Initialize DB and seed demo data
    init_db()

    # 2. Warm up Scikit-Learn ParkSure model
    db = next(get_db())
    try:
        get_trained_model(db)
    finally:
        db.close()

    print("[ParkOS System] Ready to serve frontend and ESP32 hardware telemetry!")
    yield
    print("[ParkOS System] Shutting down.")


app = FastAPI(
    title="ParkOS API",
    description="Intelligent Parking Guidance & Commercial District Management Platform API (Indiranagar 100ft Road Corridor, Bengaluru)",
    version="1.0.0",
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json",
    lifespan=lifespan
)

# CORS Configuration
raw_origins = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173,*"
)
origins = [origin.strip() for origin in raw_origins.split(",") if origin.strip()]

# If wildcard is included, allow all origins
if "*" in origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# Health check endpoint
@app.get("/api/v1/health", response_model=HealthResponse, tags=["Health"])
def health_check(db: Session = Depends(get_db)):
    """System health check and database connectivity verification."""
    db_status = "connected"
    try:
        db.execute(text("SELECT 1"))
    except Exception as e:
        db_status = f"unhealthy: {e}"

    return HealthResponse(
        status="healthy",
        service="ParkOS Backend API",
        version="1.0.0",
        timestamp=datetime.utcnow(),
        database=db_status
    )


# Root redirect to interactive Swagger documentation
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/api/v1/docs")


# Include API Routers under /api/v1
app.include_router(parking_router, prefix="/api/v1")
app.include_router(bookings_router, prefix="/api/v1")
app.include_router(analytics_router, prefix="/api/v1")
app.include_router(predictions_router, prefix="/api/v1")
app.include_router(iot_router, prefix="/api/v1")


if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("app.main:app", host=host, port=port, reload=True)
