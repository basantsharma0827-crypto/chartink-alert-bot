import os
import re
import json
import time
import logging
from typing import List, Set

import requests
from bs4 import BeautifulSoup

SCREENER_URL = os.getenv("SCREENER_URL", "https://chartink.com/screener/copy-morning-scanner-for-buy-nr7-based-breakout-8")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "60"))
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
STATE_FILE = os.getenv("STATE_FILE", "seen_state.json")
REQUEST_TIMEOUT = int(os.getenv("REQUEST_TIMEOUT", "30"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Referer": SCREENER_URL,
})

def load_seen() -> Set[str]:
    if not os.path.exists(STATE_FILE):
        return set()
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("symbols", []))
    except Exception:
        return set()

def save_seen(symbols: Set[str]) -> None:
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"symbols": sorted(symbols)}, f, ensure_ascii=False, indent=2)

def extract_symbols_from_html(html: str) -> List[str]:
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text("\n", strip=True)
    candidates = set(re.findall(r"\b[A-Z][A-Z0-9&.-]{1,14}\b", text))

    ignore = {
        "NSE", "BSE", "OLD", "NEW", "LIVE", "ALERTS", "SCAN", "SCANS", "ATLAS",
        "CHART", "GUIDE", "LOGIN", "REGISTER", "PREMIUM", "REALTIME", "FEEDBACK",
        "DESCRIPTION", "MORNING", "BUY"
    }
    cleaned = [c for c in candidates if c not in ignore and not c.isdigit()]
    return sorted(cleaned)

def fetch_symbols() -> List[str]:
    r = session.get(SCREENER_URL, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    symbols = extract_symbols_from_html(r.text)
    return symbols

def send_telegram(message: str) -> None:
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.warning("Telegram credentials missing; skipping notification")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "disable_web_page_preview": True,
    }
    r = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()

def build_message(new_symbols: List[str], all_symbols: List[str]) -> str:
    lines = [
        "Chartink NR7 Alert",
        f"New symbols: {', '.join(new_symbols)}",
        f"Current symbols count: {len(all_symbols)}",
        f"Scanner: {SCREENER_URL}",
    ]
    return "\n".join(lines)

def main() -> None:
    seen = load_seen()
    logging.info("Bot started. Polling every %s seconds", POLL_SECONDS)
    logging.info("Scanner URL: %s", SCREENER_URL)

    while True:
        try:
            symbols = fetch_symbols()
            current = set(symbols)
            new_symbols = sorted(current - seen)

            logging.info("Fetched %s symbols", len(symbols))
            if new_symbols:
                msg = build_message(new_symbols, symbols)
                send_telegram(msg)
                logging.info("Alert sent for: %s", ", ".join(new_symbols))

            seen = current
            save_seen(seen)
        except Exception as e:
            logging.exception("Loop error: %s", e)

        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()