import datetime
import enum
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, BigInteger,
    DateTime, ForeignKey, Float,
)
from sqlalchemy.orm import relationship
from database import Base


class TransactionType(str, enum.Enum):
    buy = "buy"
    license = "license"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    wallet_address = Column(String(42), unique=True, nullable=False, index=True)
    username = Column(String(100), nullable=True)
    email = Column(String(255), nullable=True)
    bio = Column(Text, nullable=True)
    avatar_url = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    ip_assets = relationship("IPAsset", back_populates="creator", lazy="selectin")
    sales = relationship(
        "Transaction",
        foreign_keys="Transaction.seller_id",
        back_populates="seller",
        lazy="selectin",
    )
    purchases = relationship(
        "Transaction",
        foreign_keys="Transaction.buyer_id",
        back_populates="buyer",
        lazy="selectin",
    )

    def to_dict(self):
        return {
            "id": self.id,
            "wallet_address": self.wallet_address,
            "username": self.username,
            "email": self.email,
            "bio": self.bio,
            "avatar_url": self.avatar_url,
            "created_at": self.created_at.isoformat(),
        }


class IPAsset(Base):
    __tablename__ = "ip_assets"

    id = Column(Integer, primary_key=True, index=True)
    token_id = Column(Integer, unique=True, nullable=True, index=True)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(100), nullable=True, index=True)
    content_hash = Column(String(64), nullable=False)  # SHA-256 hex digest
    ipfs_cid = Column(String(255), nullable=True)
    file_url = Column(String(500), nullable=True)
    thumbnail_url = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    is_listed = Column(Boolean, default=False, nullable=False)
    price_wei = Column(String(78), nullable=True)  # store as string to avoid overflow
    blockchain_tx_hash = Column(String(66), nullable=True)

    creator = relationship("User", back_populates="ip_assets", lazy="selectin")

    def to_dict(self):
        return {
            "id": self.id,
            "token_id": self.token_id,
            "creator_id": self.creator_id,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "content_hash": self.content_hash,
            "ipfs_cid": self.ipfs_cid,
            "file_url": self.file_url,
            "thumbnail_url": self.thumbnail_url,
            "created_at": self.created_at.isoformat(),
            "is_listed": self.is_listed,
            "price_wei": self.price_wei,
            "blockchain_tx_hash": self.blockchain_tx_hash,
            "creator": self.creator.to_dict() if self.creator else None,
        }


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    token_id = Column(Integer, nullable=False, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    buyer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    price_wei = Column(String(78), nullable=False)
    tx_hash = Column(String(66), nullable=False, unique=True)
    tx_type = Column(String(20), nullable=True, default=TransactionType.buy.value)
    fiat_amount = Column(Float, nullable=True)
    fiat_currency = Column(String(10), nullable=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    seller = relationship("User", foreign_keys=[seller_id], back_populates="sales", lazy="selectin")
    buyer = relationship("User", foreign_keys=[buyer_id], back_populates="purchases", lazy="selectin")

    def to_dict(self):
        return {
            "id": self.id,
            "token_id": self.token_id,
            "seller_id": self.seller_id,
            "buyer_id": self.buyer_id,
            "price_wei": self.price_wei,
            "tx_hash": self.tx_hash,
            "tx_type": self.tx_type,
            "fiat_amount": self.fiat_amount,
            "fiat_currency": self.fiat_currency,
            "timestamp": self.timestamp.isoformat(),
            "seller": self.seller.to_dict() if self.seller else None,
            "buyer": self.buyer.to_dict() if self.buyer else None,
        }


class License(Base):
    __tablename__ = "licenses"

    id = Column(Integer, primary_key=True, index=True)
    token_id = Column(Integer, ForeignKey("ip_assets.token_id"), nullable=False, index=True)
    licensee_address = Column(String(42), nullable=False)
    license_type = Column(String(50), nullable=False)
    expires_at = Column(DateTime, nullable=True)
    max_uses = Column(Integer, nullable=True)
    used_count = Column(Integer, default=0, nullable=False)
    price_wei = Column(String(78), nullable=True)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "token_id": self.token_id,
            "licensee_address": self.licensee_address,
            "license_type": self.license_type,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "max_uses": self.max_uses,
            "used_count": self.used_count,
            "price_wei": self.price_wei,
            "active": self.active,
            "created_at": self.created_at.isoformat(),
        }
