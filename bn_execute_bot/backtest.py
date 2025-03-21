import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
from binance.client import Client
import os
from dotenv import load_dotenv

class Backtester:
    def __init__(self, api_key, api_secret, symbol="BTCUSDT", timeframe="5m", 
                 start_date=None, end_date=None, initial_balance=10000):
        self.client = Client(api_key, api_secret)
        self.symbol = symbol
        self.timeframe = timeframe
        self.start_date = start_date or (datetime.now() - timedelta(days=30))
        self.end_date = end_date or datetime.now()
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.position = None
        self.trades = []
        
        # Strategy parameters
        self.ma_short = 7
        self.ma_long = 25
        self.rsi_period = 14
        self.rsi_oversold = 30
        self.rsi_overbought = 70
        self.flow_5m_threshold = 1000000  # $1M
        self.flow_1h_threshold = 5000000  # $5M
        
        # Performance metrics
        self.metrics = {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'win_rate': 0,
            'avg_win': 0,
            'avg_loss': 0,
            'max_drawdown': 0,
            'profit_factor': 0,
            'total_return': 0
        }
    
    def fetch_historical_data(self):
        """Fetch historical price data from Binance"""
        klines = self.client.get_historical_klines(
            self.symbol,
            self.timeframe,
            self.start_date.strftime("%d %b %Y %H:%M:%S"),
            self.end_date.strftime("%d %b %Y %H:%M:%S")
        )
        
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignored'
        ])
        
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
        return df
    
    def load_coinglass_data(self):
        """Load historical Coinglass data"""
        coinglass_file = "../coinglass/btc_spot_netflow.csv"
        if not os.path.exists(coinglass_file):
            print("Warning: Coinglass data file not found")
            return None
            
        df = pd.read_csv(coinglass_file)
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], format="%d %b %Y, %H:%M")
        return df
    
    def calculate_indicators(self, df):
        """Calculate technical indicators"""
        # Calculate MAs
        df['MA7'] = df['close'].rolling(window=self.ma_short).mean()
        df['MA25'] = df['close'].rolling(window=self.ma_long).mean()
        
        # Calculate RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        return df
    
    def generate_signals(self, df, coinglass_df):
        """Generate trading signals based on strategy rules"""
        df['Signal'] = 'NO SIGNAL'
        
        for i in range(len(df)):
            if i < self.ma_long:
                continue
                
            # Check MA crossover
            bullish_trend = df['MA7'].iloc[i] > df['MA25'].iloc[i]
            bearish_trend = df['MA7'].iloc[i] < df['MA25'].iloc[i]
            
            # Get corresponding Coinglass data
            if coinglass_df is not None:
                timestamp = df['timestamp'].iloc[i]
                coinglass_data = coinglass_df[coinglass_df['Timestamp'] <= timestamp].iloc[0]
                flow_5m = float(coinglass_data['5m'])
                flow_1h = sum(coinglass_df[coinglass_df['Timestamp'] <= timestamp].head(12)['5m'])
            else:
                flow_5m = 0
                flow_1h = 0
            
            # Generate signals
            if bullish_trend:
                if (df['RSI'].iloc[i] < self.rsi_oversold or 
                    flow_5m < -self.flow_5m_threshold or 
                    flow_1h < -self.flow_1h_threshold):
                    df.loc[df.index[i], 'Signal'] = 'BUY'
            
            elif bearish_trend:
                if (df['RSI'].iloc[i] > self.rsi_overbought or 
                    flow_5m > self.flow_5m_threshold or 
                    flow_1h > self.flow_1h_threshold):
                    df.loc[df.index[i], 'Signal'] = 'SELL'
        
        return df
    
    def execute_trades(self, df):
        """Execute trades based on signals"""
        position = None
        entry_price = 0
        trades = []
        
        for i in range(len(df)):
            signal = df['Signal'].iloc[i]
            current_price = df['close'].iloc[i]
            
            # Open positions
            if signal == 'BUY' and position is None:
                position = 'LONG'
                entry_price = current_price
                trades.append({
                    'entry_time': df['timestamp'].iloc[i],
                    'entry_price': entry_price,
                    'type': 'LONG'
                })
            
            elif signal == 'SELL' and position is None:
                position = 'SHORT'
                entry_price = current_price
                trades.append({
                    'entry_time': df['timestamp'].iloc[i],
                    'entry_price': entry_price,
                    'type': 'SHORT'
                })
            
            # Close positions on opposite signals
            elif signal == 'SELL' and position == 'LONG':
                pnl = (current_price - entry_price) / entry_price * 100
                trades[-1].update({
                    'exit_time': df['timestamp'].iloc[i],
                    'exit_price': current_price,
                    'pnl': pnl
                })
                position = None
            
            elif signal == 'BUY' and position == 'SHORT':
                pnl = (entry_price - current_price) / entry_price * 100
                trades[-1].update({
                    'exit_time': df['timestamp'].iloc[i],
                    'exit_price': current_price,
                    'pnl': pnl
                })
                position = None
        
        return trades
    
    def calculate_metrics(self, trades):
        """Calculate performance metrics"""
        if not trades:
            return self.metrics
            
        # Calculate basic metrics
        self.metrics['total_trades'] = len(trades)
        
        # Calculate P&L metrics
        winning_trades = [t for t in trades if t.get('pnl', 0) > 0]
        losing_trades = [t for t in trades if t.get('pnl', 0) <= 0]
        
        self.metrics['winning_trades'] = len(winning_trades)
        self.metrics['losing_trades'] = len(losing_trades)
        self.metrics['win_rate'] = len(winning_trades) / len(trades) * 100
        
        if winning_trades:
            self.metrics['avg_win'] = np.mean([t['pnl'] for t in winning_trades])
        if losing_trades:
            self.metrics['avg_loss'] = np.mean([t['pnl'] for t in losing_trades])
            
        # Calculate cumulative returns and drawdown
        cumulative_returns = np.cumsum([t.get('pnl', 0) for t in trades])
        peak = np.maximum.accumulate(cumulative_returns)
        drawdown = (peak - cumulative_returns)
        self.metrics['max_drawdown'] = np.max(drawdown)
        self.metrics['total_return'] = cumulative_returns[-1]
        
        # Calculate profit factor
        total_gains = sum([t['pnl'] for t in winning_trades])
        total_losses = abs(sum([t['pnl'] for t in losing_trades]))
        self.metrics['profit_factor'] = total_gains / total_losses if total_losses != 0 else float('inf')
        
        return self.metrics
    
    def plot_results(self, df, trades):
        """Plot price action, indicators, and trades"""
        plt.figure(figsize=(15, 10))
        
        # Plot price and MAs
        plt.subplot(2, 1, 1)
        plt.plot(df['timestamp'], df['close'], label='Price', alpha=0.7)
        plt.plot(df['timestamp'], df['MA7'], label='MA7', alpha=0.7)
        plt.plot(df['timestamp'], df['MA25'], label='MA25', alpha=0.7)
        
        # Plot trades
        for trade in trades:
            if trade.get('exit_time'):
                color = 'g' if trade.get('pnl', 0) > 0 else 'r'
                plt.plot([trade['entry_time'], trade['exit_time']], 
                        [trade['entry_price'], trade['exit_price']], 
                        color=color, linewidth=2, alpha=0.7)
        
        plt.title('Price Action and Trades')
        plt.legend()
        
        # Plot RSI
        plt.subplot(2, 1, 2)
        plt.plot(df['timestamp'], df['RSI'], label='RSI', color='purple', alpha=0.7)
        plt.axhline(y=self.rsi_oversold, color='g', linestyle='--', alpha=0.5)
        plt.axhline(y=self.rsi_overbought, color='r', linestyle='--', alpha=0.5)
        plt.title('RSI')
        plt.legend()
        
        plt.tight_layout()
        plt.show()
    
    def run_backtest(self):
        """Run the complete backtest"""
        print("Fetching historical data...")
        df = self.fetch_historical_data()
        
        print("Loading Coinglass data...")
        coinglass_df = self.load_coinglass_data()
        
        print("Calculating indicators...")
        df = self.calculate_indicators(df)
        
        print("Generating signals...")
        df = self.generate_signals(df, coinglass_df)
        
        print("Executing trades...")
        trades = self.execute_trades(df)
        
        print("Calculating metrics...")
        metrics = self.calculate_metrics(trades)
        
        print("\nBacktest Results:")
        print(f"Total Trades: {metrics['total_trades']}")
        print(f"Win Rate: {metrics['win_rate']:.2f}%")
        print(f"Average Win: {metrics['avg_win']:.2f}%")
        print(f"Average Loss: {metrics['avg_loss']:.2f}%")
        print(f"Profit Factor: {metrics['profit_factor']:.2f}")
        print(f"Max Drawdown: {metrics['max_drawdown']:.2f}%")
        print(f"Total Return: {metrics['total_return']:.2f}%")
        
        print("\nPlotting results...")
        self.plot_results(df, trades)
        
        return df, trades, metrics

def main():
    # Load environment variables
    load_dotenv()
    api_key = os.getenv('BINANCE_API_KEY')
    api_secret = os.getenv('BINANCE_API_SECRET')
    
    if not api_key or not api_secret:
        raise ValueError("API keys not found in environment variables")
    
    # Create backtester instance
    backtester = Backtester(
        api_key=api_key,
        api_secret=api_secret,
        symbol="BTCUSDT",
        timeframe="5m",
        start_date=datetime.now() - timedelta(days=30)  # Last 30 days
    )
    
    # Run backtest
    df, trades, metrics = backtester.run_backtest()

if __name__ == "__main__":
    main() 