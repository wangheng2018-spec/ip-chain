from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from ipchain.database import init_db
from ipchain.routes.auth import router as auth_router
from ipchain.routes.ip_assets import router as ip_router
from ipchain.routes.marketplace import router as market_router

app = FastAPI(
    title="IP-Chain API",
    description="Blockchain-based Intellectual Property Protection Platform",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

uploads_dir = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(uploads_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=uploads_dir), name="uploads")

app.include_router(auth_router)
app.include_router(ip_router)
app.include_router(market_router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/")
def root():
    return {"name": "IP-Chain API", "version": "1.0.0"}


@app.get("/health")
def health():
    return {"status": "ok"}
