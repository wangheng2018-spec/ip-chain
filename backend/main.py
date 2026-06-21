"""
IP-Chain (知识产权链) – FastAPI backend application.
Blockchain-based intellectual property protection platform.
"""
import os
import logging
from pathlib import Path
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from database import init_db
from routes.auth import router as auth_router
from routes.ip_assets import router as ip_assets_router
from routes.marketplace import router as marketplace_router

# Load .env before anything else
env_path = Path(__file__).resolve().parent / ".env"
if env_path.exists():
    load_dotenv(env_path)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: initialize the database on startup."""
    logger.info("Starting IP-Chain backend ...")
    init_db()
    logger.info("Database tables initialised.")
    yield
    logger.info("Shutting down IP-Chain backend ...")


app = FastAPI(
    title="IP-Chain API",
    description="Blockchain-based Intellectual Property Protection Platform",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv(
        "CORS_ORIGINS",
        "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000",
    ).split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static file serving (uploaded files)
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

# Mount routers
app.include_router(auth_router)
app.include_router(ip_assets_router)
app.include_router(marketplace_router)


@app.get("/")
def root():
    return {
        "app": "IP-Chain",
        "version": "1.0.0",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    from blockchain.web3_helper import is_connected
    return {
        "status": "ok",
        "web3_connected": is_connected(),
    }
