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
        self.start_date = start_date or (datetime.now() - timedelta(weeks=12))  # Extended to 12 weeks
        self.end_date = end_date or datetime.now()
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.position = None
        self.trades = []
        
        # Strategy parameters
        self.rsi_period = 5    # RSI period
        self.rsi_oversold = 40 # Relaxed RSI oversold level
        self.rsi_overbought = 60 # Relaxed RSI overbought level
        self.flow_threshold_5m = 100000  # Reduced to $100K for 5m flow
        self.flow_threshold_1h = 500000  # Reduced to $500K for 1h flow
        
        # Risk parameters
        self.leverage = 25          # 25x leverage
        self.risk_percentage = 0.20 # 20% of capital per trade
        self.tp_percentage = 0.05   # 5% take profit
        self.sl_percentage = -0.05  # -5% stop loss
        self.trailing_stop = 0.02   # 2% trailing stop
        
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
        
        # Convert timestamp to UTC datetime
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms', utc=True)
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            
        return df
    
    def load_coinglass_data(self):
        """Load historical Coinglass data"""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        coinglass_file = os.path.join(os.path.dirname(script_dir), "btc_spot_netflow.csv")
        
        if not os.path.exists(coinglass_file):
            print(f"Warning: Coinglass data file not found at {coinglass_file}")
            return None
            
        df = pd.read_csv(coinglass_file)
        # Convert timestamp to UTC datetime
        df['Timestamp'] = pd.to_datetime(df['Timestamp'], format="%d %b %Y, %H:%M", utc=True)
        print(f"Loaded {len(df)} Coinglass data points")
        print("Sample data:")
        print(df.head())
        return df
    
    def calculate_indicators(self, df):
        """Calculate technical indicators"""
        # Calculate RSI
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss
        df['RSI'] = 100 - (100 / (1 + rs))
        
        return df
    
    def generate_signals(self, df, coinglass_df):
        """Generate trading signals based on strategy rules"""
        df['Signal'] = 0  # 0 for no signal, 1 for buy, -1 for sell
        
        if coinglass_df is not None:
            # Ensure both dataframes use UTC timezone
            df['timestamp'] = df['timestamp'].dt.tz_localize('UTC') if df['timestamp'].dt.tz is None else df['timestamp']
            coinglass_df['Timestamp'] = coinglass_df['Timestamp'].dt.tz_localize('UTC') if coinglass_df['Timestamp'].dt.tz is None else coinglass_df['Timestamp']
            # Sort by timestamp in descending order to get latest data first
            coinglass_df = coinglass_df.sort_values('Timestamp', ascending=False)
            print(f"Coinglass data range: {coinglass_df['Timestamp'].min()} to {coinglass_df['Timestamp'].max()}")
            print(f"Price data range: {df['timestamp'].min()} to {df['timestamp'].max()}")
        
        for i in range(len(df)):
            if i < self.rsi_period:  # Wait for RSI to be calculated
                continue
                
            current_price = df['close'].iloc[i]
            rsi = df['RSI'].iloc[i]
            
            # Get corresponding Coinglass data
            flow_5m = 0
            flow_1h = 0
            if coinglass_df is not None:
                timestamp = df['timestamp'].iloc[i]
                # Find the closest timestamp within 5 minutes
                closest_data = coinglass_df[coinglass_df['Timestamp'] <= timestamp].iloc[0] if not coinglass_df[coinglass_df['Timestamp'] <= timestamp].empty else None
                if closest_data is not None:
                    time_diff = timestamp - closest_data['Timestamp']
                    if time_diff.total_seconds() <= 300:  # Within 5 minutes
                        flow_5m = float(closest_data['5m'])
                        flow_1h = float(closest_data['1h'])
            
            # Debug print for signal conditions
            if i % 100 == 0:  # Print every 100th candle to avoid spam
                print(f"\nTime: {df['timestamp'].iloc[i]}")
                print(f"Price: {current_price:.2f}")
                print(f"RSI: {rsi:.1f}")
                print(f"5m Flow: {flow_5m:,.0f}")
                print(f"1h Flow: {flow_1h:,.0f}")
            
            # Long signal conditions (either RSI or flow)
            rsi_long = rsi < self.rsi_oversold
            flow_long = (flow_5m < -self.flow_threshold_5m or flow_1h < -self.flow_threshold_1h)
            long_conditions = rsi_long or flow_long
            
            # Short signal conditions (either RSI or flow)
            rsi_short = rsi > self.rsi_overbought
            flow_short = (flow_5m > self.flow_threshold_5m or flow_1h > self.flow_threshold_1h)
            short_conditions = rsi_short or flow_short
            
            # Debug print conditions
            if i % 100 == 0:
                print("\nLong conditions:")
                print(f"RSI < {self.rsi_oversold}: {rsi_long}")
                print(f"5m Flow < -{self.flow_threshold_5m:,.0f}: {flow_5m < -self.flow_threshold_5m}")
                print(f"1h Flow < -{self.flow_threshold_1h:,.0f}: {flow_1h < -self.flow_threshold_1h}")
                print(f"Either condition met: {long_conditions}")
                
                print("\nShort conditions:")
                print(f"RSI > {self.rsi_overbought}: {rsi_short}")
                print(f"5m Flow > {self.flow_threshold_5m:,.0f}: {flow_5m > self.flow_threshold_5m}")
                print(f"1h Flow > {self.flow_threshold_1h:,.0f}: {flow_1h > self.flow_threshold_1h}")
                print(f"Either condition met: {short_conditions}")
            
            if long_conditions:
                df.loc[df.index[i], 'Signal'] = 1  # Buy signal
                print(f"\nLONG Signal at {df['timestamp'].iloc[i]}:")
                print(f"Price: {current_price:.2f}")
                print(f"RSI: {rsi:.1f}")
                print(f"5m Flow: {flow_5m:,.0f}")
                print(f"1h Flow: {flow_1h:,.0f}")
                print(f"Trigger: {'RSI' if rsi_long else 'Flow'}")
            elif short_conditions:
                df.loc[df.index[i], 'Signal'] = -1  # Sell signal
                print(f"\nSHORT Signal at {df['timestamp'].iloc[i]}:")
                print(f"Price: {current_price:.2f}")
                print(f"RSI: {rsi:.1f}")
                print(f"5m Flow: {flow_5m:,.0f}")
                print(f"1h Flow: {flow_1h:,.0f}")
                print(f"Trigger: {'RSI' if rsi_short else 'Flow'}")
        
        return df
    
    def calculate_position_size(self, entry_price):
        """Calculate position size based on risk parameters"""
        # Calculate maximum loss allowed for this trade
        risk_amount = self.balance * self.risk_percentage
        
        # Calculate position size based on stop loss distance
        stop_distance = abs(self.sl_percentage)  # Distance to stop loss (5%)
        
        # Calculate the actual position size considering leverage
        # If we risk $1000 on a 5% move with 25x leverage, our base position should be $800
        # Because: $800 * 5% * 25x = $1000 (maximum loss)
        position_value = (risk_amount / (stop_distance * self.leverage))
        
        # Calculate the number of contracts
        contract_qty = position_value / entry_price
        
        return contract_qty

    def execute_trade(self, row, signal):
        """Execute trade with position sizing and risk management"""
        if signal != 0 and self.current_position is None:  # Open new position
            entry_price = row['close']
            position_size = self.calculate_position_size(entry_price)
            
            # Calculate stop loss and take profit levels
            sl_price = entry_price * (1 + self.sl_percentage) if signal == 1 else entry_price * (1 - self.sl_percentage)
            tp_price = entry_price * (1 + self.tp_percentage) if signal == 1 else entry_price * (1 - self.tp_percentage)
            
            self.current_position = {
                'type': 'long' if signal == 1 else 'short',
                'entry_price': entry_price,
                'entry_time': row['timestamp'],
                'size': position_size,
                'tp_price': tp_price,
                'sl_price': sl_price,
                'highest_price': entry_price if signal == 1 else float('inf'),
                'lowest_price': entry_price if signal == -1 else float('-inf')
            }
            
        elif self.current_position is not None:  # Check for exit conditions
            current_price = row['close']
            position_type = self.current_position['type']
            entry_price = self.current_position['entry_price']
            position_size = self.current_position['size']
            
            # Update highest/lowest prices for trailing stop
            if position_type == 'long':
                self.current_position['highest_price'] = max(self.current_position['highest_price'], current_price)
            else:  # short
                self.current_position['lowest_price'] = min(self.current_position['lowest_price'], current_price)
            
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
                # Check trailing stop
                elif current_price <= self.current_position['highest_price'] * (1 - self.trailing_stop):
                    exit_signal = True
                    exit_reason = 'trailing_stop'
            else:  # short
                if current_price <= self.current_position['tp_price']:
                    exit_signal = True
                    exit_reason = 'tp'
                elif current_price >= self.current_position['sl_price']:
                    exit_signal = True
                    exit_reason = 'sl'
                # Check trailing stop
                elif current_price >= self.current_position['lowest_price'] * (1 + self.trailing_stop):
                    exit_signal = True
                    exit_reason = 'trailing_stop'
            
            if exit_signal:
                trade = {
                    'entry_time': self.current_position['entry_time'],
                    'exit_time': row['timestamp'],
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
        
        # Track equity curve for drawdown calculation
        equity_curve = [self.initial_balance]
        running_balance = self.initial_balance
        peak_balance = self.initial_balance
        max_drawdown = 0
        
        # Calculate profit metrics
        total_profit = 0
        total_wins = 0
        total_losses = 0
        win_count = 0
        loss_count = 0
        
        for trade in trades:
            pnl = trade['pnl']
            running_balance += pnl
            equity_curve.append(running_balance)
            
            # Update peak and calculate drawdown
            if running_balance > peak_balance:
                peak_balance = running_balance
            else:
                drawdown = (peak_balance - running_balance) / peak_balance * 100
                max_drawdown = max(max_drawdown, drawdown)
            
            # Track wins and losses
            if pnl > 0:
                total_wins += pnl
                win_count += 1
            else:
                total_losses += abs(pnl)
                loss_count += 1
        
        # Calculate averages
        avg_win = total_wins / win_count if win_count > 0 else 0
        avg_loss = total_losses / loss_count if loss_count > 0 else 0
        
        # Calculate profit factor
        profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')
        
        # Count exit reasons
        tp_hits = len([t for t in trades if t['exit_reason'] == 'tp'])
        sl_hits = len([t for t in trades if t['exit_reason'] == 'sl'])
        trailing_hits = len([t for t in trades if t['exit_reason'] == 'trailing_stop'])
        
        # Calculate total return
        total_return = ((running_balance - self.initial_balance) / self.initial_balance) * 100
        
        return {
            'Total Trades': total_trades,
            'Win Rate': f"{win_rate:.2%}",
            'Total Return': f"{total_return:.2f}%",
            'Max Drawdown': f"{max_drawdown:.2f}%",
            'Average Win': f"${avg_win:.2f}",
            'Average Loss': f"${avg_loss:.2f}",
            'Profit Factor': f"{profit_factor:.2f}",
            'TP Hits': tp_hits,
            'SL Hits': sl_hits,
            'Trailing Stop Hits': trailing_hits,
            'Final Capital': f"${running_balance:.2f}",
            'Leverage Used': f"{self.leverage}x",
            'Risk Per Trade': f"{self.risk_percentage:.0%}"
        }
    
    def plot_results(self, df, trades):
        """Plot backtest results"""
        plt.style.use('dark_background')
        fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(15, 12), gridspec_kw={'height_ratios': [2, 1, 1]})
        
        # Plot price
        ax1.plot(df['timestamp'], df['close'], label='Price', alpha=0.8)
        
        # Plot entry/exit points
        for trade in trades:
            if trade['type'] == 'long':
                ax1.scatter(trade['entry_time'], trade['entry_price'], color='g', marker='^', s=100, label='Long Entry' if 'Long Entry' not in ax1.get_legend_handles_labels()[1] else '')
                ax1.scatter(trade['exit_time'], trade['exit_price'], color='r', marker='v', s=100, label='Long Exit' if 'Long Exit' not in ax1.get_legend_handles_labels()[1] else '')
            else:
                ax1.scatter(trade['entry_time'], trade['entry_price'], color='r', marker='v', s=100, label='Short Entry' if 'Short Entry' not in ax1.get_legend_handles_labels()[1] else '')
                ax1.scatter(trade['exit_time'], trade['exit_price'], color='g', marker='^', s=100, label='Short Exit' if 'Short Exit' not in ax1.get_legend_handles_labels()[1] else '')
        
        ax1.set_title(f'Backtest Results - {self.symbol} ({self.leverage}x Leverage)')
        ax1.legend()
        ax1.grid(True, alpha=0.2)
        
        # Plot RSI with updated levels
        ax2.plot(df['timestamp'], df['RSI'], label='RSI', color='purple', alpha=0.8)
        ax2.axhline(y=self.rsi_overbought, color='r', linestyle='--', alpha=0.3, label=f'Overbought ({self.rsi_overbought})')
        ax2.axhline(y=self.rsi_oversold, color='g', linestyle='--', alpha=0.3, label=f'Oversold ({self.rsi_oversold})')
        ax2.set_title('RSI(5)')
        ax2.legend()
        ax2.grid(True, alpha=0.2)
        
        # Plot portfolio value
        if trades:
            equity_curve = [self.initial_balance]
            current_balance = self.initial_balance
            timestamps = [df['timestamp'].iloc[0]]
            
            for trade in trades:
                current_balance += trade['pnl']
                equity_curve.append(current_balance)
                timestamps.append(trade['exit_time'])
            
            ax3.plot(timestamps, equity_curve, label='Portfolio Value', color='cyan')
            ax3.set_title(f'Portfolio Value (Initial: ${self.initial_balance:,.2f})')
            ax3.legend()
            ax3.grid(True, alpha=0.2)
            
            # Add final value annotation
            final_value = equity_curve[-1]
            total_return = ((final_value - self.initial_balance) / self.initial_balance) * 100
            ax3.annotate(f'Final: ${final_value:,.2f} ({total_return:+.2f}%)', 
                        xy=(timestamps[-1], final_value),
                        xytext=(10, 10), textcoords='offset points')
        
        # Format x-axis to show dates
        for ax in [ax1, ax2, ax3]:
            ax.xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter('%Y-%m-%d %H:%M'))
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
            ax.set_xlim(df['timestamp'].iloc[0], df['timestamp'].iloc[-1])
        
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
        start_date=datetime.now() - timedelta(weeks=12)  # Extended to 12 weeks
    )
    
    # Run backtest
    df, trades, metrics = backtester.run_backtest()

if __name__ == "__main__":
    main() 