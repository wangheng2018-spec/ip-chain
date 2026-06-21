import os
import json
from typing import Optional, Any
from dotenv import load_dotenv
from web3 import Web3
from web3.middleware import ExtraDataToPOAMiddleware
from web3.types import TxParams, Wei

load_dotenv()

RPC_URL = os.getenv("RPC_URL", "http://127.0.0.1:7545")
CHAIN_ID = int(os.getenv("CHAIN_ID", "1337"))
CONTRACT_ADDRESS = os.getenv("CONTRACT_ADDRESS", "")
CONTRACT_ABI_PATH = os.getenv("CONTRACT_ABI_PATH", "")

_contract = None
_w3: Optional[Web3] = None


def get_web3() -> Web3:
    global _w3
    if _w3 is None:
        _w3 = Web3(Web3.HTTPProvider(RPC_URL))
        if _w3.eth.chain_id == 137 or _w3.eth.chain_id == 80001:
            _w3.middleware_onion.inject(ExtraDataToPOAMiddleware, layer=0)
    return _w3


def get_contract_abi() -> list:
    if CONTRACT_ABI_PATH and os.path.exists(CONTRACT_ABI_PATH):
        with open(CONTRACT_ABI_PATH, "r") as f:
            artifact = json.load(f)
            if isinstance(artifact, dict) and "abi" in artifact:
                return artifact["abi"]
            elif isinstance(artifact, list):
                return artifact
    return []


def get_contract():
    global _contract
    if _contract is None:
        w3 = get_web3()
        if not CONTRACT_ADDRESS:
            raise RuntimeError("CONTRACT_ADDRESS is not configured")
        abi = get_contract_abi()
        if not abi:
            raise RuntimeError("Contract ABI is empty or not found")
        _contract = w3.eth.contract(address=Web3.to_checksum_address(CONTRACT_ADDRESS), abi=abi)
    return _contract


def mint_ip(wallet_private_key: str, token_uri: str, content_hash: str) -> Optional[str]:
    """Mint a new IP token on-chain. Returns tx hash."""
    w3 = get_web3()
    contract = get_contract()
    account = w3.eth.account.from_key(wallet_private_key)
    nonce = w3.eth.get_transaction_count(account.address)

    tx: TxParams = contract.functions.safeMint(account.address, token_uri, content_hash).build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": 300000,
        "gasPrice": w3.eth.gas_price,
        "chainId": CHAIN_ID,
    })
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    return receipt.transactionHash.hex()


def list_for_sale(wallet_private_key: str, token_id: int, price_wei: int) -> Optional[str]:
    """List an IP token for sale."""
    w3 = get_web3()
    contract = get_contract()
    account = w3.eth.account.from_key(wallet_private_key)
    nonce = w3.eth.get_transaction_count(account.address)

    tx: TxParams = contract.functions.listForSale(token_id, price_wei).build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": 200000,
        "gasPrice": w3.eth.gas_price,
        "chainId": CHAIN_ID,
    })
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    return receipt.transactionHash.hex()


def buy_ip(wallet_private_key: str, token_id: int, price_wei: int) -> Optional[str]:
    """Purchase a listed IP token. Returns tx hash."""
    w3 = get_web3()
    contract = get_contract()
    account = w3.eth.account.from_key(wallet_private_key)
    nonce = w3.eth.get_transaction_count(account.address)

    tx: TxParams = contract.functions.buy(token_id).build_transaction({
        "from": account.address,
        "nonce": nonce,
        "gas": 200000,
        "gasPrice": w3.eth.gas_price,
        "chainId": CHAIN_ID,
        "value": Wei(price_wei),
    })
    signed = account.sign_transaction(tx)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    return receipt.transactionHash.hex()


def get_onchain_ip_metadata(token_id: int) -> dict[str, Any]:
    """Fetch IP metadata stored on-chain for a given token."""
    contract = get_contract()
    uri = contract.functions.tokenURI(token_id).call()
    return {"tokenURI": uri}


def parse_registration_event(tx_hash: str) -> Optional[dict[str, Any]]:
    """Parse IPRegistered events from a transaction receipt."""
    w3 = get_web3()
    contract = get_contract()
    receipt = w3.eth.get_transaction_receipt(tx_hash)
    logs = contract.events.IPRegistered().process_receipt(receipt)
    if logs:
        args = logs[0]["args"]
        return {
            "tokenId": args.get("tokenId"),
            "creator": args.get("creator"),
            "contentHash": args.get("contentHash"),
        }
    return None


def parse_sale_event(tx_hash: str) -> Optional[dict[str, Any]]:
    """Parse IPSold events from a transaction receipt."""
    w3 = get_web3()
    contract = get_contract()
    receipt = w3.eth.get_transaction_receipt(tx_hash)
    logs = contract.events.IPSold().process_receipt(receipt)
    if logs:
        args = logs[0]["args"]
        return {
            "tokenId": args.get("tokenId"),
            "seller": args.get("seller"),
            "buyer": args.get("buyer"),
            "price": args.get("price"),
        }
    return None
