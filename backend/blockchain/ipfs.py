"""IPFS integration: Pinata / Web3.Storage / Local IPFS / Local fallback"""
import os, json, logging, shutil
from typing import Optional
import requests

logger = logging.getLogger(__name__)

PINATA_API_URL = "https://api.pinata.cloud"
PINATA_GATEWAY = os.getenv("IPFS_GATEWAY", "https://gateway.pinata.cloud")
PINATA_API_KEY = os.getenv("PINATA_API_KEY", "")
PINATA_SECRET_KEY = os.getenv("PINATA_SECRET_API_KEY", "")
LOCAL_IPFS_URL = os.getenv("IPFS_API_URL", "")
WEB3STORAGE_TOKEN = os.getenv("WEB3STORAGE_TOKEN", "")
LOCAL_STORAGE_PATH = os.getenv("LOCAL_STORAGE_PATH", "")

def _pinata_headers():
    return {"pinata_api_key": PINATA_API_KEY, "pinata_secret_api_key": PINATA_SECRET_KEY}

def _upload_via_pinata_file(file_path, filename=None):
    fn = filename or os.path.basename(file_path)
    with open(file_path, "rb") as f:
        resp = requests.post(PINATA_API_URL + "/pinning/pinFileToIPFS", headers=_pinata_headers(), files={"file": (fn, f)}, timeout=120)
    if resp.status_code == 200:
        cid = resp.json().get("IpfsHash", "")
        logger.info("Pinata OK: %s", cid)
        return cid
    logger.error("Pinata error: %s", resp.text[:200])
    return None

def _upload_via_pinata_json(data):
    payload = {"pinataContent": data, "pinataMetadata": {"name": "metadata.json"}}
    resp = requests.post(PINATA_API_URL + "/pinning/pinJSONToIPFS", headers=_pinata_headers(), json=payload, timeout=60)
    if resp.status_code == 200:
        cid = resp.json().get("IpfsHash", "")
        logger.info("Pinata JSON OK: %s", cid)
        return cid
    logger.error("Pinata JSON error: %s", resp.text[:200])
    return None

def _upload_via_web3storage(file_path, filename=None):
    if not WEB3STORAGE_TOKEN:
        return None
    fn = filename or os.path.basename(file_path)
    with open(file_path, "rb") as f:
        resp = requests.post("https://api.web3.storage/upload", headers={"Authorization": "Bearer " + WEB3STORAGE_TOKEN}, files={"file": (fn, f)}, timeout=120)
    if resp.status_code == 200:
        cid = resp.json().get("cid", "")
        logger.info("Web3.Storage OK: %s", cid)
        return cid
    logger.error("Web3.Storage error: %s", resp.text[:200])
    return None

def _upload_via_local(file_path):
    import subprocess
    try:
        result = subprocess.run(["ipfs", "add", "-q", file_path], capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            cid = result.stdout.strip()
            logger.info("Local IPFS OK: %s", cid)
            return cid
        logger.error("Local IPFS error: %s", result.stderr[:200])
    except Exception as e:
        logger.error("Local IPFS: %s", e)
    return None

def _upload_local_fallback(file_path, filename=None):
    store = LOCAL_STORAGE_PATH or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")
    os.makedirs(store, exist_ok=True)
    dest = os.path.join(store, filename or os.path.basename(file_path))
    shutil.copy2(file_path, dest)
    cid = "local:" + (filename or os.path.basename(file_path))
    logger.info("Local storage: %s", dest)
    return cid

def upload_file_to_ipfs(file_path, filename=None):
    if PINATA_API_KEY and PINATA_SECRET_KEY:
        cid = _upload_via_pinata_file(file_path, filename)
        if cid: return cid
    if WEB3STORAGE_TOKEN:
        cid = _upload_via_web3storage(file_path, filename)
        if cid: return cid
    if LOCAL_IPFS_URL:
        cid = _upload_via_local(file_path)
        if cid: return cid
    return _upload_local_fallback(file_path, filename)

def upload_json_to_ipfs(data):
    if PINATA_API_KEY and PINATA_SECRET_KEY:
        cid = _upload_via_pinata_json(data)
        if cid: return cid
    import tempfile
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(data, tmp, ensure_ascii=False)
    tmp_path = tmp.name
    tmp.close()
    cid = upload_file_to_ipfs(tmp_path, "metadata.json")
    os.unlink(tmp_path)
    return cid