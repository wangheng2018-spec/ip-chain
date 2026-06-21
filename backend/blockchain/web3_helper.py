"""
Web3 helper utilities for interacting with the IP-Chain smart contract.
"""
import os
import logging
from typing import Optional

from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from eth_account.messages import encode_defunct

logger = logging.getLogger(__name__)

RPC_URL = os.getenv("RPC_URL", "http://127.0.0.1:8545")
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS", "0x0000000000000000000000000000000000000000")
CHAIN_ID = int(os.getenv("CHAIN_ID", "1337"))

# ── Minimal IP-Chain contract ABI ──────────────────────────────────────────────
# This ABI covers the essential functions for minting, listing, buying, and
# verifying IP NFTs. Deploy your own contract with these function signatures
# and update the address.
CONTRACT_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "string", "name": "tokenURI", "type": "string"},
            {"internalType": "string", "name": "contentHash", "type": "string"},
        ],
        "name": "mintIP",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
        "name": "ownerOf",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "uint256", "name": "tokenId", "type": "uint256"}],
        "name": "tokenURI",
        "outputs": [{"internalType": "string", "name": "", "type": "string"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "totalSupply",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "string", "name": "contentHash", "type": "string"}],
        "name": "verifyContent",
        "outputs": [
            {"internalType": "bool", "name": "exists", "type": "bool"},
            {"internalType": "uint256", "name": "tokenId", "type": "uint256"},
            {"internalType": "address", "name": "owner", "type": "address"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]


def get_web3() -> Web3:
    """Return a Web3 instance connected to the configured RPC."""
    w3 = Web3(Web3.HTTPProvider(RPC_URL, request_kwargs={"timeout": 30}))
    # Inject POA middleware for networks like Polygon / BSC
    w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return w3


def get_contract(w3: Optional[Web3] = None):
    """Return a contract instance for the IP-Chain contract."""
    if w3 is None:
        w3 = get_web3()
    return w3.eth.contract(address=Web3.to_checksum_address(CONTRACT_ADDRESS), abi=CONTRACT_ABI)


def is_connected() -> bool:
    """Check whether the Web3 provider is reachable."""
    try:
        return get_web3().is_connected()
    except Exception as exc:
        logger.warning("Web3 connection check failed: %s", exc)
        return False


def recover_signer(message: str, signature: str) -> Optional[str]:
    """
    Recover the Ethereum address that signed *message* and produced *signature*.
    Returns the checksummed address, or None on failure.
    """
    try:
        w3 = get_web3()
        message_encoded = encode_defunct(text=message)
        address = w3.eth.account.recover_message(message_encoded, signature=signature)
        return Web3.to_checksum_address(address)
    except Exception as exc:
        logger.error("Signature recovery failed: %s", exc)
        return None


def verify_content(content_hash: str) -> Optional[dict]:
    """
    Call the smart contract's verifyContent function to check whether a
    content hash is registered on-chain.

    Returns a dict with keys ``exists`` (bool), ``token_id`` (int),
    ``owner`` (address str) if the contract is reachable, or None on failure.
    """
    try:
        contract = get_contract()
        exists, token_id, owner = contract.functions.verifyContent(content_hash).call()
        return {
            "exists": exists,
            "token_id": token_id,
            "owner": owner,
        }
    except Exception as exc:
        logger.error("verifyContent call failed for hash %s: %s", content_hash, exc)
        return None


def format_wei(wei: str) -> int:
    """Safely convert a wei string to int."""
    return int(wei)


def format_eth(wei: str) -> float:
    """Convert a wei string to ETH float."""
    return float(Web3.from_wei(int(wei), "ether"))
