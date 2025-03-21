# Binance Trading Bot with Coinglass Netflow Signals

A cryptocurrency trading bot that combines technical analysis with Coinglass exchange flow data to generate trading signals for Binance Futures.

## Project Structure

```
Grok/
├── bn_execute_bot/          # Main trading bot
│   ├── main.py             # Entry point
│   ├── gui.py              # Trading interface
│   ├── trader.py           # Trading logic
│   ├── strategies.json     # Trading templates
│   └── .env               # API credentials
└── coinglass/             # Coinglass data crawler
    ├── btc_crawler.py     # Data collection script
    ├── btc_spot_netflow.csv # Exchange flow data
    └── requirements.txt   # Dependencies
```

## Features

- Real-time trading signals based on:
  - Technical Analysis (5-minute timeframe)
    - MA7/MA25 crossovers
    - RSI (14 periods)
  - Coinglass Exchange Flow Data
    - 5-minute netflow
    - 1-hour aggregated netflow
- Automated trade execution with:
  - Fixed Take Profit (5%)
  - Fixed Stop Loss (-10%)
  - 1-hour position auto-close
- User-friendly GUI with:
  - Real-time price updates
  - Exchange flow visualization
  - Trade history tracking
  - Collapsible logging panel

## Signal Generation Logic

The bot generates trading signals by combining multiple indicators:

### Technical Analysis
- MA Crossovers (5-minute timeframe)
  - Bullish: MA7 crosses above MA25
  - Bearish: MA7 crosses below MA25
- RSI (14 periods)
  - Oversold: RSI < 30 (bullish)
  - Overbought: RSI > 70 (bearish)

### Exchange Flow Analysis
- 5-minute netflow thresholds
  - Bullish: < -1M USD (significant outflow)
  - Bearish: > +1M USD (significant inflow)
- 1-hour netflow thresholds
  - Bullish: < -5M USD (sustained outflow)
  - Bearish: > +5M USD (sustained inflow)

## Setup

1. Clone the repository:
```bash
git clone https://github.com/Daikonkun/bn_bot_with_netflow_signal.git
cd bn_bot_with_netflow_signal
```

2. Install dependencies for both components:
```bash
# Trading bot dependencies
pip install python-binance pandas tkinter python-dotenv

# Coinglass crawler dependencies
cd coinglass
pip install -r requirements.txt
```

3. Configure API credentials:
Create a `.env` file in the bn_execute_bot directory:
```env
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret
```

## Usage

The bot is designed to run both components (trading bot and data crawler) simultaneously:

1. Start the application:
```bash
cd bn_execute_bot
python main.py
```

This will:
- Automatically start the Coinglass data crawler
- Launch the trading bot GUI
- Begin monitoring for trading signals

2. Monitor trading signals:
- The GUI displays current market data and signals
- Exchange flow data updates every 5 minutes
- Trading signals are generated based on the combined analysis
- Position management is automated according to set parameters

3. Application shutdown:
- Closing the GUI will automatically terminate the crawler
- All positions are preserved on Binance
- Data is saved for the next session

## Risk Management

The bot implements fixed risk management parameters:
- Take Profit: 5%
- Stop Loss: -10%
- Maximum position duration: 1 hour
- Leverage and position sizing configurable via templates

## Contributing

Feel free to submit issues, fork the repository, and create pull requests for any improvements.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

Trading cryptocurrencies carries significant risk. This bot is for educational purposes only. Always test thoroughly in testnet before using real funds. 