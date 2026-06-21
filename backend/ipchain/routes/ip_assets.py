import hashlib
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc

from ipchain.database import get_db
from ipchain.models import IPAsset, User
from ipchain.routes.auth import get_current_user
from ipchain.blockchain import ipfs

router = APIRouter(prefix="/api/ip", tags=["ip-assets"])

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)


class IPAssetResponse(BaseModel):
    id: int
    token_id: Optional[int]
    creator_id: int
    title: str
    description: str
    category: str
    content_hash: str
    ipfs_cid: Optional[str]
    file_url: Optional[str]
    thumbnail_url: Optional[str]
    created_at: str
    is_listed: bool
    price_wei: Optional[int]
    blockchain_tx_hash: Optional[str]
    creator_username: Optional[str]
    creator_wallet: Optional[str]


class IPListResponse(BaseModel):
    items: list[IPAssetResponse]
    total: int


class MintRequest(BaseModel):
    token_id: int
    tx_hash: str


class MintResponse(BaseModel):
    id: int
    token_id: int
    blockchain_tx_hash: str


def _serialize_asset(asset: IPAsset) -> IPAssetResponse:
    creator_username = None
    creator_wallet = None
    if asset.creator:
        creator_username = asset.creator.username
        creator_wallet = asset.creator.wallet_address
    return IPAssetResponse(
        id=asset.id,
        token_id=asset.token_id,
        creator_id=asset.creator_id,
        title=asset.title,
        description=asset.description or "",
        category=asset.category or "other",
        content_hash=asset.content_hash,
        ipfs_cid=asset.ipfs_cid,
        file_url=asset.file_url,
        thumbnail_url=asset.thumbnail_url,
        created_at=asset.created_at.isoformat() if asset.created_at else "",
        is_listed=asset.is_listed or False,
        price_wei=asset.price_wei,
        blockchain_tx_hash=asset.blockchain_tx_hash,
        creator_username=creator_username,
        creator_wallet=creator_wallet,
    )


@router.post("/upload", response_model=IPAssetResponse, status_code=201)
async def upload_ip(
    title: str = Form(...),
    description: str = Form(""),
    category: str = Form("other"),
    file: UploadFile = File(...),
    thumbnail: Optional[UploadFile] = File(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file.")

    content_hash = hashlib.sha256(file_bytes).hexdigest()

    existing = db.query(IPAsset).filter(IPAsset.content_hash == content_hash).first()
    if existing:
        raise HTTPException(status_code=409, detail="IP asset with this content hash already exists.")

    ext = os.path.splitext(file.filename or "file")[1] or ""
    safe_name = f"{uuid.uuid4().hex}{ext}"
    file_path = os.path.join(UPLOAD_DIR, safe_name)
    with open(file_path, "wb") as f:
        f.write(file_bytes)

    file_url_path = f"/uploads/{safe_name}"

    thumbnail_url = None
    if thumbnail:
        thumb_bytes = await thumbnail.read()
        if thumb_bytes:
            thumb_ext = os.path.splitext(thumbnail.filename or "thumb")[1] or ".jpg"
            thumb_name = f"{uuid.uuid4().hex}{thumb_ext}"
            thumb_path = os.path.join(UPLOAD_DIR, thumb_name)
            with open(thumb_path, "wb") as f:
                f.write(thumb_bytes)
            thumbnail_url = f"/uploads/{thumb_name}"

    ipfs_cid = None
    try:
        ipfs_cid = ipfs.upload_file_to_ipfs(file_bytes, file.filename or "asset")
    except RuntimeError:
        pass

    asset = IPAsset(
        creator_id=user.id,
        title=title,
        description=description,
        category=category,
        content_hash=content_hash,
        ipfs_cid=ipfs_cid,
        file_url=file_url_path,
        thumbnail_url=thumbnail_url,
        created_at=datetime.now(timezone.utc),
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)

    return _serialize_asset(asset)


@router.get("/my", response_model=IPListResponse)
def get_my_assets(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    assets = (
        db.query(IPAsset)
        .filter(IPAsset.creator_id == user.id)
        .order_by(desc(IPAsset.created_at))
        .all()
    )
    return IPListResponse(
        items=[_serialize_asset(a) for a in assets],
        total=len(assets),
    )


@router.get("/{asset_id}", response_model=IPAssetResponse)
def get_ip_asset(asset_id: int, db: Session = Depends(get_db)):
    asset = db.query(IPAsset).filter(IPAsset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="IP asset not found.")
    return _serialize_asset(asset)


@router.post("/mint", response_model=MintResponse)
def record_mint(
    req: MintRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    asset = db.query(IPAsset).filter(IPAsset.id == req.token_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="IP asset not found.")
    if asset.creator_id != user.id:
        raise HTTPException(status_code=403, detail="Not your asset to mint.")
    if asset.blockchain_tx_hash:
        raise HTTPException(status_code=409, detail="Already minted on-chain.")

    asset.token_id = req.token_id
    asset.blockchain_tx_hash = req.tx_hash
    db.commit()
    db.refresh(asset)

    return MintResponse(
        id=asset.id,
        token_id=asset.token_id,
        blockchain_tx_hash=asset.blockchain_tx_hash,
    )
