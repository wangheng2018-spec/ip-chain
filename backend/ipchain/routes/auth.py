import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer
from pydantic import BaseModel
from sqlalchemy.orm import Session
from eth_account.messages import encode_defunct

from ipchain.database import get_db
from ipchain.models import User

router = APIRouter(prefix="/api/auth", tags=["auth"])

SECRET_KEY = os.getenv("JWT_SECRET_KEY", secrets.token_hex(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "1440"))

_nonce_store: dict[str, dict] = {}


class NonceRequest(BaseModel):
    wallet_address: str


class NonceResponse(BaseModel):
    nonce: str
    message: str


class VerifyRequest(BaseModel):
    wallet_address: str
    signature: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


class UserResponse(BaseModel):
    id: int
    wallet_address: str
    username: Optional[str]
    email: Optional[str]
    bio: Optional[str]
    avatar_url: Optional[str]
    created_at: str


def _build_login_message(wallet_address: str, nonce: str) -> str:
    return (
        f"Welcome to IP-Chain!\n\n"
        f"Sign this message to authenticate with your wallet.\n"
        f"This request will not trigger any blockchain transaction.\n\n"
        f"Wallet address:\n{wallet_address}\n\n"
        f"Nonce: {nonce}"
    )


@router.post("/nonce", response_model=NonceResponse)
def get_nonce(req: NonceRequest):
    addr = req.wallet_address.lower()
    nonce = secrets.token_hex(16)
    _nonce_store[addr] = {
        "nonce": nonce,
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    message = _build_login_message(req.wallet_address, nonce)
    return NonceResponse(nonce=nonce, message=message)


@router.post("/verify", response_model=TokenResponse)
def verify_signature(req: VerifyRequest, db: Session = Depends(get_db)):
    addr = req.wallet_address.lower()
    stored = _nonce_store.get(addr)
    if not stored:
        raise HTTPException(status_code=400, detail="No nonce requested. Call /nonce first.")
    if datetime.now(timezone.utc) > stored["expires_at"]:
        del _nonce_store[addr]
        raise HTTPException(status_code=400, detail="Nonce expired. Request a new one.")

    message = _build_login_message(req.wallet_address, stored["nonce"])
    try:
        message_encoded = encode_defunct(text=message)
        from web3 import Web3
        recovered = Web3().eth.account.recover_message(message_encoded, signature=req.signature)
        if recovered.lower() != addr:
            raise HTTPException(status_code=401, detail="Signature mismatch.")
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Signature verification failed: {{e}}")

    del _nonce_store[addr]

    user = db.query(User).filter(User.wallet_address == addr).first()
    if not user:
        user = User(wallet_address=addr)
        db.add(user)
        db.commit()
        db.refresh(user)

    payload = {
        "sub": str(user.id),
        "wallet_address": user.wallet_address,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    access_token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    return TokenResponse(
        access_token=access_token,
        user={
            "id": user.id,
            "wallet_address": user.wallet_address,
            "username": user.username,
            "email": user.email,
            "bio": user.bio or "",
            "avatar_url": user.avatar_url or "",
            "created_at": user.created_at.isoformat() if user.created_at else "",
        },
    )


def get_current_user_token(token: str = Depends(HTTPBearer(auto_error=False))) -> str:
    if token is None:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    token_str = token.credentials if hasattr(token, "credentials") else str(token)
    try:
        payload = jwt.decode(token_str, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token.")


def get_current_user(
    payload: dict = Depends(get_current_user_token),
    db: Session = Depends(get_db),
) -> User:
    user_id = int(payload.get("sub", 0))
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")
    return user


@router.get("/me", response_model=UserResponse)
def get_me(user: User = Depends(get_current_user)):
    return UserResponse(
        id=user.id,
        wallet_address=user.wallet_address,
        username=user.username,
        email=user.email,
        bio=user.bio or "",
        avatar_url=user.avatar_url or "",
        created_at=user.created_at.isoformat() if user.created_at else "",
    )
