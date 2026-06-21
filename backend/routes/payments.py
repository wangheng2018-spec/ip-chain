"""
Stripe fiat payment integration for IP-Chain.
Provides a fiat on-ramp so users can pay with credit card.
"""
import os
import logging
from typing import Optional

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import IPAsset, License, Transaction, TransactionType, User
from routes.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payments", tags=["payments"])

# ── Stripe config ──────────────────────────────────────────────────────────────

STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
DOMAIN = os.getenv("FRONTEND_URL", "http://localhost:3000")

stripe.api_key = STRIPE_SECRET_KEY

# Price oracle: how many USD per 1 ETH (used to convert wei prices to fiat)
# In production this should come from a price feed (e.g. Chainlink, CoinGecko API)
ETH_USD_RATE = float(os.getenv("ETH_USD_RATE", "3500"))


# ── Schemas ────────────────────────────────────────────────────────────────────

class CreateCheckoutRequest(BaseModel):
    asset_id: int


class CreateCheckoutResponse(BaseModel):
    session_url: str
    session_id: str


class CreateLicenseCheckoutRequest(BaseModel):
    license_id: int


class CreateLicenseCheckoutResponse(BaseModel):
    session_url: str
    session_id: str


# ── Helpers ────────────────────────────────────────────────────────────────────

def _wei_to_usd(wei_str: str) -> int:
    """Convert a wei amount string to the nearest USD cent for Stripe."""
    try:
        wei = int(wei_str)
        eth = wei / 1e18
        usd_cents = int(eth * ETH_USD_RATE * 100)
        return max(usd_cents, 50)  # minimum 50 cents
    except (ValueError, OverflowError):
        return 50  # fallback


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.post("/create-checkout", response_model=CreateCheckoutResponse)
def create_checkout_session(
    req: CreateCheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a Stripe Checkout Session for buying an IP asset with fiat.
    The session converts the asset's wei price to USD using the configured rate.
    """
    if not STRIPE_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Stripe is not configured (STRIPE_SECRET_KEY missing)",
        )

    asset = db.query(IPAsset).filter(IPAsset.id == req.asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="IP asset not found")
    if not asset.is_listed or not asset.price_wei:
        raise HTTPException(status_code=400, detail="IP asset is not listed for sale")
    if asset.creator_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot buy your own asset")

    unit_amount = _wei_to_usd(asset.price_wei)

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": asset.title,
                            "description": asset.description or "IP Asset",
                        },
                        "unit_amount": unit_amount,
                    },
                    "quantity": 1,
                }
            ],
            metadata={
                "type": "buy",
                "asset_id": str(asset.id),
                "token_id": str(asset.token_id or ""),
                "buyer_wallet": current_user.wallet_address,
                "seller_id": str(asset.creator_id),
                "price_wei": asset.price_wei,
            },
            success_url=f"{DOMAIN}/marketplace?payment=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{DOMAIN}/marketplace?payment=cancelled",
        )

        logger.info(
            "Stripe checkout created: session=%s asset_id=%d buyer=%s",
            session.id, asset.id, current_user.wallet_address,
        )
        return CreateCheckoutResponse(session_url=session.url, session_id=session.id)

    except stripe.error.StripeError as exc:
        logger.error("Stripe session creation failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Stripe error: {exc.user_message or str(exc)}")


@router.post("/create-checkout-license", response_model=CreateLicenseCheckoutResponse)
def create_license_checkout_session(
    req: CreateLicenseCheckoutRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a Stripe Checkout Session for purchasing a license with fiat.
    """
    if not STRIPE_SECRET_KEY:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Stripe is not configured (STRIPE_SECRET_KEY missing)",
        )

    lic = db.query(License).filter(License.id == req.license_id).first()
    if not lic:
        raise HTTPException(status_code=404, detail="License not found")
    if not lic.price_wei or lic.price_wei == "0":
        raise HTTPException(status_code=400, detail="This license is free; no payment required")

    unit_amount = _wei_to_usd(lic.price_wei)
    asset = db.query(IPAsset).filter(IPAsset.token_id == lic.token_id).first()

    try:
        session = stripe.checkout.Session.create(
            mode="payment",
            payment_method_types=["card"],
            line_items=[
                {
                    "price_data": {
                        "currency": "usd",
                        "product_data": {
                            "name": f"License - {asset.title if asset else 'IP Asset'}",
                            "description": f"{lic.license_type} license (token #{lic.token_id})",
                        },
                        "unit_amount": unit_amount,
                    },
                    "quantity": 1,
                }
            ],
            metadata={
                "type": "license",
                "license_id": str(lic.id),
                "token_id": str(lic.token_id),
                "license_type": lic.license_type,
                "buyer_wallet": current_user.wallet_address,
                "price_wei": lic.price_wei,
            },
            success_url=f"{DOMAIN}/licenses?payment=success&session_id={{CHECKOUT_SESSION_ID}}",
            cancel_url=f"{DOMAIN}/licenses?payment=cancelled",
        )

        logger.info(
            "Stripe license checkout created: session=%s license_id=%d buyer=%s",
            session.id, lic.id, current_user.wallet_address,
        )
        return CreateLicenseCheckoutResponse(session_url=session.url, session_id=session.id)

    except stripe.error.StripeError as exc:
        logger.error("Stripe license session creation failed: %s", exc)
        raise HTTPException(status_code=502, detail=f"Stripe error: {exc.user_message or str(exc)}")


@router.post("/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    """
    Stripe webhook endpoint.
    Handles ``checkout.session.completed`` events to record successful
    purchases and license acquisitions in the database.
    """
    if not STRIPE_WEBHOOK_SECRET:
        logger.warning("STRIPE_WEBHOOK_SECRET not set; webhook signature verification disabled")

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    # Verify signature if webhook secret is configured
    if STRIPE_WEBHOOK_SECRET:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
        except stripe.error.SignatureVerificationError as exc:
            logger.error("Stripe webhook signature verification failed: %s", exc)
            raise HTTPException(status_code=400, detail="Invalid signature")
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid payload")
    else:
        # Dev mode: parse without verification
        import json
        event = json.loads(payload)

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        metadata = session.get("metadata", {})
        tx_type = metadata.get("type", "buy")

        # Avoid duplicate processing
        existing = db.query(Transaction).filter(
            Transaction.tx_hash == session["id"]
        ).first()
        if existing:
            logger.info("Webhook: session %s already processed, skipping", session["id"])
            return {"status": "already_processed"}

        if tx_type == "buy":
            _handle_buy_completed(db, session)
        elif tx_type == "license":
            _handle_license_completed(db, session)
        else:
            logger.warning("Unknown webhook tx_type: %s", tx_type)

        logger.info("Stripe webhook processed: session=%s type=%s", session["id"], tx_type)
    else:
        logger.debug("Stripe webhook received unhandled event: %s", event["type"])

    return {"status": "ok"}


# ── Webhook helpers ────────────────────────────────────────────────────────────

def _handle_buy_completed(db: Session, session: dict):
    """Record a successful fiat purchase of an IP asset."""
    metadata = session.get("metadata", {})
    asset_id = int(metadata.get("asset_id", "0"))
    buyer_wallet = metadata.get("buyer_wallet", "")
    price_wei = metadata.get("price_wei", "0")
    token_id_str = metadata.get("token_id", "0")
    amount_paid = session.get("amount_total", 0)  # in cents

    asset = db.query(IPAsset).filter(IPAsset.id == asset_id).first()
    if not asset:
        logger.error("Webhook buy: asset %d not found", asset_id)
        return

    buyer = db.query(User).filter(User.wallet_address == buyer_wallet.lower()).first()
    if not buyer:
        logger.error("Webhook buy: buyer %s not found", buyer_wallet)
        return

    # Record the transaction
    tx = Transaction(
        token_id=int(token_id_str) or (asset.token_id or 0),
        seller_id=asset.creator_id,
        buyer_id=buyer.id,
        price_wei=price_wei,
        tx_hash=session["id"],
        tx_type=TransactionType.buy.value,
        fiat_amount=amount_paid / 100.0,
        fiat_currency="usd",
    )
    db.add(tx)

    # Transfer ownership and delist
    asset.creator_id = buyer.id
    asset.is_listed = False
    asset.price_wei = None
    db.commit()

    logger.info(
        "Fiat purchase completed: asset_id=%d buyer=%s amount_usd=%.2f",
        asset_id, buyer_wallet, amount_paid / 100.0,
    )


def _handle_license_completed(db: Session, session: dict):
    """Record a successful fiat license purchase."""
    metadata = session.get("metadata", {})
    license_id = int(metadata.get("license_id", "0"))
    buyer_wallet = metadata.get("buyer_wallet", "")
    price_wei = metadata.get("price_wei", "0")
    amount_paid = session.get("amount_total", 0)

    lic = db.query(License).filter(License.id == license_id).first()
    if not lic:
        logger.error("Webhook license: license %d not found", license_id)
        return

    buyer = db.query(User).filter(User.wallet_address == buyer_wallet.lower()).first()
    if not buyer:
        logger.error("Webhook license: buyer %s not found", buyer_wallet)
        return

    lic.licensee_address = buyer_wallet.lower()
    lic.active = True
    db.commit()

    logger.info(
        "Fiat license purchase completed: license_id=%d buyer=%s amount_usd=%.2f",
        license_id, buyer_wallet, amount_paid / 100.0,
    )
