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
            max_retries = 5
            for attempt in range(max_retries):
                if entry_price <= 0:
                    self.log_message(f"Invalid entry_price for {contract}: {entry_price}. Retrying... (Attempt {attempt + 1}/{max_retries})")
                    time.sleep(1)
                    entry_price = float(self.client.futures_symbol_ticker(symbol=contract)['price'])
                else:
                    break
            if entry_price <= 0:
                fallback_prices = {
                    'BTCUSDT': 83000.00,
                    'ETHUSDT': 4000.00,
                    'XRPUSDT': 1.00,
                }
                fallback_price = fallback_prices.get(contract, 83000.00)
                self.log_message(f"Failed to fetch valid entry_price for {contract} after {max_retries} retries. Using fallback price {fallback_price}")
                entry_price = fallback_price

            if size <= 0:
                self.log_message(f"Invalid size for {contract}: {size}")
                return False

            # Adjust SL/TP prices for leverage (sl_percent and tp_percent are margin percentages)
            if direction.lower() == 'long':
                sl_price = entry_price * (1 + sl_percent / 100 / leverage)
                tp_price = entry_price * (1 + tp_percent / 100 / leverage)
            else:
                sl_price = entry_price * (1 - sl_percent / 100 / leverage)
                tp_price = entry_price * (1 - tp_percent / 100 / leverage)

            symbol_info = self.client.futures_exchange_info()['symbols']
            for s in symbol_info:
                if s['symbol'] == contract:
                    price_filter = next(filter(lambda x: x['filterType'] == 'PRICE_FILTER', s['filters']), None)
                    if price_filter:
                        min_price = float(price_filter['minPrice'])
                        max_price = float(price_filter['maxPrice'])
                        if sl_price < min_price or sl_price > max_price:
                            raise ValueError(f"Stop Loss price {sl_price} is out of range for {contract} ({min_price}-{max_price})")
                        if tp_price < min_price or tp_price > max_price:
                            raise ValueError(f"Take Profit price {tp_price} is out of range for {contract} ({min_price}-{max_price})")
                    break

            price_precision = 1
            try:
                for s in symbol_info:
                    if s['symbol'] == contract:
                        price_precision = s['pricePrecision']
                        break
                self.log_message(f"Price precision for {contract}: {price_precision}")
            except Exception as e:
                self.log_message(f"Error fetching price precision for {contract}: {e}, using default precision 2")

            sl_price = round(sl_price, price_precision)
            tp_price = round(tp_price, price_precision)
            self.log_message(f"Rounded SL/TP for {contract}: sl_price={sl_price}, tp_price={tp_price}")

            # Place SL order
            sl_order = self.client.futures_create_order(
                symbol=contract,
                side='SELL' if direction.lower() == 'long' else 'BUY',
                type='STOP_MARKET',
                stopPrice=str(sl_price),
                closePosition=True,
                quantity=str(abs(size))
            )
            sl_order_id = sl_order['orderId']
            self.log_message(f"Placed Stop Loss for {contract} at {sl_price:.2f} with orderId {sl_order_id}")

            # Place TP order
            tp_order = self.client.futures_create_order(
                symbol=contract,
                side='SELL' if direction.lower() == 'long' else 'BUY',
                type='TAKE_PROFIT_MARKET',
                stopPrice=str(tp_price),
                closePosition=True,
                quantity=str(abs(size))
            )
            tp_order_id = tp_order['orderId']
            self.log_message(f"Placed Take Profit for {contract} at {tp_price:.2f} with orderId {tp_order_id}")

            self.sl_tp_orders[contract] = {
                'sl_order_id': sl_order_id,
                'tp_order_id': tp_order_id,
                'sl_percent': sl_percent,
                'tp_percent': tp_percent,
                'sl_price': sl_price,
                'tp_price': tp_price,
                'sl_status': 'open',
                'tp_status': 'open',
                'leverage': leverage  # Ensure leverage is stored
            }
            self.log_message(f"Placed SL/TP for {contract}. Monitoring status...")
            return True
        except Exception as e:
            self.log_message(f"Error placing SL/TP for {contract}: {e}")
            self.sl_tp_orders[contract] = {
                'sl_order_id': None,
                'tp_order_id': None,
                'sl_percent': sl_percent,
                'tp_percent': tp_percent,
                'sl_price': None,
                'tp_price': None,
                'sl_status': 'error',
                'tp_status': 'error',
                'leverage': leverage
            }
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