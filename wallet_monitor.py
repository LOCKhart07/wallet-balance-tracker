import json
import os
from typing import Dict

import dotenv
import requests
from web3 import Web3

dotenv.load_dotenv()


NATIVE_TOKEN_ADDRESS = "0x0000000000000000000000000000000000000000"
# --- Load RPC URLs ---

RPC_URLS: Dict = json.loads(os.getenv("RPC_URLS", "{}"))
WEB3_PROVIDERS = {
    chain: Web3(Web3.HTTPProvider(rpc_url)) for chain, rpc_url in RPC_URLS.items()
}

# --- Load wallets JSON ---
WALLETS_TO_MONITOR: Dict = json.load(open("wallets.json"))
# --- Minimal ERC20 ABI ---
ERC20_ABI = [
    {
        "constant": True,
        "inputs": [],
        "name": "symbol",
        "outputs": [{"name": "", "type": "string"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [],
        "name": "decimals",
        "outputs": [{"name": "", "type": "uint8"}],
        "type": "function",
    },
    {
        "constant": True,
        "inputs": [{"name": "_owner", "type": "address"}],
        "name": "balanceOf",
        "outputs": [{"name": "balance", "type": "uint256"}],
        "type": "function",
    },
]


SHOULD_NOTIFY = os.getenv("SHOULD_NOTIFY", "false").lower() == "true"
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_IDS = json.loads(os.getenv("TELEGRAM_CHAT_IDS", "[]"))


def send_telegram_message(message: str):
    """Send a message to all configured Telegram chat IDs."""
    if not SHOULD_NOTIFY or not TELEGRAM_TOKEN or not TELEGRAM_CHAT_IDS:
        print("Telegram notifications are disabled or not configured.")
        return

    for chat_id in TELEGRAM_CHAT_IDS:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown",  # or "HTML" or omit
            "disable_web_page_preview": True,  # optional
        }
        try:
            response = requests.post(url, data=payload, timeout=10)
            if response.status_code != 200:
                print(f"Failed to send Telegram message to {chat_id}: {response.text}")
        except Exception as e:
            print(f"Error sending Telegram message to {chat_id}: {e}")


def get_erc20_metadata(contract):
    """Fetch ERC20 symbol + decimals with fallbacks."""
    try:
        symbol = contract.functions.symbol().call()
    except Exception:
        symbol = "UNKNOWN"
    try:
        decimals = contract.functions.decimals().call()
    except Exception:
        decimals = 18
    return symbol, decimals


def get_balance(w3: Web3, wallet: str, token_info: dict):
    """Get native or ERC20 balance (always return in wei)."""
    wallet = Web3.to_checksum_address(wallet)
    token_addr = Web3.to_checksum_address(token_info["address"])

    # Native token
    if token_addr == Web3.to_checksum_address(NATIVE_TOKEN_ADDRESS):
        balance_wei = w3.eth.get_balance(wallet)
        return {"symbol": "NATIVE", "decimals": 18, "balance_wei": balance_wei}

    # ERC20 token
    contract = w3.eth.contract(address=token_addr, abi=ERC20_ABI)
    symbol, decimals = get_erc20_metadata(contract)
    balance_wei = contract.functions.balanceOf(wallet).call()

    return {"symbol": symbol, "decimals": decimals, "balance_wei": balance_wei}


def format_amount(wei_value, decimals):
    return wei_value / (10**decimals)


def run(give_request_format: bool = False, inform_regardless_of_balance: bool = False):
    # Check RPCs
    for chain, w3 in WEB3_PROVIDERS.items():
        print(f"{chain}: connected={w3.is_connected()}")

    for wallet_name, metadata in WALLETS_TO_MONITOR.items():
        print(f"💼 Wallet: {wallet_name}")
        chain = metadata["chain"]

        if chain not in WEB3_PROVIDERS:
            print(f"  ⚠️ No provider for chain: {chain}")
            continue

        w3 = WEB3_PROVIDERS[chain]
        wallet_address = metadata["address"]

        for token_name, token_info in metadata.get("tokens", {}).items():
            try:
                result = get_balance(w3, wallet_address, token_info)

                balance_eth = format_amount(result["balance_wei"], result["decimals"])
                threshold_eth = format_amount(
                    token_info.get("threshold", 0), result["decimals"]
                )
                topup_eth = format_amount(
                    token_info.get("topup", 0), result["decimals"]
                )

                needs_topup = result["balance_wei"] < token_info.get("threshold", 0)
                status = "🟢 OK"
                if needs_topup:
                    status = f"🔴 BELOW threshold → top up {topup_eth:.6f}"

                symbol_display = (
                    token_name if result["symbol"] == "NATIVE" else result["symbol"]
                )

                print(
                    f"  {symbol_display:>6}: {balance_eth:.6f} "
                    f"(threshold={threshold_eth:.6f}) {status}"
                )

                if (SHOULD_NOTIFY and needs_topup) or inform_regardless_of_balance:
                    message = (
                        "⚠️ *Top-up Alert*\n"
                        if needs_topup
                        else "ℹ️ *Wallet Status*\n"
                        f"• **Wallet:** `{wallet_name}`\n"
                        f"• **Address:** `{wallet_address}`\n"
                        f"• **Chain:** `{chain}`\n"
                        f"• **Token:** `{symbol_display}`\n"
                        f"• **Current Balance:** `{balance_eth:.6f}`\n"
                        f"• **Threshold:** `{threshold_eth:.6f}`\n"
                        f"• **Suggested Top-up:** `{topup_eth:.6f}`\n"
                    )

                    if give_request_format:
                        # Feature not implemented: placeholder for future request format
                        request_message = ""
                        message += request_message
                    send_telegram_message(message)

            except Exception as e:
                print(f"  ⚠️ Error reading {token_name}: {e}")

        print("")


if __name__ == "__main__":
    run()
