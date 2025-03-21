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
        
        # Risk parameters
        self.leverage = 25
        self.risk_percentage = 0.50  # 50% of capital per trade
        self.tp_percentage = 0.05    # 5% take profit
        self.sl_percentage = -0.10   # -10% stop loss
        
        self.positions = []
        self.current_position = None
        
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
    
    def calculate_position_size(self, entry_price):
        """Calculate position size based on risk parameters"""
        position_value = self.balance * self.risk_percentage
        contract_qty = (position_value * self.leverage) / entry_price
        return contract_qty

    def execute_trade(self, row, signal):
        """Execute trade with position sizing and risk management"""
        if signal != 0 and self.current_position is None:  # Open new position
            entry_price = row['close']
            position_size = self.calculate_position_size(entry_price)
            
            tp_price = entry_price * (1 + self.tp_percentage) if signal == 1 else entry_price * (1 - self.tp_percentage)
            sl_price = entry_price * (1 + self.sl_percentage) if signal == 1 else entry_price * (1 - self.sl_percentage)
            
            self.current_position = {
                'type': 'long' if signal == 1 else 'short',
                'entry_price': entry_price,
                'entry_time': row.name,
                'size': position_size,
                'tp_price': tp_price,
                'sl_price': sl_price
            }
            
        elif self.current_position is not None:  # Check for exit conditions
            current_price = row['close']
            position_type = self.current_position['type']
            entry_price = self.current_position['entry_price']
            position_size = self.current_position['size']
            
            # Calculate P&L
            if position_type == 'long':
                price_change = (current_price - entry_price) / entry_price
            else:  # short
                price_change = (entry_price - current_price) / entry_price
                
            pnl = position_size * entry_price * price_change * self.leverage
            
            # Check if TP or SL hit
            exit_signal = False
            exit_reason = ''
            
            if position_type == 'long':
                if current_price >= self.current_position['tp_price']:
                    exit_signal = True
                    exit_reason = 'tp'
                elif current_price <= self.current_position['sl_price']:
                    exit_signal = True
                    exit_reason = 'sl'
            else:  # short
                if current_price <= self.current_position['tp_price']:
                    exit_signal = True
                    exit_reason = 'tp'
                elif current_price >= self.current_position['sl_price']:
                    exit_signal = True
                    exit_reason = 'sl'
            
            if exit_signal:
                trade = {
                    'entry_time': self.current_position['entry_time'],
                    'exit_time': row.name,
                    'type': position_type,
                    'entry_price': entry_price,
                    'exit_price': current_price,
                    'size': position_size,
                    'pnl': pnl,
                    'exit_reason': exit_reason
                }
                self.trades.append(trade)
                self.balance += pnl
                self.current_position = None
    
    def calculate_metrics(self, trades):
        """Calculate performance metrics"""
        if not trades:
            return {}
        
        total_trades = len(trades)
        profitable_trades = len([t for t in trades if t['pnl'] > 0])
        win_rate = profitable_trades / total_trades if total_trades > 0 else 0
        
        total_profit = sum(t['pnl'] for t in trades)
        profit_percentage = (total_profit / self.initial_balance) * 100
        
        max_drawdown = 0
        peak = self.initial_balance
        for trade in trades:
            capital_after_trade = peak + trade['pnl']
            drawdown = (peak - capital_after_trade) / peak * 100
            max_drawdown = min(max_drawdown, -drawdown)
            peak = max(peak, capital_after_trade)
        
        avg_profit = sum(t['pnl'] for t in trades if t['pnl'] > 0) / profitable_trades if profitable_trades > 0 else 0
        avg_loss = sum(t['pnl'] for t in trades if t['pnl'] <= 0) / (total_trades - profitable_trades) if (total_trades - profitable_trades) > 0 else 0
        
        tp_hits = len([t for t in trades if t['exit_reason'] == 'tp'])
        sl_hits = len([t for t in trades if t['exit_reason'] == 'sl'])
        
        return {
            'Total Trades': total_trades,
            'Win Rate': f"{win_rate:.2%}",
            'Total Return': f"{profit_percentage:.2f}%",
            'Max Drawdown': f"{max_drawdown:.2f}%",
            'Average Profit': f"${avg_profit:.2f}",
            'Average Loss': f"${avg_loss:.2f}",
            'TP Hits': tp_hits,
            'SL Hits': sl_hits,
            'Final Capital': f"${self.balance:.2f}",
            'Leverage Used': f"{self.leverage}x",
            'Risk Per Trade': f"{self.risk_percentage:.0%}"
        }
    
    def plot_results(self, df, trades):
        """Plot backtest results"""
        plt.style.use('dark_background')
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(15, 12), gridspec_kw={'height_ratios': [2, 1, 1]})
        
        # Plot price and MA
        ax1.plot(df.index, df['close'], label='Price', alpha=0.8)
        ax1.plot(df.index, df['MA7'], label='MA7', alpha=0.6)
        ax1.plot(df.index, df['MA25'], label='MA25', alpha=0.6)
        
        # Plot entry/exit points
        for trade in trades:
            if trade['type'] == 'long':
                ax1.scatter(trade['entry_time'], trade['entry_price'], color='g', marker='^', s=100)
                ax1.scatter(trade['exit_time'], trade['exit_price'], color='r', marker='v', s=100)
            else:
                ax1.scatter(trade['entry_time'], trade['entry_price'], color='r', marker='v', s=100)
                ax1.scatter(trade['exit_time'], trade['exit_price'], color='g', marker='^', s=100)
        
        ax1.set_title(f'Backtest Results - {self.symbol} ({self.leverage}x Leverage)')
        ax1.legend()
        ax1.grid(True, alpha=0.2)
        
        # Plot RSI
        ax2.plot(df.index, df['RSI'], label='RSI', color='purple', alpha=0.8)
        ax2.axhline(y=70, color='r', linestyle='--', alpha=0.3)
        ax2.axhline(y=30, color='g', linestyle='--', alpha=0.3)
        ax2.set_title('RSI')
        ax2.legend()
        ax2.grid(True, alpha=0.2)
        
        # Plot cumulative returns
        cumulative_returns = [self.initial_balance]
        current_balance = self.initial_balance
        for trade in trades:
            current_balance += trade['pnl']
            cumulative_returns.append(current_balance)
        
        trade_times = [df.index[0]] + [trade['exit_time'] for trade in trades]
        ax3.plot(trade_times, cumulative_returns, label='Portfolio Value', color='cyan')
        ax3.set_title('Portfolio Value')
        ax3.legend()
        ax3.grid(True, alpha=0.2)
        
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
        for i in range(len(df)):
            signal = df['Signal'].iloc[i]
            self.execute_trade(df.iloc[i], signal)
        
        print("Calculating metrics...")
        metrics = self.calculate_metrics(self.trades)
        
        print("\nBacktest Results:")
        for metric, value in metrics.items():
            print(f"{metric}: {value}")
        
        print("\nPlotting results...")
        self.plot_results(df, self.trades)
        
        return df, self.trades, metrics

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