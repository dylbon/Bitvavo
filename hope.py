import requests
import time
import signal
import sys

# === CONFIG ===
BOT_TOKEN = "8202969495:AAGf1TIJH_kvY0Navr3GcUJfM3b46sOhpSw"
CHAT_ID = "5659915827"
THRESHOLD_PERCENT = 4.0  # Price difference threshold
CHECK_INTERVAL = 60      # Time between full cycles in seconds
MAX_RETRIES = 3          # Retry attempts for failed API calls
BINANCE_RATE_LIMIT = 0.05  # Seconds between Binance API calls
BITVAVO_RATE_LIMIT = 0.05  # Seconds between Bitvavo API calls
BITVAVO_TAKER_FEE = 0.0025  # 0.25% taker fee for selling on Bitvavo
BINANCE_TAKER_FEE = 0.001   # 0.1% taker fee for buying on Binance

# Symbol mapping for mismatches (Bitvavo base -> Binance base)
SYMBOL_MAP = {
    'LUNA': 'LUNC',   # Bitvavo LUNA is Terra Classic (Binance LUNC)
    'LUNA2': 'LUNA',  # Bitvavo LUNA2 is Terra 2.0 (Binance LUNA)
    'BTT': 'BTTC'     # Bitvavo BTT is BitTorrent (Binance BTTC)
}

def send_telegram(text):
    """Send a colorful message via Telegram bot with emojis."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.post(
                url,
                json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"},
                timeout=5
            )
            if resp.ok:
                print("📤 Telegram message sent successfully! 🎉")
                return
            else:
                print(f"❗ Telegram send error: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"❗ Telegram send error (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
        time.sleep(1 ** attempt)
    print("❌ Failed to send Telegram message after retries. 😔")

def fetch_bitvavo_tickers():
    """Fetch all 24h tickers from Bitvavo and extract bid prices for EUR markets."""
    print("🔄 Fetching all Bitvavo 24h tickers...")
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get("https://api.bitvavo.com/v2/ticker/24h", timeout=10)
            if resp.status_code != 200:
                print(f"❗ HTTP error: {resp.status_code} - {resp.text}")
                continue
            data = resp.json()
            prices = {}
            for d in data:
                m = d.get("market")
                if m and m.endswith("-EUR") and "bid" in d and d["bid"]:
                    bid_price = float(d["bid"])
                    prices[m] = bid_price
                    print(f"✅ Bid price for {m}: €{bid_price:.4f} 💶")
            print(f"✅ Fetched {len(prices)} Bitvavo bid prices (EUR). 🎯\n")
            return prices
        except Exception as e:
            print(f"❗ Error fetching Bitvavo tickers (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
        time.sleep(1 ** attempt)
    print("❌ Failed to fetch Bitvavo tickers after retries. 😔")
    return {}

def fetch_all_binance_prices():
    """Fetch all last traded prices from Binance."""
    print("🔄 Fetching all Binance prices...")
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get("https://api.binance.com/api/v3/ticker/price", timeout=10)
            if resp.status_code != 200:
                print(f"❗ HTTP error: {resp.status_code} - {resp.text}")
                continue
            data = resp.json()
            prices = {d["symbol"]: float(d["price"]) for d in data if "symbol" in d and "price" in d}
            print(f"✅ Fetched {len(prices)} Binance prices. 🎯\n")
            return prices
        except Exception as e:
            print(f"❗ Error fetching Binance prices (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
        time.sleep(1 ** attempt)
    print("❌ Failed to fetch Binance prices after retries. 😔")
    return {}

def check_arbitrage():
    """Check for price differences: buy on Binance (last traded), sell on Bitvavo (bid)."""
    bv = fetch_bitvavo_tickers()
    if not bv:
        print("❗ No Bitvavo data. Skipping cycle. 😔")
        return

    bn_all = fetch_all_binance_prices()
    if not bn_all:
        print("❗ No Binance data. Skipping cycle. 😔")
        return

    if "EURUSDT" not in bn_all:
        print("❗ EURUSDT not found in Binance prices. Skipping cycle. 😔")
        return
    eur_usdt_rate = bn_all["EURUSDT"]
    print(f"✅ EUR/USDT rate: {eur_usdt_rate:.4f} 💱\n")

    found = 0
    for sym, bv_bid in bv.items():
        base = sym.split("-")[0]
        bn_base = SYMBOL_MAP.get(base, base)  # Use mapped Binance base if mismatch
        bn_sym = bn_base + "USDT"
        if bn_sym not in bn_all:
            print(f"❗ No Binance price for {bn_sym} (Bitvavo: {base}). Skipping.")
            continue
        bn_usdt = bn_all[bn_sym]
        bn_eur = bn_usdt / eur_usdt_rate
        print(f"✅ Binance price for {sym} (EUR-converted): €{bn_eur:.4f} 💵")

        adjusted_bn = bn_eur * (1 + BINANCE_TAKER_FEE)
        adjusted_bv = bv_bid * (1 - BITVAVO_TAKER_FEE)
        diff = (adjusted_bv - adjusted_bn) / adjusted_bn * 100
        if diff >= THRESHOLD_PERCENT:
            found += 1
            msg = (
                f"*🚀 Arbitrage Opportunity! 🚀*\n"
                f"💸 *Buy {base}* on Binance: €{bn_eur:.4f}\n"
                f"💰 *Sell on Bitvavo (bid)*: €{bv_bid:.4f}\n"
                f"📈 *Profit (fee-adjusted)*: {diff:.2f}% 🎉"
            )
            print(msg, "\n")
            send_telegram(msg)

    if found == 0:
        print(f"✅ No opportunities ≥ {THRESHOLD_PERCENT}% this cycle. 😴\n")
    else:
        print(f"📊 Found {found} arbitrage opportunities! 🎉\n")

def signal_handler(sig, frame):
    """Handle graceful exit."""
    print("\n🛑 Stopping arbitrage monitor... 👋")
    sys.exit(0)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)
    print("🚀 Starting arbitrage monitor (Buy on Binance USDT last traded, Sell on Bitvavo EUR bid). 🌟")
    while True:
        try:
            check_arbitrage()
            print(f"⏳ Waiting {CHECK_INTERVAL} seconds until next cycle... 😴")
            time.sleep(CHECK_INTERVAL)
        except KeyboardInterrupt:
            print("\n🛑 Stopping arbitrage monitor... 👋")
            break
        except Exception as e:
            print(f"❗ Unexpected error: {e}. Continuing after {CHECK_INTERVAL} seconds... 😔")
            time.sleep(CHECK_INTERVAL)
