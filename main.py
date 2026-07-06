import os
import json
import time
import logging
import requests

SCREENER_URL = "https://chartink.com/screener/process"
SCREENER_SLUG = os.getenv("SCREENER_SLUG", "copy-morning-scanner-for-buy-nr7-based-breakout-8")
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "60"))
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
STATE_FILE = os.getenv("STATE_FILE", "seen_state.json")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": f"https://chartink.com/screener/{SCREENER_SLUG}",
})

def get_csrf_token():
    r = session.get(f"https://chartink.com/screener/{SCREENER_SLUG}", timeout=30)
    for line in r.text.split("\n"):
        if "csrf-token" in line:
            token = line.split('content="')[1].split('"')[0]
            logging.info("CSRF token fetched")
            return token
    return None

def load_seen():
    if not os.path.exists(STATE_FILE):
        return set()
    try:
        with open(STATE_FILE, "r") as f:
            return set(json.load(f).get("symbols", []))
    except Exception:
        return set()

def save_seen(symbols):
    with open(STATE_FILE, "w") as f:
        json.dump({"symbols": sorted(symbols)}, f, indent=2)

def fetch_symbols(csrf_token):
    headers = {"X-CSRF-TOKEN": csrf_token}
    data = {"scan_clause": ""}
    
    # Get scan clause from screener page
    r = session.get(f"https://chartink.com/screener/{SCREENER_SLUG}", timeout=30)
    
    # Extract scan_clause
    if "scan_clause" in r.text:
        try:
            part = r.text.split('"scan_clause"')[1]
            clause = part.split('value="')[1].split('"')[0]
            data["scan_clause"] = clause
        except Exception:
            pass
    
    resp = session.post(
        SCREENER_URL,
        data=data,
        headers=headers,
        timeout=30
    )
    
    result = resp.json()
    symbols = []
    
    if "data" in result:
        for row in result["data"]:
            sym = row.get("nsecode") or row.get("symbol") or row.get("name", "")
            if sym:
                symbols.append(sym.strip())
    
    logging.info("Fetched %d symbols: %s", len(symbols), symbols)
    return symbols

def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logging.warning("Telegram credentials missing")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "disable_web_page_preview": True,
    }
    r = requests.post(url, json=payload, timeout=30)
    logging.info("Telegram response: %s", r.text)

def main():
    seen = load_seen()
    csrf_token = None
    logging.info("Bot started. Polling every %s seconds", POLL_SECONDS)

    while True:
        try:
            if not csrf_token:
                csrf_token = get_csrf_token()
            
            symbols = fetch_symbols(csrf_token)
            current = set(symbols)
            new_symbols = sorted(current - seen)

            if new_symbols:
                msg = (
                    f"NR7 Breakout Alert!\n"
                    f"New Stocks: {', '.join(new_symbols)}\n"
                    f"Total: {len(symbols)} stocks\n"
                    f"Time: {time.strftime('%H:%M:%S')}"
                )
                send_telegram(msg)
                logging.info("Alert sent: %s", new_symbols)

            seen = current
            save_seen(seen)

        except Exception as e:
            logging.exception("Error: %s", e)
            csrf_token = None  # Reset token on error

        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()