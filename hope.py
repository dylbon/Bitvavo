import requests
import time
import signal
import sys

# === CONFIG ===
BOT_TOKEN = "8202969495:AAGf1TIJH_kvY0Navr3GcUJfM3b46sOhpSw"
CHAT_ID = "5659915827"
THRESHOLD_PERCENT = 3.0  # Price difference threshold
CHECK_INTERVAL = 60  # Time between full cycles in seconds
MAX_RETRIES = 3  # Retry attempts for failed API calls
BINANCE_RATE_LIMIT = 0.05  # Seconds between Binance API calls
BITVAVO_RATE_LIMIT = 0.05  # Seconds between Bitvavo API calls
MEXC_RATE_LIMIT = 0.05  # Seconds between MEXC API calls
BITVAVO_TAKER_FEE = 0.0025  # 0.25% taker fee for selling on Bitvavo
BINANCE_TAKER_FEE = 0.001   # 0.1% taker fee for buying on Binance
MEXC_TAKER_FEE = 0.0005     # 0.05% taker fee for buying on MEXC
BLACKLIST = {'ALPHA', 'HOOK', 'ONG', 'DCR', 'STRAX'}  # Exclude these base assets

# Symbol mapping for mismatches (Bitvavo base -> Binance base)
SYMBOL_MAP = {
    'LUNA': 'LUNC',   # Bitvavo LUNA is Terra Classic (Binance LUNC)
    'LUNA2': 'LUNA',  # Bitvavo LUNA2 is Terra 2.0 (Binance LUNA)
    'BTT': 'BTTC',    # Bitvavo BTT is BitTorrent (Binance BTTC)
    'FUN': 'FUNTOKEN',# To skip Binance's mismatched FUN
    'HNT': 'HNT',      #HNT MAP
    'UP': 'SUPERFORM'   # Bitvavo UP is Superform on MEXC
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
                print(f"📤 Telegram message sent successfully! 🎉")
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

def fetch_mexc_tickers():
    """Fetch all 24h tickers from MEXC and extract last prices for EUR and USDT markets."""
    print("🔄 Fetching all MEXC 24h tickers...")
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get("https://api.mexc.com/api/v3/ticker/24hr", timeout=10)
            if resp.status_code != 200:
                print(f"❗ HTTP error: {resp.status_code} - {resp.text}")
                continue
            data = resp.json()
            prices = {}
            for d in data:
                symbol = d.get("symbol", "")
                if symbol.endswith("EUR") or symbol.endswith("USDT"):
                    # Handle EUR pairs (hyphenated or not)
                    if symbol.endswith("EUR"):
                        if "-" in symbol and symbol.endswith("-EUR"):
                            m = symbol  # Already formatted, e.g., "WAXP-EUR"
                        else:
                            m = symbol[:-3] + "-" + symbol[-3:]  # Insert hyphen, e.g., "WAXPEUR" -> "WAXP-EUR"
                    else:
                        # Handle USDT pairs, keep as-is
                        m = symbol  # e.g., "IKAUSDT"
                    last_price = float(d["lastPrice"])
                    prices[m] = last_price
                    print(f"✅ Last price for {m}: {last_price:.4f} {'€' if symbol.endswith('EUR') else '$'} 💶")
            print(f"✅ Fetched {len(prices)} MEXC last prices (EUR and USDT). 🎯\n")
            return prices
        except Exception as e:
            print(f"❗ Error fetching MEXC tickers (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
        time.sleep(1 ** attempt)
    print("❌ Failed to fetch MEXC tickers after retries. 😔")
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
    """Check for price differences: buy on Binance/MEXC (last traded), sell on Bitvavo (bid)."""
    bv = fetch_bitvavo_tickers()
    if not bv:
        print("❗ No Bitvavo data. Skipping cycle. 😔")
        return
    bn_all = fetch_all_binance_prices()
    if not bn_all:
        print("❗ No Binance data. Skipping cycle. 😔")
        return
    mex = fetch_mexc_tickers()
    if "EURUSDT" not in bn_all:
        print("❗ EURUSDT not found in Binance prices. Skipping cycle. 😔")
        return
    eur_usdt_rate = bn_all["EURUSDT"]
    if eur_usdt_rate <= 0 or not 0.8 <= eur_usdt_rate <= 1.2:
        print(f"❗ Invalid EURUSDT rate: {eur_usdt_rate:.4f}. Skipping cycle. 😔")
        return
    print(f"✅ EUR/USDT rate: {eur_usdt_rate:.4f} 💱\n")

    found = 0
    for sym, bv_bid in bv.items():
        base = sym.split("-")[0]
        if base in BLACKLIST:
            print(f"❗ Skipping blacklisted ticker: {base}")
            continue

        bn_base = SYMBOL_MAP.get(base, base)  # Use mapped Binance base if mismatch
        bn_sym = bn_base + "USDT"
        exchange = None
        taker_fee = None
        bn_eur = None

        # === SPECIAL HANDLING FOR HOOK: ALWAYS USE MEXC ===
        if base == 'HOOK':
            mex_sym = 'HOOK-EUR'
            mex_usdt_sym = 'HOOKUSDT'
            print(f"🔍 HOOK detected - skipping Binance, checking MEXC: {mex_sym} or {mex_usdt_sym}")
            if mex_sym in mex and mex[mex_sym] > 0:
                bn_eur = mex[mex_sym]
                exchange = 'MEXC'
                taker_fee = MEXC_TAKER_FEE
            else:
                if mex_usdt_sym in mex and mex[mex_usdt_sym] > 0:
                    bn_eur = mex[mex_usdt_sym] / eur_usdt_rate
                    exchange = 'MEXC'
                    taker_fee = MEXC_TAKER_FEE
                    print(f"✅ Using MEXC USDT for HOOK: {mex[mex_usdt_sym]:.4f} → €{bn_eur:.4f}")
                else:
                    print(f"❌ No MEXC price for HOOK")

        # === SPECIAL HANDLING FOR LRC: ALWAYS USE MEXC ===
        elif base == 'LRC':
            mex_sym = 'LRC-EUR'
            mex_usdt_sym = 'LRCUSDT'
            print(f"🔍 LRC detected - skipping Binance, checking MEXC: {mex_sym} or {mex_usdt_sym}")
            if mex_sym in mex and mex[mex_sym] > 0:
                bn_eur = mex[mex_sym]
                exchange = 'MEXC'
                taker_fee = MEXC_TAKER_FEE
            else:
                if mex_usdt_sym in mex and mex[mex_usdt_sym] > 0:
                    bn_eur = mex[mex_usdt_sym] / eur_usdt_rate
                    exchange = 'MEXC'
                    taker_fee = MEXC_TAKER_FEE
                    print(f"✅ Using MEXC USDT for LRC: {mex[mex_usdt_sym]:.4f} → €{bn_eur:.4f}")
                else:
                    print(f"❌ No MEXC price for LRC")

        # === SPECIAL HANDLING FOR FUN, HNT, POLS (unchanged) ===
        elif base in ['FUN', 'HNT', 'POLS']:
            mex_sym = base + '-EUR'
            mex_usdt_sym = base + 'USDT'
            print(f"🔍 Skipping Binance for {base}; checking MEXC: {mex_sym} or {mex_usdt_sym}")
            if mex_sym in mex and mex[mex_sym] > 0:
                bn_eur = mex[mex_sym]
                exchange = 'MEXC'
                taker_fee = MEXC_TAKER_FEE
            else:
                if mex_usdt_sym in mex and mex[mex_usdt_sym] > 0:
                    bn_eur = mex[mex_usdt_sym] / eur_usdt_rate
                    exchange = 'MEXC'
                    taker_fee = MEXC_TAKER_FEE
                    print(f"✅ Using MEXC USDT for {sym}: {mex[mex_usdt_sym]:.4f} → €{bn_eur:.4f}")
                else:
                    print(f"❌ No MEXC price for {mex_sym} or {mex_usdt_sym}")
        
        else:
            # Normal flow for all other coins
            if bn_sym in bn_all:
                bn_usdt = bn_all[bn_sym]
                if bn_usdt > 0:
                    bn_eur = bn_usdt / eur_usdt_rate
                    exchange = 'Binance'
                    taker_fee = BINANCE_TAKER_FEE
            else:
                # Try MEXC EUR pair first
                mex_sym = bn_base + "-EUR"
                mex_usdt_sym = bn_base + "USDT"
                print(f"🔍 Binance missing {bn_sym}; checking MEXC: {mex_sym} or {mex_usdt_sym}")
                if mex_sym in mex and mex[mex_sym] > 0:
                    bn_eur = mex[mex_sym]
                    exchange = 'MEXC'
                    taker_fee = MEXC_TAKER_FEE
                else:
                    # Fallback to MEXC USDT pair
                    if mex_usdt_sym in mex and mex[mex_usdt_sym] > 0:
                        bn_eur = mex[mex_usdt_sym] / eur_usdt_rate
                        exchange = 'MEXC'
                        taker_fee = MEXC_TAKER_FEE
                        print(f"✅ Using MEXC USDT for {sym}: {mex[mex_usdt_sym]:.4f} → €{bn_eur:.4f}")
                    else:
                        print(f"❌ No MEXC price for {mex_sym} or {mex_usdt_sym}")

        if bn_eur is None or bn_eur <= 0:
            print(f"❗ No valid price for {sym} on Binance or MEXC. Skipping.")
            continue

        print(f"✅ {exchange} price for {sym} (EUR-converted): €{bn_eur:.4f} 💵")

        adjusted_bn = bn_eur * (1 + taker_fee)
        adjusted_bv = bv_bid * (1 - BITVAVO_TAKER_FEE)

        if adjusted_bn <= 0:
            print(f"❗ Invalid adjusted {exchange} price for {sym}: €{adjusted_bn:.4f}. Skipping.")
            continue

        diff = (adjusted_bv - adjusted_bn) / adjusted_bn * 100
        if diff >= THRESHOLD_PERCENT:
            found += 1
            msg = (
                f"*🚀 Arbitrage Opportunity! 🚀*\n"
                f"💸 *Buy {base}* on {exchange}: €{bn_eur:.4f}\n"
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
    print("🚀 Starting arbitrage monitor (Buy on Binance/MEXC USDT/EUR last traded, Sell on Bitvavo EUR bid). 🌟")
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