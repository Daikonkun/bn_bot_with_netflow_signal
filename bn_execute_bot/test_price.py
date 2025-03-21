# test_prices.py
from binance.client import Client
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
if not API_KEY or not API_SECRET:
    raise ValueError("API keys not found in .env")

client = Client(API_KEY, API_SECRET, testnet=True)
ticker = client.futures_symbol_ticker(symbol='BTCUSDT')
trades = client.futures_historical_trades(symbol='BTCUSDT', limit=1)
mark = client.futures_mark_price(symbol='BTCUSDT')
print(f"Ticker: {ticker}")
print(f"Trades: {trades}")
print(f"Mark: {mark}")