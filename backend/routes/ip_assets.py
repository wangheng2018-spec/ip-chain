"""
IP Asset management routes.
"""
import os
import hashlib
import json
import logging
import shutil
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import IPAsset, User
from routes.auth import get_current_user
from blockchain.ipfs import upload_file_to_ipfs, upload_json_to_ipfs, get_ipfs_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ip", tags=["ip-assets"])

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024


# ── Schemas ──────────────────────────────────────────────────────────────────

class IPAssetResponse(BaseModel):
    ip_asset: dict


class IPAssetListResponse(BaseModel):
    ip_assets: list[dict]
    total: int


class MintRequest(BaseModel):
    token_id: int
    tx_hash: str


class MintResponse(BaseModel):
    ip_asset: dict


# ── Upload helpers ───────────────────────────────────────────────────────────

def _ensure_upload_dir():
    """Create the upload directory and category subdirectories if they do not exist."""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _compute_sha256(file_path: Path) -> str:
    """Return the hex SHA-256 digest of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("/upload", response_model=IPAssetResponse, status_code=status.HTTP_201_CREATED)
async def upload_ip_asset(
    file: UploadFile = File(...),
    title: str = Form(...),
    description: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Upload a file + metadata and create a new IP asset record."""
    _ensure_upload_dir()

    # Validate file size
    contents = await file.read()
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {MAX_UPLOAD_SIZE_MB} MB limit",
        )

    # Save file to disk
    safe_filename = f"{hashlib.sha256(contents).hexdigest()}_{file.filename or 'unnamed'}"
    dest = UPLOAD_DIR / safe_filename
    with open(dest, "wb") as f:
        f.write(contents)

    # Compute content hash
    content_hash = _compute_sha256(dest)

    # Upload to IPFS
    ipfs_cid = upload_file_to_ipfs(str(dest), filename=file.filename)
    file_url = get_ipfs_url(ipfs_cid) if ipfs_cid else None

    # Build metadata JSON and upload to IPFS too
    metadata = {
        "title": title,
        "description": description,
        "category": category,
        "content_hash": content_hash,
        "file_url": file_url,
        "creator_wallet": current_user.wallet_address,
    }
    metadata_cid = upload_json_to_ipfs(metadata)
    thumbnail_url = get_ipfs_url(metadata_cid) if metadata_cid else None

    # Create DB record
    asset = IPAsset(
        creator_id=current_user.id,
        title=title,
        description=description,
        category=category,
        content_hash=content_hash,
        ipfs_cid=ipfs_cid,
        file_url=file_url,
        thumbnail_url=thumbnail_url,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)

    logger.info("IP asset created: id=%d title=%s", asset.id, asset.title)
    return IPAssetResponse(ip_asset=asset.to_dict())


@router.get("/{asset_id}", response_model=IPAssetResponse)
def get_ip_asset(asset_id: int, db: Session = Depends(get_db)):
    """Get details of a specific IP asset."""
    asset = db.query(IPAsset).filter(IPAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="IP asset not found")
    return IPAssetResponse(ip_asset=asset.to_dict())


@router.get("/my", response_model=IPAssetListResponse)
def get_my_ip_assets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get all IP assets owned by the current user."""
    assets = (
        db.query(IPAsset)
        .filter(IPAsset.creator_id == current_user.id)
        .order_by(IPAsset.created_at.desc())
        .all()
    )
    return IPAssetListResponse(
        ip_assets=[a.to_dict() for a in assets],
        total=len(assets),
    )


@router.post("/mint", response_model=MintResponse)
def record_mint(
    req: MintRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Record a blockchain minting transaction for an IP asset.
    The caller must first upload the asset, then call this with the
    token_id and tx_hash from the smart contract.
    """
    asset = (
        db.query(IPAsset)
        .filter(IPAsset.creator_id == current_user.id, IPAsset.token_id.is_(None))
        .order_by(IPAsset.created_at.desc())
        .first()
    )
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No unminted IP asset found for this user",
        )

    asset.token_id = req.token_id
    asset.blockchain_tx_hash = req.tx_hash
    db.commit()
    db.refresh(asset)

    logger.info("IP asset minted: id=%d token_id=%d", asset.id, asset.token_id)
    return MintResponse(ip_asset=asset.to_dict())
