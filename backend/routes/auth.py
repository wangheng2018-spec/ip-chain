"""
Authentication routes – Web3 wallet signature-based login.
"""
import os
import secrets
import datetime
import logging
from fastapi import APIRouter, Depends, HTTPException, Header, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
from jose import jwt, JWTError

from database import get_db
from models import User
from blockchain.web3_helper import recover_signer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

SECRET_KEY = os.getenv("SECRET_KEY", "change-this-to-a-random-secret-key")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

# In-memory nonce store (wallet_address -> nonce)
_nonce_store: dict[str, str] = {}


# ── Pydantic schemas ─────────────────────────────────────────────────────────

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
    user: dict


# ── Helpers ──────────────────────────────────────────────────────────────────

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.datetime.utcnow() + datetime.timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def get_token_from_header(authorization: str = Header(...)) -> str:
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header",
        )
    return authorization[len("Bearer "):].strip()


def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(get_token_from_header),
) -> User:
    """Dependency – decode JWT and return the authenticated User."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        wallet: str | None = payload.get("wallet_address")
        if wallet is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = db.query(User).filter(User.wallet_address == wallet).first()
    if user is None:
        raise credentials_exception
    return user


# ── Routes ───────────────────────────────────────────────────────────────────

@router.post("/nonce", response_model=NonceResponse)
def get_nonce(req: NonceRequest):
    """Generate a nonce for the given wallet address to sign."""
    nonce = secrets.token_hex(16)
    _nonce_store[req.wallet_address.lower()] = nonce
    message = (
        f"Welcome to IP-Chain!\n\n"
        f"Sign this message to authenticate.\n\n"
        f"Nonce: {nonce}"
    )
    return NonceResponse(nonce=nonce, message=message)


@router.post("/verify", response_model=TokenResponse)
def verify_signature(req: VerifyRequest, db: Session = Depends(get_db)):
    """Verify the signed message and return a JWT."""
    wallet_lower = req.wallet_address.lower()
    stored_nonce = _nonce_store.pop(wallet_lower, None)
    if stored_nonce is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No nonce requested for this wallet. Call /api/auth/nonce first.",
        )

    expected_message = (
        f"Welcome to IP-Chain!\n\n"
        f"Sign this message to authenticate.\n\n"
        f"Nonce: {stored_nonce}"
    )
    signer = recover_signer(expected_message, req.signature)
    if signer is None or signer.lower() != wallet_lower:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Signature verification failed",
        )

    # Upsert user
    user = db.query(User).filter(User.wallet_address == wallet_lower).first()
    if user is None:
        user = User(wallet_address=wallet_lower)
        db.add(user)
        db.commit()
        db.refresh(user)

    access_token = create_access_token({"wallet_address": wallet_lower})
    return TokenResponse(access_token=access_token, user=user.to_dict())


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    """Return the authenticated user's profile."""
    return UserResponse(user=current_user.to_dict())
