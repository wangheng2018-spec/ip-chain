"""
License management routes for IP-Chain.
"""
import datetime
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import IPAsset, License, User
from routes.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/licenses", tags=["licenses"])


# ── License templates ──────────────────────────────────────────────────────────

LICENSE_TEMPLATES = [
    {
        "id": "standard",
        "name": "Standard License",
        "description": "Basic personal-use license. Allows the licensee to use the IP asset for non-commercial personal projects.",
        "max_uses": 1,
        "duration_days": None,  # perpetual
        "price_wei": "10000000000000000",  # 0.01 ETH
    },
    {
        "id": "commercial",
        "name": "Commercial License",
        "description": "Permits commercial use including incorporation into products, marketing materials, and client projects.",
        "max_uses": None,  # unlimited
        "duration_days": 365,
        "price_wei": "50000000000000000",  # 0.05 ETH
    },
    {
        "id": "exclusive",
        "name": "Exclusive License",
        "description": "Grants exclusive commercial rights. No other party may use the IP asset during the license term.",
        "max_uses": None,
        "duration_days": 365,
        "price_wei": "500000000000000000",  # 0.5 ETH
    },
    {
        "id": "educational",
        "name": "Educational License",
        "description": "Free license for educational institutions and non-profit research. Must provide attribution.",
        "max_uses": None,
        "duration_days": None,
        "price_wei": "0",
    },
]


# ── Schemas ────────────────────────────────────────────────────────────────────

class LicenseTemplatesResponse(BaseModel):
    templates: list[dict]


class CreateLicenseRequest(BaseModel):
    token_id: int
    licensee_address: str
    license_type: str
    expires_at: Optional[str] = None  # ISO datetime string
    max_uses: Optional[int] = None
    price_wei: Optional[str] = None


class CreateLicenseResponse(BaseModel):
    license: dict


class UseLicenseRequest(BaseModel):
    license_id: int


class UseLicenseResponse(BaseModel):
    license: dict


class LicenseListResponse(BaseModel):
    licenses: list[dict]
    total: int


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/templates", response_model=LicenseTemplatesResponse)
def get_license_templates():
    """Get available license template definitions."""
    return LicenseTemplatesResponse(templates=LICENSE_TEMPLATES)


@router.post("/create", response_model=CreateLicenseResponse, status_code=status.HTTP_201_CREATED)
def create_license(
    req: CreateLicenseRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Create a license for an IP asset.
    Only the asset owner can issue licenses.
    """
    # Verify the asset exists and the caller is the owner
    asset = db.query(IPAsset).filter(IPAsset.token_id == req.token_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="IP asset not found")
    if asset.creator_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the asset owner can create licenses",
        )

    # Resolve license template defaults
    template = next((t for t in LICENSE_TEMPLATES if t["id"] == req.license_type), None)
    price = req.price_wei or (template["price_wei"] if template else None)
    max_uses = req.max_uses if req.max_uses is not None else (template["max_uses"] if template else None)
    expires_at = None
    if req.expires_at:
        expires_at = datetime.datetime.fromisoformat(req.expires_at)
    elif template and template.get("duration_days"):
        expires_at = datetime.datetime.utcnow() + datetime.timedelta(days=template["duration_days"])

    lic = License(
        token_id=req.token_id,
        licensee_address=req.licensee_address.lower(),
        license_type=req.license_type,
        expires_at=expires_at,
        max_uses=max_uses,
        used_count=0,
        price_wei=price,
        active=True,
    )
    db.add(lic)
    db.commit()
    db.refresh(lic)

    logger.info(
        "License created: id=%d token_id=%d type=%s licensee=%s",
        lic.id, lic.token_id, lic.license_type, lic.licensee_address,
    )
    return CreateLicenseResponse(license=lic.to_dict())


@router.post("/use", response_model=UseLicenseResponse)
def use_license(
    req: UseLicenseRequest,
    db: Session = Depends(get_db),
):
    """
    Record a use of an existing license. Increments the used_count.
    """
    lic = db.query(License).filter(License.id == req.license_id).first()
    if not lic:
        raise HTTPException(status_code=404, detail="License not found")
    if not lic.active:
        raise HTTPException(status_code=400, detail="License is deactivated")

    # Check expiration
    if lic.expires_at and datetime.datetime.utcnow() > lic.expires_at:
        lic.active = False
        db.commit()
        raise HTTPException(status_code=400, detail="License has expired")

    # Check max_uses cap
    if lic.max_uses is not None and lic.used_count >= lic.max_uses:
        raise HTTPException(
            status_code=400,
            detail=f"License usage limit reached ({lic.used_count}/{lic.max_uses})",
        )

    lic.used_count += 1
    db.commit()
    db.refresh(lic)

    logger.info("License used: id=%d used_count=%d", lic.id, lic.used_count)
    return UseLicenseResponse(license=lic.to_dict())


@router.get("/{token_id}", response_model=LicenseListResponse)
def get_licenses_for_asset(
    token_id: int,
    db: Session = Depends(get_db),
):
    """Get all licenses issued for a specific IP asset (by token_id)."""
    licenses = (
        db.query(License)
        .filter(License.token_id == token_id)
        .order_by(License.created_at.desc())
        .all()
    )
    return LicenseListResponse(
        licenses=[l.to_dict() for l in licenses],
        total=len(licenses),
    )
