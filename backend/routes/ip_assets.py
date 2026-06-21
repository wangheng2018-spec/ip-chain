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

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import IPAsset, User
from routes.auth import get_current_user
from blockchain.ipfs import upload_file_to_ipfs, upload_json_to_ipfs, get_ipfs_url
from blockchain.web3_helper import verify_content as bc_verify_content

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ip", tags=["ip-assets"])

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", "./uploads"))
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "50"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_SIZE_MB * 1024 * 1024
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")


# ── Schemas ────────────────────────────────────────────────────────────────────

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


class VerifyResponse(BaseModel):
    registered: bool
    details: Optional[dict] = None


class ShareResponse(BaseModel):
    platform_urls: dict[str, str]
    metadata: dict


# ── Upload helpers ─────────────────────────────────────────────────────────────

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


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/verify", response_model=VerifyResponse)
def verify_ip_asset(
    hash: str = Query(..., description="SHA-256 hash of the content to verify"),
    db: Session = Depends(get_db),
):
    """
    Verify whether content with the given SHA-256 hash is registered on the
    blockchain. Checks both the local database and the smart contract.
    """
    if len(hash) != 64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid SHA-256 hash — must be 64 hex characters",
        )

    # Check the local database first
    asset = db.query(IPAsset).filter(IPAsset.content_hash == hash).first()

    # Check the blockchain via the smart contract
    chain_result = bc_verify_content(hash)

    if chain_result and chain_result.get("exists"):
        return VerifyResponse(
            registered=True,
            details={
                "source": "blockchain",
                "token_id": chain_result["token_id"],
                "owner": chain_result["owner"],
                "blockchain_tx_hash": asset.blockchain_tx_hash if asset else None,
                "title": asset.title if asset else None,
                "created_at": asset.created_at.isoformat() if asset else None,
            },
        )

    if asset and asset.blockchain_tx_hash:
        return VerifyResponse(
            registered=True,
            details={
                "source": "database",
                "token_id": asset.token_id,
                "content_hash": asset.content_hash,
                "title": asset.title,
                "created_at": asset.created_at.isoformat(),
            },
        )

    return VerifyResponse(
        registered=False,
        details={
            "message": "Content hash not found on blockchain or in local records",
            "db_found": asset is not None,
            "chain_found": chain_result.get("exists", False) if chain_result else False,
        },
    )


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


@router.get("/{asset_id}/share", response_model=ShareResponse)
def share_ip_asset(asset_id: int, db: Session = Depends(get_db)):
    """
    Return share URLs and metadata for social platforms (Twitter/X, Telegram, etc.).
    """
    asset = db.query(IPAsset).filter(IPAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="IP asset not found")

    asset_url = f"{FRONTEND_URL}/asset/{asset.id}"
    share_text = f"Check out this IP asset on IP-Chain: {asset.title}"

    return ShareResponse(
        platform_urls={
            "twitter": f"https://twitter.com/intent/tweet?text={_url_encode(share_text)}&url={_url_encode(asset_url)}",
            "telegram": f"https://t.me/share/url?url={_url_encode(asset_url)}&text={_url_encode(share_text)}",
            "facebook": f"https://www.facebook.com/sharer/sharer.php?u={_url_encode(asset_url)}",
            "linkedin": f"https://www.linkedin.com/sharing/share-offsite/?url={_url_encode(asset_url)}",
            "reddit": f"https://reddit.com/submit?url={_url_encode(asset_url)}&title={_url_encode(share_text)}",
            "copy_link": asset_url,
        },
        metadata={
            "title": asset.title,
            "description": asset.description or "",
            "content_hash": asset.content_hash,
            "token_id": asset.token_id,
            "url": asset_url,
            "thumbnail_url": asset.thumbnail_url,
            "creator": asset.creator.to_dict() if asset.creator else None,
        },
    )


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


# ── Helpers ────────────────────────────────────────────────────────────────────

def _url_encode(text: str) -> str:
    """Percent-encode a string for use in a URL query parameter."""
    import urllib.parse
    return urllib.parse.quote(text, safe="")
