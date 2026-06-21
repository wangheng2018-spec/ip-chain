"""
IPFS integration via Pinata (production) or local IPFS node (development).
"""
import os
import json
import logging
from typing import Optional

import requests

logger = logging.getLogger(__name__)

PINATA_API_URL = "https://api.pinata.cloud"
PINATA_GATEWAY = os.getenv("IPFS_GATEWAY", "https://gateway.pinata.cloud")
PINATA_API_KEY = os.getenv("PINATA_API_KEY", "")
PINATA_SECRET_KEY = os.getenv("PINATA_SECRET_API_KEY", "")
LOCAL_IPFS_URL = os.getenv("IPFS_API_URL", "")


def _pinata_headers() -> dict:
    return {
        "pinata_api_key": PINATA_API_KEY,
        "pinata_secret_api_key": PINATA_SECRET_KEY,
    }


def upload_file_to_ipfs(file_path: str, filename: Optional[str] = None) -> Optional[str]:
    """
    Upload a file to IPFS via Pinata.
    Returns the IPFS CID (content identifier) on success, or None on failure.
    """
    if PINATA_API_KEY and PINATA_SECRET_KEY:
        return _upload_via_pinata_file(file_path, filename)
    if LOCAL_IPFS_URL:
        return _upload_via_local(file_path)
    logger.warning("No IPFS backend configured (set PINATA_API_KEY or IPFS_API_URL)")
    return None


def upload_json_to_ipfs(data: dict) -> Optional[str]:
    """
    Upload a JSON metadata object to IPFS via Pinata.
    Returns the IPFS CID on success, or None on failure.
    """
    if PINATA_API_KEY and PINATA_SECRET_KEY:
        return _upload_via_pinata_json(data)
    if LOCAL_IPFS_URL:
        return _upload_via_local_json(data)
    logger.warning("No IPFS backend configured (set PINATA_API_KEY or IPFS_API_URL)")
    return None


def get_ipfs_url(cid: str) -> str:
    """Return an HTTP gateway URL for the given IPFS CID."""
    return f"{PINATA_GATEWAY}/ipfs/{cid}"


# ── Private helpers ──────────────────────────────────────────────────────────


def _upload_via_pinata_file(file_path: str, filename: Optional[str] = None) -> Optional[str]:
    url = f"{PINATA_API_URL}/pinning/pinFileToIPFS"
    with open(file_path, "rb") as f:
        files = {"file": (filename or os.path.basename(file_path), f)}
        try:
            resp = requests.post(url, files=files, headers=_pinata_headers(), timeout=120)
            resp.raise_for_status()
            cid = resp.json().get("IpfsHash")
            logger.info("File pinned to IPFS via Pinata: %s", cid)
            return cid
        except requests.RequestException as exc:
            logger.error("Pinata file upload failed: %s", exc)
            return None


def _upload_via_pinata_json(data: dict) -> Optional[str]:
    url = f"{PINATA_API_URL}/pinning/pinJSONToIPFS"
    try:
        resp = requests.post(url, json=data, headers=_pinata_headers(), timeout=30)
        resp.raise_for_status()
        cid = resp.json().get("IpfsHash")
        logger.info("JSON pinned to IPFS via Pinata: %s", cid)
        return cid
    except requests.RequestException as exc:
        logger.error("Pinata JSON upload failed: %s", exc)
        return None


def _upload_via_local(file_path: str) -> Optional[str]:
    url = f"{LOCAL_IPFS_URL}/api/v0/add"
    try:
        with open(file_path, "rb") as f:
            resp = requests.post(url, files={"file": f}, timeout=120)
            resp.raise_for_status()
            cid = resp.json().get("Hash")
            logger.info("File pinned to local IPFS: %s", cid)
            return cid
    except requests.RequestException as exc:
        logger.error("Local IPFS upload failed: %s", exc)
        return None


def _upload_via_local_json(data: dict) -> Optional[str]:
    url = f"{LOCAL_IPFS_URL}/api/v0/add"
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    try:
        resp = requests.post(url, files={"file": ("metadata.json", payload)}, timeout=30)
        resp.raise_for_status()
        cid = resp.json().get("Hash")
        logger.info("JSON pinned to local IPFS: %s", cid)
        return cid
    except requests.RequestException as exc:
        logger.error("Local IPFS JSON upload failed: %s", exc)
        return None
