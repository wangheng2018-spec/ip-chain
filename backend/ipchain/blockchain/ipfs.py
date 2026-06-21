import os
import json
import requests
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

PINATA_API_KEY = os.getenv("PINATA_API_KEY", "")
PINATA_SECRET_KEY = os.getenv("PINATA_SECRET_KEY", "")
PINATA_JWT = os.getenv("PINATA_JWT", "")
PINATA_GATEWAY = os.getenv("PINATA_GATEWAY", "https://gateway.pinata.cloud/ipfs/")
LOCAL_IPFS_URL = os.getenv("LOCAL_IPFS_URL", "http://127.0.0.1:5001")


def upload_file_to_ipfs(file_bytes: bytes, filename: str) -> Optional[str]:
    """Upload raw file bytes to IPFS via Pinata. Returns CID string or None."""
    if PINATA_JWT:
        return _upload_via_pinata_jwt(file_bytes, filename)
    elif PINATA_API_KEY and PINATA_SECRET_KEY:
        return _upload_via_pinata_key(file_bytes, filename)
    else:
        return _upload_via_local(file_bytes)


def _upload_via_pinata_jwt(file_bytes: bytes, filename: str) -> Optional[str]:
    url = "https://api.pinata.cloud/pinning/pinFileToIPFS"
    headers = {"Authorization": f"Bearer {PINATA_JWT}"}
    files = {"file": (filename, file_bytes)}
    try:
        resp = requests.post(url, headers=headers, files=files, timeout=120)
        resp.raise_for_status()
        return resp.json().get("IpfsHash")
    except requests.RequestException as e:
        raise RuntimeError(f"Pinata JWT upload failed: {e}")


def _upload_via_pinata_key(file_bytes: bytes, filename: str) -> Optional[str]:
    url = "https://api.pinata.cloud/pinning/pinFileToIPFS"
    headers = {
        "pinata_api_key": PINATA_API_KEY,
        "pinata_secret_api_key": PINATA_SECRET_KEY,
    }
    files = {"file": (filename, file_bytes)}
    try:
        resp = requests.post(url, headers=headers, files=files, timeout=120)
        resp.raise_for_status()
        return resp.json().get("IpfsHash")
    except requests.RequestException as e:
        raise RuntimeError(f"Pinata key upload failed: {e}")


def _upload_via_local(file_bytes: bytes) -> Optional[str]:
    url = f"{LOCAL_IPFS_URL}/api/v0/add"
    try:
        resp = requests.post(url, files={"file": ("file", file_bytes)}, timeout=120)
        resp.raise_for_status()
        return resp.json().get("Hash")
    except requests.RequestException as e:
        raise RuntimeError(f"Local IPFS upload failed: {e}")


def upload_json_to_ipfs(metadata: dict) -> Optional[str]:
    """Upload JSON metadata to IPFS. Returns CID string or None."""
    data = json.dumps(metadata, ensure_ascii=False).encode("utf-8")
    if PINATA_JWT:
        return _upload_json_via_pinata_jwt(data)
    elif PINATA_API_KEY and PINATA_SECRET_KEY:
        return _upload_json_via_pinata_key(data)
    else:
        return _upload_json_via_local(data)


def _upload_json_via_pinata_jwt(data: bytes) -> Optional[str]:
    url = "https://api.pinata.cloud/pinning/pinJSONToIPFS"
    headers = {
        "Authorization": f"Bearer {PINATA_JWT}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(url, headers=headers, data=data, timeout=120)
        resp.raise_for_status()
        return resp.json().get("IpfsHash")
    except requests.RequestException as e:
        raise RuntimeError(f"Pinata JWT JSON upload failed: {e}")


def _upload_json_via_pinata_key(data: bytes) -> Optional[str]:
    url = "https://api.pinata.cloud/pinning/pinJSONToIPFS"
    headers = {
        "pinata_api_key": PINATA_API_KEY,
        "pinata_secret_api_key": PINATA_SECRET_KEY,
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(url, headers=headers, data=data, timeout=120)
        resp.raise_for_status()
        return resp.json().get("IpfsHash")
    except requests.RequestException as e:
        raise RuntimeError(f"Pinata key JSON upload failed: {e}")


def _upload_json_via_local(data: bytes) -> Optional[str]:
    url = f"{LOCAL_IPFS_URL}/api/v0/add"
    try:
        resp = requests.post(url, files={"file": ("metadata.json", data)}, timeout=120)
        resp.raise_for_status()
        return resp.json().get("Hash")
    except requests.RequestException as e:
        raise RuntimeError(f"Local IPFS JSON upload failed: {e}")


def ipfs_gateway_url(cid: str) -> str:
    return f"{PINATA_GATEWAY}{cid}"
