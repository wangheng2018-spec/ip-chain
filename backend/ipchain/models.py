from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, Text, Boolean, BigInteger, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from ipchain.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    wallet_address = Column(String(42), unique=True, index=True, nullable=False)
    username = Column(String(64), unique=True, nullable=True)
    email = Column(String(128), unique=True, nullable=True)
    bio = Column(Text, nullable=True, default="")
    avatar_url = Column(String(512), nullable=True, default="")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    ip_assets = relationship("IPAsset", back_populates="creator", foreign_keys="IPAsset.creator_id")
    sales = relationship("Transaction", back_populates="seller", foreign_keys="Transaction.seller_id")
    purchases = relationship("Transaction", back_populates="buyer", foreign_keys="Transaction.buyer_id")


class IPAsset(Base):
    __tablename__ = "ip_assets"

    id = Column(Integer, primary_key=True, index=True)
    token_id = Column(Integer, unique=True, nullable=True, index=True)
    creator_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(256), nullable=False)
    description = Column(Text, nullable=True, default="")
    category = Column(String(64), nullable=True, default="other")
    content_hash = Column(String(64), nullable=False)
    ipfs_cid = Column(String(128), nullable=True)
    file_url = Column(String(512), nullable=True)
    thumbnail_url = Column(String(512), nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    is_listed = Column(Boolean, default=False)
    price_wei = Column(BigInteger, nullable=True, default=0)
    blockchain_tx_hash = Column(String(128), nullable=True)

    creator = relationship("User", back_populates="ip_assets", foreign_keys=[creator_id])


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    token_id = Column(Integer, ForeignKey("ip_assets.token_id"), nullable=False, index=True)
    seller_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    buyer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    price_wei = Column(BigInteger, nullable=False)
    tx_hash = Column(String(128), nullable=False, unique=True)
    timestamp = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    ip_asset = relationship("IPAsset", foreign_keys=[token_id])
    seller = relationship("User", back_populates="sales", foreign_keys=[seller_id])
    buyer = relationship("User", back_populates="purchases", foreign_keys=[buyer_id])
