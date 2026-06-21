"""
Marketplace routes – listing, buying, and transaction history.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import IPAsset, Transaction, User
from routes.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/market", tags=["marketplace"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class ListingResponse(BaseModel):
    listings: list[dict]
    total: int
    page: int
    page_size: int


class ListForSaleRequest(BaseModel):
    asset_id: int
    price_wei: str  # price in wei as a decimal string to avoid overflow


class ListForSaleResponse(BaseModel):
    ip_asset: dict


class BuyRequest(BaseModel):
    asset_id: int
    tx_hash: str
    price_wei: str


class BuyResponse(BaseModel):
    transaction: dict


class TransactionListResponse(BaseModel):
    transactions: list[dict]
    total: int
    page: int
    page_size: int


# ── Routes ───────────────────────────────────────────────────────────────────

@router.get("/listings", response_model=ListingResponse)
def get_listings(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    """Get paginated list of all IP assets currently listed for sale."""
    query = db.query(IPAsset).filter(IPAsset.is_listed == True)  # noqa: E712

    if category:
        query = query.filter(IPAsset.category == category)

    total = query.count()
    assets = (
        query.order_by(IPAsset.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return ListingResponse(
        listings=[a.to_dict() for a in assets],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/list", response_model=ListForSaleResponse)
def list_for_sale(
    req: ListForSaleRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List an IP asset for sale on the marketplace."""
    asset = db.query(IPAsset).filter(IPAsset.id == req.asset_id).first()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="IP asset not found")
    if asset.creator_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not own this IP asset",
        )

    wei_int = int(req.price_wei)
    if wei_int <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Price must be greater than 0",
        )

    asset.is_listed = True
    asset.price_wei = str(wei_int)
    db.commit()
    db.refresh(asset)

    logger.info("IP asset listed: id=%d price_wei=%s", asset.id, asset.price_wei)
    return ListForSaleResponse(ip_asset=asset.to_dict())


@router.post("/buy", response_model=BuyResponse)
def buy_asset(
    req: BuyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Record a purchase transaction for a listed IP asset."""
    asset = db.query(IPAsset).filter(IPAsset.id == req.asset_id).first()
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="IP asset not found")
    if not asset.is_listed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="IP asset is not listed for sale")
    if asset.creator_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="You cannot buy your own asset")

    # Verify price matches
    if asset.price_wei != req.price_wei:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Price mismatch: expected {asset.price_wei} wei",
        )

    # Check tx_hash uniqueness
    existing = db.query(Transaction).filter(Transaction.tx_hash == req.tx_hash).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Transaction hash already recorded",
        )

    # Create the transaction record
    tx = Transaction(
        token_id=asset.token_id or 0,
        seller_id=asset.creator_id,
        buyer_id=current_user.id,
        price_wei=req.price_wei,
        tx_hash=req.tx_hash,
    )
    db.add(tx)

    # Delist the asset and transfer ownership
    asset.creator_id = current_user.id
    asset.is_listed = False
    asset.price_wei = None

    db.commit()
    db.refresh(tx)

    logger.info("Asset purchased: asset_id=%d buyer_id=%d tx=%s", req.asset_id, current_user.id, req.tx_hash)
    return BuyResponse(transaction=tx.to_dict())


@router.get("/transactions", response_model=TransactionListResponse)
def get_transactions(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Get paginated transaction history."""
    query = db.query(Transaction).order_by(Transaction.timestamp.desc())
    total = query.count()
    txs = (
        query.offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return TransactionListResponse(
        transactions=[t.to_dict() for t in txs],
        total=total,
        page=page,
        page_size=page_size,
    )
