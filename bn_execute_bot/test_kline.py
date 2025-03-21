from trader import BinanceFuturesTrader
import os
from dotenv import load_dotenv

load_dotenv()
trader = BinanceFuturesTrader(os.getenv('BINANCE_API_KEY'), os.getenv('BINANCE_API_SECRET'), testnet=True)

# Test current price
try:
    ticker = trader.client.futures_symbol_ticker(symbol='BTCUSDT')
    print(f"Current Price: {ticker['price']}")
except Exception as e:
    print(f"Ticker Error: {e}")

# Test historical data
try:
    klines = trader.client.futures_historical_klines(symbol='BTCUSDT', interval='1m', limit=100)
    print(f"Number of Candles: {len(klines)}")
    print(f"Latest Close: {klines[-1][4]}")
except Exception as e:
    print(f"Klines Error: {e}")