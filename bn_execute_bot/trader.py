# trader.py
from binance.client import Client
import os
from datetime import datetime
import time

class BinanceFuturesTrader:
    def __init__(self, api_key, api_secret, testnet=True):
        self.client = Client(api_key, api_secret, testnet=testnet)
        self.sl_tp_orders = {}  # Dictionary to store SL/TP order details
        try:
            # Sync client time with Binance server time
            server_time = self.client.get_server_time()
            local_time = int(time.time() * 1000)
            time_diff = server_time['serverTime'] - local_time
            self.client.timestamp_offset = time_diff
            self.log_message(f"Adjusted timestamp offset by {time_diff}ms to sync with server")
        except Exception as e:
            self.log_message(f"Error initializing trader: {e}")

    def log_message(self, message):
        """Log messages for debugging; replace with your logging mechanism if needed."""
        print(f"{datetime.now()}: {message}")

    def get_account_balance(self):
        """Fetch account balance in USDT."""
        try:
            account = self.client.futures_account()
            for asset in account['assets']:
                if asset['asset'] == 'USDT':
                    return {
                        'total': float(asset['walletBalance']),
                        'available': float(asset['availableBalance'])
                    }
            self.log_message("USDT balance not found")
            return None
        except Exception as e:
            self.log_message(f"Error fetching account balance: {e}")
            return None

    def get_open_positions(self):
        try:
            positions = self.client.futures_position_information()
            open_positions = [pos for pos in positions if float(pos['positionAmt']) != 0]
            
            # Fetch open orders to check for SL/TP
            orders = self.client.futures_get_open_orders()
            for pos in open_positions:
                contract = pos['symbol']
                # Fetch leverage directly from the exchange
                leverage = float(pos.get('leverage', 1))
                # If leverage is 1, try to fetch it from the exchange's account settings
                if leverage == 1:
                    try:
                        account_info = self.client.futures_account()
                        for asset in account_info['positions']:
                            if asset['symbol'] == contract and float(asset['positionAmt']) != 0:
                                leverage = float(asset['leverage'])
                                break
                    except Exception as e:
                        self.log_message(f"Error fetching leverage for {contract} from account info: {e}")
                sl_order = next((order for order in orders if order['symbol'] == contract and order['type'] == 'STOP_MARKET'), None)
                tp_order = next((order for order in orders if order['symbol'] == contract and order['type'] == 'TAKE_PROFIT_MARKET'), None)
                
                # Update sl_tp_orders with actual exchange data if present
                if sl_order or tp_order:
                    sl_price = float(sl_order['stopPrice']) if sl_order else None
                    tp_price = float(tp_order['stopPrice']) if tp_order else None
                    entry_price = float(pos['entryPrice'])
                    self.log_message(f"Fetched SL/TP prices for {contract}: sl_price={sl_price}, tp_price={tp_price}, entry_price={entry_price}, leverage={leverage}")
                    
                    # Calculate expected SL/TP prices based on template percentages
                    intended_sl_percent = self.sl_tp_orders.get(contract, {}).get('sl_percent', -2.0)
                    intended_tp_percent = self.sl_tp_orders.get(contract, {}).get('tp_percent', 5.0)
                    direction = 'long' if float(pos['positionAmt']) > 0 else 'short'
                    if direction == 'long':
                        expected_sl_price = entry_price * (1 + intended_sl_percent / 100 / leverage)
                        expected_tp_price = entry_price * (1 + intended_tp_percent / 100 / leverage)
                    else:
                        expected_sl_price = entry_price * (1 - intended_sl_percent / 100 / leverage)
                        expected_tp_price = entry_price * (1 - intended_tp_percent / 100 / leverage)
                    
                    # Check if fetched prices match expected prices (within a small tolerance)
                    price_tolerance = 0.1  # Allow 0.1 price unit difference
                    sl_match = sl_price is None or abs(sl_price - expected_sl_price) <= price_tolerance
                    tp_match = tp_price is None or abs(tp_price - expected_tp_price) <= price_tolerance
                    
                    # If prices match, use template percentages; otherwise, recalculate
                    if sl_match:
                        sl_percent = intended_sl_percent
                    else:
                        sl_percent = ((sl_price - entry_price) / entry_price * 100 * leverage) if sl_price else intended_sl_percent
                    if tp_match:
                        tp_percent = intended_tp_percent
                    else:
                        tp_percent = ((tp_price - entry_price) / entry_price * 100 * leverage) if tp_price else intended_tp_percent
                    
                    self.sl_tp_orders[contract] = {
                        'sl_order_id': sl_order['orderId'] if sl_order else None,
                        'tp_order_id': tp_order['orderId'] if tp_order else None,
                        'sl_percent': sl_percent,
                        'tp_percent': tp_percent,
                        'sl_price': sl_price,
                        'tp_price': tp_price,
                        'sl_status': 'open' if sl_order else 'none',
                        'tp_status': 'open' if tp_order else 'none',
                        'leverage': leverage
                    }
                    self.log_message(f"Updated SL/TP % for {contract}: sl_percent={self.sl_tp_orders[contract]['sl_percent']}, tp_percent={self.sl_tp_orders[contract]['tp_percent']}")
                elif contract not in self.sl_tp_orders:
                    self.sl_tp_orders[contract] = {
                        'sl_order_id': None,
                        'tp_order_id': None,
                        'sl_percent': -2.0,
                        'tp_percent': 5.0,
                        'sl_price': None,
                        'tp_price': None,
                        'sl_status': 'none',
                        'tp_status': 'none',
                        'leverage': leverage
                    }
            
            self.log_message(f"Fetched {len(open_positions)} open positions from exchange")
            return open_positions
        except Exception as e:
            self.log_message(f"Error fetching open positions: {e}")
            return []

    def calculate_unrealized_pnl(self):
        """Calculate the unrealized profit/loss for all open positions in USDT."""
        try:
            positions = self.get_open_positions()
            if not positions:
                self.log_message("No open positions to calculate unrealized P&L")
                return 0.0

            total_pnl = 0.0
            for pos in positions:
                contract = pos['symbol']
                position_amt = float(pos['positionAmt'])
                entry_price = float(pos['entryPrice'])
                
                # Fetch current market price
                ticker = self.client.futures_symbol_ticker(symbol=contract)
                current_price = float(ticker.get('price', 0))
                if current_price <= 0:
                    self.log_message(f"Invalid current price for {contract}: {current_price}")
                    continue

                # Determine direction
                direction = 'long' if position_amt > 0 else 'short'
                
                # Calculate unrealized P&L
                # For Binance Futures, positionAmt is in the base asset (e.g., BTC for BTCUSDT)
                # Contract multiplier is typically 1 for most USDT-margined futures
                if direction == 'long':
                    pnl = (current_price - entry_price) * abs(position_amt)
                else:
                    pnl = (entry_price - current_price) * abs(position_amt)
                
                total_pnl += pnl
                self.log_message(f"Unrealized P&L for {contract} ({direction}): {pnl:.2f} USDT")

            return total_pnl
        except Exception as e:
            self.log_message(f"Error calculating unrealized P&L: {e}")
            return 0.0

    def calculate_position_size(self, params):
        """Calculate position size based on risk, leverage, and entry price."""
        try:
            risk_percentage = float(params['risk_percentage'])
            leverage = float(params['leverage'])
            entry_price = float(params['price']) if params['price'] != '0' else float(self.client.futures_symbol_ticker(symbol=params['contract'])['price'])
            contract = params['contract']

            max_retries = 2
            for attempt in range(max_retries):
                if entry_price <= 0:
                    self.log_message(f"Invalid entry price for {contract}: {entry_price}. Retrying... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(1)
                    entry_price = float(self.client.futures_symbol_ticker(symbol=params['contract'])['price'])
                else:
                    break
            if entry_price <= 0:
                fallback_prices = {
                    'BTCUSDT': 83000.00,
                    'ETHUSDT': 4000.00,
                    'XRPUSDT': 1.00,
                    # Add more contracts as needed
                }
                fallback_price = fallback_prices.get(contract, 83000.00)
                self.log_message(f"Failed to fetch valid entry price for {contract} after {max_retries} retries. Using fallback price {fallback_price}")
                entry_price = fallback_price

            balance = self.get_account_balance()
            if not balance:
                raise ValueError("Failed to fetch account balance")
            available_balance = float(balance['available'])

            risk_amount = available_balance * risk_percentage
            position_value = risk_amount * leverage
            size = position_value / entry_price

            symbol_info = self.client.futures_exchange_info()['symbols']
            for s in symbol_info:
                if s['symbol'] == contract:
                    quantity_precision = s['quantityPrecision']
                    size = round(size, quantity_precision)
                    break

            if size <= 0:
                raise ValueError(f"Calculated position size is zero or negative: {size}")

            self.log_message(f"Calculated position size: {size} for {contract}")
            return size
        except Exception as e:
            self.log_message(f"Error calculating position size: {e}")
            raise

    def execute_trade(self, params):
        """Execute a trade with given parameters."""
        try:
            contract = params['contract']
            direction = params['direction']
            price = params['price']
            leverage = params['leverage']
            tif = params['tif']

            self.client.futures_change_leverage(symbol=contract, leverage=int(float(leverage)))

            order_type = 'MARKET' if price in ('0', '0.0') else 'LIMIT'
            side = 'BUY' if direction.lower() == 'long' else 'SELL'

            size = self.calculate_position_size(params)
            if size <= 0:
                self.log_message(f"Invalid position size for {contract}: {size}")
                return False

            order_params = {
                'symbol': contract,
                'side': side,
                'type': order_type,
                'quantity': str(size)
            }
            if order_type == 'LIMIT':
                order_params['price'] = str(price)
                order_params['timeInForce'] = tif

            order = self.client.futures_create_order(**order_params)
            self.log_message(f"Order placed successfully: {order}")
            return True
        except Exception as e:
            self.log_message(f"Error executing trade: {e}")
            return False

    def close_position(self, contract, size, price, tif):
        """Close a specific position."""
        try:
            side = 'SELL' if float(size) > 0 else 'BUY'
            order_type = 'MARKET' if price in ('0', '0.0') else 'LIMIT'
            order_params = {
                'symbol': contract,
                'side': side,
                'type': order_type,
                'quantity': str(abs(float(size)))
            }
            if order_type == 'LIMIT':
                order_params['price'] = str(price)
                order_params['timeInForce'] = tif

            order = self.client.futures_create_order(**order_params)
            self.log_message(f"Closed position for {contract}: {order}")
            return True
        except Exception as e:
            self.log_message(f"Error closing position for {contract}: {e}")
            return False

    def close_all_positions(self):
        """Close all open positions."""
        try:
            positions = self.get_open_positions()
            if not positions:
                self.log_message("No open positions to close")
                return True

            success = True
            for position in positions:
                contract = position['symbol']
                size = position['positionAmt']
                if float(size) != 0:
                    if not self.close_position(contract=contract, size=size, price='0', tif='IOC'):
                        success = False
            return success
        except Exception as e:
            self.log_message(f"Error closing all positions: {e}")
            return False

    def place_stop_loss_take_profit(self, contract, entry_price, size, direction, sl_percent, tp_percent, leverage):
        """Place stop loss and take profit orders."""
        try:
            # Get the actual position size from position info
            positions = self.client.futures_position_information(symbol=contract)
            position = next((pos for pos in positions if float(pos['positionAmt']) != 0), None)
            if not position:
                raise ValueError(f"No open position found for {contract}")
            
            actual_size = abs(float(position['positionAmt']))
            if actual_size != abs(size):
                self.log_message(f"Adjusting order size from {abs(size)} to {actual_size} to match position")
                size = actual_size

            # Ensure we have a valid entry price
            max_retries = 3
            for attempt in range(max_retries):
                if entry_price <= 0:
                    self.log_message(f"Invalid entry price ({entry_price}), fetching current price... (Attempt {attempt + 1}/{max_retries})")
                    try:
                        entry_price = float(self.client.futures_symbol_ticker(symbol=contract)['price'])
                        time.sleep(0.5)  # Small delay between retries
                    except Exception as e:
                        self.log_message(f"Error fetching price: {e}")
                else:
                    break
            
            if entry_price <= 0:
                raise ValueError(f"Could not get valid entry price after {max_retries} attempts")

            # Store SL/TP values for this contract
            if not hasattr(self, 'sl_tp_orders'):
                self.sl_tp_orders = {}
            self.sl_tp_orders[contract] = {
                'stop_loss': sl_percent,
                'take_profit': tp_percent,
                'leverage': leverage
            }

            # Calculate SL/TP prices
            if direction == 'long':
                # For long positions:
                # SL is below entry price (negative percentage)
                # TP is above entry price (positive percentage)
                sl_price = entry_price * (1 + (sl_percent / 100))  # sl_percent is negative
                tp_price = entry_price * (1 + (tp_percent / 100))  # tp_percent is positive
            else:
                # For short positions:
                # SL is above entry price (negative percentage)
                # TP is below entry price (positive percentage)
                sl_price = entry_price * (1 - (sl_percent / 100))  # sl_percent is negative
                tp_price = entry_price * (1 - (tp_percent / 100))  # tp_percent is positive

            # Round prices to appropriate precision
            symbol_info = self.client.futures_exchange_info()['symbols']
            price_precision = 2  # default precision
            quantity_precision = 3  # default precision
            for s in symbol_info:
                if s['symbol'] == contract:
                    price_precision = s['pricePrecision']
                    quantity_precision = s['quantityPrecision']
                    break
            
            sl_price = round(sl_price, price_precision)
            tp_price = round(tp_price, price_precision)
            size = round(size, quantity_precision)

            # Log the calculations
            self.log_message(f"Calculated values for {contract}:")
            self.log_message(f"Entry: {entry_price}, Size: {size}")
            self.log_message(f"SL: {sl_price} ({sl_percent}%), TP: {tp_price} ({tp_percent}%)")

            # Cancel any existing SL/TP orders
            open_orders = self.client.futures_get_open_orders(symbol=contract)
            for order in open_orders:
                if order['type'] in ['STOP_MARKET', 'TAKE_PROFIT_MARKET']:
                    self.client.futures_cancel_order(
                        symbol=contract,
                        orderId=order['orderId']
                    )

            # Place stop loss order
            sl_order = self.client.futures_create_order(
                symbol=contract,
                side='SELL' if direction == 'long' else 'BUY',
                type='STOP_MARKET',
                quantity=size,
                stopPrice=sl_price,
                reduceOnly=True
            )

            # Place take profit order
            tp_order = self.client.futures_create_order(
                symbol=contract,
                side='SELL' if direction == 'long' else 'BUY',
                type='TAKE_PROFIT_MARKET',
                quantity=size,
                stopPrice=tp_price,
                reduceOnly=True
            )

            self.log_message(f"Successfully placed SL/TP orders for {contract}:")
            self.log_message(f"SL order: {sl_order['orderId']}, price: {sl_price}, size: {size}")
            self.log_message(f"TP order: {tp_order['orderId']}, price: {tp_price}, size: {size}")
            return True
        except Exception as e:
            self.log_message(f"Error placing SL/TP orders: {e}")
            # Clean up stored values on error
            if hasattr(self, 'sl_tp_orders') and contract in self.sl_tp_orders:
                del self.sl_tp_orders[contract]
            return False

    def cleanup(self):
        """Clean up before shutdown by closing positions and canceling open orders."""
        self.log_message("Cleaning up before shutdown...")
        try:
            self.close_all_positions()
            orders = self.client.futures_get_open_orders()
            for order in orders:
                self.client.futures_cancel_order(symbol=order['symbol'], orderId=order['orderId'])
                self.log_message(f"Canceled order {order['orderId']} for {order['symbol']}")
        except Exception as e:
            self.log_message(f"Error during cleanup: {e}")

    def calculate_rsi(self, klines, period=5):
        """Calculate RSI for given klines data."""
        try:
            closes = [float(k[4]) for k in klines]  # Close prices
            deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
            
            gains = []
            losses = []
            for delta in deltas:
                if delta > 0:
                    gains.append(delta)
                    losses.append(0)
                else:
                    gains.append(0)
                    losses.append(abs(delta))
            
            avg_gain = sum(gains[-period:]) / period
            avg_loss = sum(losses[-period:]) / period
            
            if avg_loss == 0:
                return 100
            
            rs = avg_gain / avg_loss
            rsi = 100 - (100 / (1 + rs))
            
            return rsi
        except Exception as e:
            self.log_message(f"Error calculating RSI: {e}")
            return None

    def get_coinglass_flow_data(self):
        """Get flow data from Coinglass API or local file."""
        try:
            # For now, we'll use a placeholder implementation
            # In production, this should be connected to your Coinglass data source
            return {
                '5m': 0,  # 5-minute netflow
                '1h': 0   # 1-hour netflow
            }
        except Exception as e:
            self.log_message(f"Error fetching Coinglass flow data: {e}")
            return None

    def check_strategy_conditions(self, contract="BTCUSDT"):
        """Check if strategy conditions are met for trading."""
        try:
            # Strategy parameters
            rsi_period = 5
            rsi_oversold = 40
            rsi_overbought = 60
            flow_threshold_5m = 100000
            flow_threshold_1h = 500000
            
            # Get recent klines for RSI calculation
            klines = self.client.futures_klines(
                symbol=contract,
                interval='5m',
                limit=rsi_period + 1
            )
            
            if not klines or len(klines) < rsi_period + 1:
                self.log_message("Not enough klines data for RSI calculation")
                return None
            
            # Calculate RSI
            rsi = self.calculate_rsi(klines, rsi_period)
            if rsi is None:
                return None
            
            # Get flow data
            flow_data = self.get_coinglass_flow_data()
            if flow_data is None:
                return None
            
            flow_5m = flow_data['5m']
            flow_1h = flow_data['1h']
            
            # Check conditions
            rsi_long = rsi < rsi_oversold
            flow_long = (flow_5m < -flow_threshold_5m or flow_1h < -flow_threshold_1h)
            long_conditions = rsi_long or flow_long
            
            rsi_short = rsi > rsi_overbought
            flow_short = (flow_5m > flow_threshold_5m or flow_1h > flow_threshold_1h)
            short_conditions = rsi_short or flow_short
            
            # Log conditions
            self.log_message(f"\nStrategy Check for {contract}:")
            self.log_message(f"RSI(5): {rsi:.1f}")
            self.log_message(f"5m Flow: {flow_5m:,.0f}")
            self.log_message(f"1h Flow: {flow_1h:,.0f}")
            
            if long_conditions:
                return {
                    'signal': 'long',
                    'trigger': 'RSI' if rsi_long else 'Flow',
                    'rsi': rsi,
                    'flow_5m': flow_5m,
                    'flow_1h': flow_1h
                }
            elif short_conditions:
                return {
                    'signal': 'short',
                    'trigger': 'RSI' if rsi_short else 'Flow',
                    'rsi': rsi,
                    'flow_5m': flow_5m,
                    'flow_1h': flow_1h
                }
            
            return None
            
        except Exception as e:
            self.log_message(f"Error checking strategy conditions: {e}")
            return None

    def execute_strategy(self, contract="BTCUSDT"):
        """Execute the trading strategy."""
        try:
            # Check if we already have an open position
            positions = self.get_open_positions()
            has_position = any(pos['symbol'] == contract and float(pos['positionAmt']) != 0 for pos in positions)
            
            if has_position:
                self.log_message(f"Already have an open position for {contract}")
                return False
            
            # Check strategy conditions
            signal = self.check_strategy_conditions(contract)
            if not signal:
                return False
            
            # Strategy parameters
            params = {
                'contract': contract,
                'direction': signal['signal'],
                'price': '0',  # Use market price
                'leverage': '25',  # 25x leverage
                'risk_percentage': 0.20,  # 20% risk per trade
                'tif': 'GTC'
            }
            
            # Execute the trade
            success = self.execute_trade(params)
            if not success:
                return False
            
            # Get the entry price from the position
            positions = self.get_open_positions()
            position = next((pos for pos in positions if pos['symbol'] == contract), None)
            if not position:
                self.log_message(f"Failed to get position info for {contract}")
                return False
            
            entry_price = float(position['entryPrice'])
            position_size = float(position['positionAmt'])
            
            # Place stop loss and take profit orders
            sl_percent = -5.0  # 5% stop loss
            tp_percent = 5.0   # 5% take profit
            self.place_stop_loss_take_profit(
                contract=contract,
                entry_price=entry_price,
                size=abs(position_size),
                direction=signal['signal'],
                sl_percent=sl_percent,
                tp_percent=tp_percent,
                leverage=25
            )
            
            self.log_message(f"\nTrade executed for {contract}:")
            self.log_message(f"Direction: {signal['signal'].upper()}")
            self.log_message(f"Trigger: {signal['trigger']}")
            self.log_message(f"Entry Price: {entry_price}")
            self.log_message(f"Position Size: {position_size}")
            self.log_message(f"Stop Loss: {sl_percent}%")
            self.log_message(f"Take Profit: {tp_percent}%")
            
            return True
            
        except Exception as e:
            self.log_message(f"Error executing strategy: {e}")
            return False