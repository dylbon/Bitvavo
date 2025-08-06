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

def fetch_bitvavo_prices():
    """Fetch highest bid prices from Bitvavo 24h ticker for EUR markets."""
    print("🔄 Fetching Bitvavo markets (EUR)...")
    try:
        markets = requests.get("https://api.bitvavo.com/v2/markets", timeout=10).json()
        eur_markets = [
            m["market"] for m in markets
            if m.get("status") == "trading" and m["market"].endswith("-EUR")
        ]
        print(f"Found {len(eur_markets)} EUR trading markets on Bitvavo. 🏦")
    except Exception as e:
        print(f"❗ Error fetching Bitvavo markets: {e}")
        return {}

    prices = {}
    for idx, sym in enumerate(eur_markets, start=1):
        for attempt in range(MAX_RETRIES):
            try:
                resp = requests.get(f"https://api.bitvavo.com/v2/ticker/24h?market={sym}", timeout=10)
                if resp.status_code != 200:
                    print(f"❗ HTTP error for {sym}: {resp.status_code} - {resp.text}")
                    break
                data = resp.json()
                if "bid" in data and data["bid"]:
                    bid_price = float(data["bid"])
                    # Optional: Check 24h volume for liquidity
                    # if "volume" in data and float(data["volume"]) < 1000:  # Adjust threshold
                    #     print(f"❗ Low 24h volume for {sym}: {data['volume']} units")
                    #     break
                    prices[sym] = bid_price
                    print(f"✅ Bid price for {sym}: €{bid_price:.4f} 💶")
                    break
                else:
                    print(f"❗ No bid price for {sym}: {data}. Skipping.")
                    break
            except Exception as e:
                print(f"❗ Error fetching bid price for {sym} (attempt {attempt + 1}/{MAX_RETRIES}): {e} - HTTP Status: {resp.status_code if 'resp' in locals() else 'N/A'}")
            time.sleep(1 ** attempt)
        else:
            print(f"❌ Failed to fetch bid price for {sym} after retries. Skipping.")
        if idx % 50 == 0:
            print(f"→ Retrieved {idx}/{len(eur_markets)} prices so far.")
        time.sleep(BITVAVO_RATE_LIMIT)
    print(f"✅ Fetched {len(prices)} Bitvavo bid prices (EUR). 🎯\n")
    return prices

def get_eur_usdt_rate():
    """Fetch EUR/USDT last traded price from Binance."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(
                "https://api.binance.com/api/v3/ticker/price?symbol=EURUSDT",
                timeout=10
            )
            if resp.status_code != 200:
                print(f"❗ HTTP error for EURUSDT: {resp.status_code} - {resp.text}")
                return None
            data = resp.json()
            if "price" in data:
                return float(data["price"])  # USDT per EUR
            else:
                print(f"❗ No price data for EURUSDT: {data}")
        except Exception as e:
            print(f"❗ Error fetching EURUSDT price (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
        time.sleep(1 ** attempt)
    print("❌ Failed to fetch EURUSDT price after retries. 😔")
    return None

def fetch_binance_prices(bitvavo_prices):
    """Fetch last traded prices from Binance for USDT pairs and convert to EUR."""
    symbols = [sym.split("-")[0] + "USDT" for sym in bitvavo_prices]
    print("🔄 Fetching Binance USDT markets...")
    
    try:
        resp = requests.get("https://api.binance.com/api/v3/exchangeInfo", timeout=10)
        if resp.status_code != 200:
            print(f"❗ HTTP error for Binance exchange info: {resp.status_code} - {resp.text}")
            return {}
        exchange_info = resp.json()
        binance_pairs = [s["symbol"] for s in exchange_info["symbols"] if s["status"] == "TRADING" and s["symbol"].endswith("USDT")]
        valid_symbols = [sym for sym in symbols if sym in binance_pairs]
        print(f"Found {len(valid_symbols)} matching USDT pairs on Binance. 🏦")
    except Exception as e:
        print(f"❗ Error fetching Binance exchange info: {e}")
        return {}

    eur_usdt_rate = get_eur_usdt_rate()
    if not eur_usdt_rate:
        print("❗ Cannot proceed without EURUSDT price. 😔")
        return {}

    prices = {}
    for idx, sym in enumerate(valid_symbols, start=1):
        for attempt in range(MAX_RETRIES):
            try:
                resp = requests.get(
                    f"https://api.binance.com/api/v3/ticker/price?symbol={sym}",
                    timeout=10
                )
                if resp.status_code != 200:
                    print(f"❗ HTTP error for {sym}: {resp.status_code} - {resp.text}")
                    break
                data = resp.json()
                if "price" in data:
                    usdt_price = float(data["price"])
                    eur_price = usdt_price / eur_usdt_rate
                    prices[sym.replace("USDT", "-EUR")] = eur_price
                    print(f"✅ Last traded price for {sym} (EUR-converted): €{eur_price:.4f} 💵")
                    break
                else:
                    print(f"❗ No price data for {sym}: {data}")
            except Exception as e:
                print(f"❗ Error fetching price for {sym} (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
            time.sleep(1 ** attempt)
        else:
            print(f"❌ Failed to fetch price for {sym} after retries.")
        if idx % 50 == 0:
            print(f"→ Retrieved {idx}/{len(valid_symbols)} prices so far.")
        time.sleep(BINANCE_RATE_LIMIT)
    print(f"✅ Retrieved {len(prices)} Binance EUR-converted prices. 🎯\n")
    return prices

def check_arbitrage():
    """Check for price differences: buy on Binance (last traded), sell on Bitvavo (bid)."""
    bv = fetch_bitvavo_prices()
    if not bv:
        print("❗ No Bitvavo data. Skipping cycle. 😔")
        return
    bn = fetch_binance_prices(bv)
    if not bn:
        print("❗ No Binance data. Skipping cycle. 😔")
        return

    found = 0
    for pair, bp in bv.items():
        bn_price = bn.get(pair)
        if not bn_price:
            print(f"❗ No Binance price for {pair}. Skipping.")
            continue
        adjusted_bn = bn_price * (1 + BINANCE_TAKER_FEE)
        adjusted_bp = bp * (1 - BITVAVO_TAKER_FEE)
        diff = (adjusted_bp - adjusted_bn) / adjusted_bn * 100
        if diff >= THRESHOLD_PERCENT:
            found += 1
            base = pair.split("-")[0]
            msg = (
                f"*🚀 Arbitrage Opportunity! 🚀*\n"
                f"💸 *Buy {base}* on Binance: €{bn_price:.4f}\n"
                f"💰 *Sell on Bitvavo (bid)*: €{bp:.4f}\n"
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