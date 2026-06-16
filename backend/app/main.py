"""FastAPI application entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    await init_db()
    yield


app = FastAPI(
    title="Check-YG API",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok"}


# Register routers
from app.routers import auth_router, users_router
from app.routers.tasks import router as tasks_router
from app.routers.customers import router as customers_router
from app.routers.settings import router as settings_router
from app.routers.reviews import router as reviews_router
from app.routers.reports import router as reports_router
from app.routers.exports import router as exports_router
from app.websocket.router import router as websocket_router

app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(customers_router, prefix="/api")
app.include_router(settings_router, prefix="/api")
app.include_router(reviews_router, prefix="/api")
app.include_router(reports_router, prefix="/api")
app.include_router(exports_router, prefix="/api")
app.include_router(websocket_router)
