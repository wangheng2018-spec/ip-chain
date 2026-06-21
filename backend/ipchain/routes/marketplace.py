from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc

from ipchain.database import get_db
from ipchain.models import IPAsset, Transaction, User
from ipchain.routes.auth import get_current_user

router = APIRouter(prefix="/api/market", tags=["marketplace"])


class ListingResponse(BaseModel):
    id: int
    token_id: Optional[int]
    title: str
    description: str
    category: str
    content_hash: str
    ipfs_cid: Optional[str]
    file_url: Optional[str]
    thumbnail_url: Optional[str]
    created_at: str
    price_wei: int
    creator_username: Optional[str]
    creator_wallet: Optional[str]


class ListingListResponse(BaseModel):
    items: list[ListingResponse]
    total: int
    page: int
    page_size: int


class ListForSaleRequest(BaseModel):
    token_id: int
    price_wei: int
    tx_hash: Optional[str] = None


class BuyRequest(BaseModel):
    token_id: int
    price_wei: int
    tx_hash: str


class TransactionResponse(BaseModel):
    id: int
    token_id: int
    seller_wallet: str
    buyer_wallet: str
    price_wei: int
    tx_hash: str
    timestamp: str


class TransactionListResponse(BaseModel):
    items: list[TransactionResponse]
    total: int


def _serialize_listing(asset: IPAsset) -> ListingResponse:
    creator_username = None
    creator_wallet = None
    if asset.creator:
        creator_username = asset.creator.username
        creator_wallet = asset.creator.wallet_address
    return ListingResponse(
        id=asset.id,
        token_id=asset.token_id,
        title=asset.title,
        description=asset.description or "",
        category=asset.category or "other",
        content_hash=asset.content_hash,
        ipfs_cid=asset.ipfs_cid,
        file_url=asset.file_url,
        thumbnail_url=asset.thumbnail_url,
        created_at=asset.created_at.isoformat() if asset.created_at else "",
        price_wei=asset.price_wei or 0,
        creator_username=creator_username,
        creator_wallet=creator_wallet,
    )


@router.get("/listings", response_model=ListingListResponse)
def get_listings(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    query = db.query(IPAsset).filter(IPAsset.is_listed == True)

    if category:
        query = query.filter(IPAsset.category == category)

    total = query.count()
    assets = (
        query.order_by(desc(IPAsset.created_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return ListingListResponse(
        items=[_serialize_listing(a) for a in assets],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/list", status_code=201)
def list_for_sale(
    req: ListForSaleRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    asset = db.query(IPAsset).filter(IPAsset.id == req.token_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="IP asset not found.")
    if asset.creator_id != user.id:
        raise HTTPException(status_code=403, detail="Only the owner can list this asset.")
    if req.price_wei <= 0:
        raise HTTPException(status_code=400, detail="Price must be greater than 0.")

    asset.is_listed = True
    asset.price_wei = req.price_wei
    if req.tx_hash:
        asset.blockchain_tx_hash = req.tx_hash
    db.commit()

    return {"message": "IP asset listed for sale.", "token_id": req.token_id, "price_wei": req.price_wei}


@router.post("/buy", status_code=201)
def buy_asset(
    req: BuyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    asset = db.query(IPAsset).filter(IPAsset.id == req.token_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="IP asset not found.")
    if not asset.is_listed:
        raise HTTPException(status_code=400, detail="IP asset is not listed for sale.")
    if asset.creator_id == user.id:
        raise HTTPException(status_code=400, detail="Cannot buy your own asset.")
    if req.price_wei != (asset.price_wei or 0):
        raise HTTPException(status_code=400, detail="Price mismatch.")
    if not req.tx_hash:
        raise HTTPException(status_code=400, detail="Transaction hash is required.")

    existing_tx = db.query(Transaction).filter(Transaction.tx_hash == req.tx_hash).first()
    if existing_tx:
        raise HTTPException(status_code=409, detail="Transaction already recorded.")

    tx = Transaction(
        token_id=req.token_id,
        seller_id=asset.creator_id,
        buyer_id=user.id,
        price_wei=req.price_wei,
        tx_hash=req.tx_hash,
    )
    db.add(tx)

    asset.is_listed = False
    asset.creator_id = user.id

    db.commit()

    return {"message": "Purchase recorded.", "token_id": req.token_id, "tx_hash": req.tx_hash}


@router.get("/transactions", response_model=TransactionListResponse)
def get_transactions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    txs = (
        db.query(Transaction)
        .filter(
            (Transaction.seller_id == user.id) | (Transaction.buyer_id == user.id)
        )
        .order_by(desc(Transaction.timestamp))
        .all()
    )

    items = []
    for tx in txs:
        seller = db.query(User).filter(User.id == tx.seller_id).first()
        buyer = db.query(User).filter(User.id == tx.buyer_id).first()
        items.append(TransactionResponse(
            id=tx.id,
            token_id=tx.token_id,
            seller_wallet=seller.wallet_address if seller else "unknown",
            buyer_wallet=buyer.wallet_address if buyer else "unknown",
            price_wei=tx.price_wei,
            tx_hash=tx.tx_hash,
            timestamp=tx.timestamp.isoformat() if tx.timestamp else "",
        ))

    return TransactionListResponse(items=items, total=len(items))
