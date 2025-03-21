# gui.py
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, simpledialog
from datetime import datetime, timedelta
import json
import os
import pandas as pd
import time

class TradingGUI:
    def __init__(self, root, trader):
        self.root = root
        self.trader = trader
        self.root.title("Binance Futures Trading")
        self.root.geometry("1000x800")  # Keeping as 1000x800 per your preference

        # Add update flags
        self.is_updating_price = False
        self.is_updating_positions = False
        self.last_price_update = 0
        self.last_position_update = 0
        self.update_interval = 2000  # 2 seconds
        self.position_update_interval = 5000  # 5 seconds
        
        # Create main container frame
        self.main_container = ttk.Frame(self.root)
        self.main_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Initialize log frame first
        self.create_log_frame()

        # Get the script's directory
        self.script_dir = os.path.dirname(os.path.abspath(__file__))
        self.strategy_file = os.path.join(self.script_dir, "strategies.json")
        self.trade_configs = self.load_trade_configs()
        self.current_trade_params = {}

        # Initialize previous values for signal calculation
        self.prev_ma7 = None
        self.prev_ma25 = None
        self.prev_price = None
        self.prev_signal = None  # Track previous signal to prevent duplicates
        self.prev_signal_time = None  # Track when the last signal was generated
        # Initialize signal history
        self.signal_history = []  # List to store (timestamp, signal) tuples
        
        # Initialize Coinglass data with absolute path
        self.coinglass_data = None
        self.last_coinglass_update = None
        self.coinglass_file = os.path.abspath(os.path.join(self.script_dir, "..", "btc_spot_netflow.csv"))

        # Create other frames
        self.create_trade_frame()
        self.create_positions_frame()

        if self.trade_configs:
            first_trade = list(self.trade_configs.keys())[0]
            self.trade_var.set(first_trade)
            self.load_trade_template()

        self.update_positions_and_price()

    def load_trade_configs(self):
        try:
            if os.path.exists(self.strategy_file):
                with open(self.strategy_file, 'r') as f:
                    configs = json.load(f)
                if not configs:
                    raise ValueError("Empty configuration file")
                return configs
            else:
                self.log_message(f"Warning: {self.strategy_file} not found. Using default templates.")
                return {
                    'long_btc_3x': {
                        'contract': 'BTCUSDT',
                        'direction': 'long',
                        'price': '0',
                        'tif': 'IOC',
                        'leverage': '3',
                        'risk_percentage': 0.015,
                        'stop_loss': -2.0,
                        'take_profit': 5.0
                    }
                }
        except Exception as e:
            self.log_message(f"Error loading trade configs: {e}")
            return {
                'long_btc_3x': {
                    'contract': 'BTCUSDT',
                    'direction': 'long',
                    'price': '0',
                    'tif': 'IOC',
                    'leverage': '3',
                    'risk_percentage': 0.015,
                    'stop_loss': -2.0,
                    'take_profit': 5.0
                }
            }

    def save_trade_template(self):
        trade_name = self.trade_var.get()
        if not trade_name:
            self.log_message("No trade selected to save")
            return

        params = {
            'contract': self.contract_var.get(),
            'direction': self.direction_var.get(),
            'price': self.price_var.get(),
            'tif': self.tif_var.get(),
            'leverage': float(self.leverage_var.get()),
            'risk_percentage': float(self.risk_var.get()),
            'stop_loss': float(self.sl_var.get()),
            'take_profit': float(self.tp_var.get())
        }

        try:
            # Load existing strategies
            import json
            try:
                with open(self.strategy_file, 'r') as f:
                    strategies = json.load(f)
            except FileNotFoundError:
                strategies = {}

            # Update or add the trade template
            strategies[trade_name] = params
            with open(self.strategy_file, 'w') as f:
                json.dump(strategies, f, indent=4)

            self.trade_configs = strategies
            self.log_message(f"Saved trade template: {trade_name}")
        except Exception as e:
            self.log_message(f"Error saving trade template {trade_name}: {e}")

    def create_trade_frame(self):
        """Create the main trading interface frame."""
        # Create frames
        trade_frame = ttk.LabelFrame(self.main_container, text="Trading Interface", padding="5 5 5 5")
        trade_frame.pack(fill=tk.BOTH, padx=5, pady=5)

        # Left frame for trade parameters
        left_frame = ttk.Frame(trade_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=5)

        # Right frame for market data and signals
        right_frame = ttk.Frame(trade_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5)

        # Trade template selection
        template_frame = ttk.Frame(left_frame)
        template_frame.pack(fill=tk.X, pady=5)
        ttk.Label(template_frame, text="Trade Template:").pack(side=tk.LEFT)
        self.trade_var = tk.StringVar()
        trade_menu = ttk.Combobox(template_frame, textvariable=self.trade_var, values=list(self.trade_configs.keys()))
        trade_menu.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        trade_menu.bind('<<ComboboxSelected>>', self.load_trade_template)

        # Contract selection
        contract_frame = ttk.Frame(left_frame)
        contract_frame.pack(fill=tk.X, pady=5)
        ttk.Label(contract_frame, text="Contract:").pack(side=tk.LEFT)
        self.contract_var = tk.StringVar(value="BTCUSDT")
        contract_entry = ttk.Entry(contract_frame, textvariable=self.contract_var)
        contract_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # Direction selection
        direction_frame = ttk.Frame(left_frame)
        direction_frame.pack(fill=tk.X, pady=5)
        ttk.Label(direction_frame, text="Direction:").pack(side=tk.LEFT)
        self.direction_var = tk.StringVar(value="long")
        ttk.Radiobutton(direction_frame, text="Long", variable=self.direction_var, value="long").pack(side=tk.LEFT)
        ttk.Radiobutton(direction_frame, text="Short", variable=self.direction_var, value="short").pack(side=tk.LEFT)

        # Price entry
        price_frame = ttk.Frame(left_frame)
        price_frame.pack(fill=tk.X, pady=5)
        ttk.Label(price_frame, text="Price:").pack(side=tk.LEFT)
        self.price_var = tk.StringVar(value="0")
        price_entry = ttk.Entry(price_frame, textvariable=self.price_var)
        price_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # Time in force selection
        tif_frame = ttk.Frame(left_frame)
        tif_frame.pack(fill=tk.X, pady=5)
        ttk.Label(tif_frame, text="TIF:").pack(side=tk.LEFT)
        self.tif_var = tk.StringVar(value="IOC")
        tif_menu = ttk.Combobox(tif_frame, textvariable=self.tif_var, values=["GTC", "IOC", "FOK"])
        tif_menu.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # Leverage entry
        leverage_frame = ttk.Frame(left_frame)
        leverage_frame.pack(fill=tk.X, pady=5)
        ttk.Label(leverage_frame, text="Leverage:").pack(side=tk.LEFT)
        self.leverage_var = tk.StringVar(value="3")
        leverage_entry = ttk.Entry(leverage_frame, textvariable=self.leverage_var)
        leverage_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # Risk percentage entry
        risk_frame = ttk.Frame(left_frame)
        risk_frame.pack(fill=tk.X, pady=5)
        ttk.Label(risk_frame, text="Risk %:").pack(side=tk.LEFT)
        self.risk_var = tk.StringVar(value="1.5")
        risk_entry = ttk.Entry(risk_frame, textvariable=self.risk_var)
        risk_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # Stop loss entry
        sl_frame = ttk.Frame(left_frame)
        sl_frame.pack(fill=tk.X, pady=5)
        ttk.Label(sl_frame, text="Stop Loss %:").pack(side=tk.LEFT)
        self.sl_var = tk.StringVar(value="-2.0")
        sl_entry = ttk.Entry(sl_frame, textvariable=self.sl_var)
        sl_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # Take profit entry
        tp_frame = ttk.Frame(left_frame)
        tp_frame.pack(fill=tk.X, pady=5)
        ttk.Label(tp_frame, text="Take Profit %:").pack(side=tk.LEFT)
        self.tp_var = tk.StringVar(value="5.0")
        tp_entry = ttk.Entry(tp_frame, textvariable=self.tp_var)
        tp_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # Market Data Display (more compact)
        market_frame = ttk.LabelFrame(right_frame, text="Market Data", padding="2 2 2 2")
        market_frame.pack(fill=tk.X, pady=1)

        # Price and MA in same row
        price_ma_frame = ttk.Frame(market_frame)
        price_ma_frame.pack(fill=tk.X)
        
        self.price_label = ttk.Label(price_ma_frame, text="Price: 0.00", font=('TkDefaultFont', 11, 'bold'))
        self.price_label.pack(side=tk.LEFT, padx=2)
        
        self.ma7_label = ttk.Label(price_ma_frame, text="MA7: 0.00")
        self.ma7_label.pack(side=tk.LEFT, padx=2)
        self.ma25_label = ttk.Label(price_ma_frame, text="MA25: 0.00")
        self.ma25_label.pack(side=tk.LEFT, padx=2)

        # Exchange Flow Data Frame
        coinglass_frame = ttk.LabelFrame(right_frame, text="Exchange Flow Data", padding="2 2 2 2")
        coinglass_frame.pack(fill=tk.X, pady=1)
        
        # Last update time
        self.exchange_flow_time_var = tk.StringVar(value="Last Update: N/A")
        time_label = ttk.Label(coinglass_frame, textvariable=self.exchange_flow_time_var)
        time_label.pack(fill=tk.X, padx=5, pady=2)
        
        # Create frames for different time periods
        short_frame = ttk.Frame(coinglass_frame)
        short_frame.pack(fill=tk.X, padx=5, pady=2)
        
        medium_frame = ttk.Frame(coinglass_frame)
        medium_frame.pack(fill=tk.X, padx=5, pady=2)
        
        long_frame = ttk.Frame(coinglass_frame)
        long_frame.pack(fill=tk.X, padx=5, pady=2)
        
        # Define flow periods and their groupings
        flow_periods = [
            ('5m', 'short'), ('15m', 'short'), ('30m', 'short'), ('1h', 'short'),
            ('2h', 'medium'), ('4h', 'medium'), ('6h', 'medium'), ('8h', 'medium'),
            ('12h', 'long'), ('24h', 'long')
        ]
        
        # Create labels for each period
        for period, frame_type in flow_periods:
            frame = locals()[f"{frame_type}_frame"]
            
            # Create container frame for this period
            period_frame = ttk.Frame(frame)
            period_frame.pack(side=tk.LEFT, padx=2)
            
            # Period label
            ttk.Label(period_frame, text=f"{period}:").pack(side=tk.LEFT)
            
            # Value label with initial value
            value_label = ttk.Label(period_frame, text="0", width=8)
            value_label.pack(side=tk.LEFT, padx=(2, 5))
            
            # Store reference to the value label
            setattr(self, f"flow_{period}_label", value_label)
        
        # Add tooltips
        strategy_info = """Exchange Flow Data shows the net flow of BTC between exchanges:
• Positive values (red) indicate more BTC flowing into exchanges
• Negative values (green) indicate more BTC flowing out of exchanges
• Values are shown in different time periods from 5 minutes to 24 hours"""
        self.create_tooltip(coinglass_frame, strategy_info)

        # Signal Display (more compact)
        signal_frame = ttk.LabelFrame(right_frame, text="Trading Signals", padding="2 2 2 2")
        signal_frame.pack(fill=tk.X, pady=1)
        self.signal_label = ttk.Label(signal_frame, text="Signal: NO SIGNAL", font=('TkDefaultFont', 11, 'bold'))
        self.signal_label.pack(fill=tk.X, pady=1)

        # Signal History (reduced height)
        history_frame = ttk.LabelFrame(right_frame, text="Signal History", padding="2 2 2 2")
        history_frame.pack(fill=tk.X, pady=1)
        self.signal_history_text = scrolledtext.ScrolledText(history_frame, height=4)
        self.signal_history_text.pack(fill=tk.BOTH)

        # Buttons
        button_frame = ttk.Frame(left_frame)
        button_frame.pack(fill=tk.X, pady=2)
        ttk.Button(button_frame, text="Execute Trade", command=self.execute_trade).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Close All", command=self.close_all_positions).pack(side=tk.LEFT, padx=2)
        ttk.Button(button_frame, text="Reset Template", command=self.reset_to_template).pack(side=tk.LEFT, padx=2)

        # Auto Trading Frame (compact with hover)
        auto_frame = ttk.LabelFrame(left_frame, text="Automatic Trading", padding="2 2 2 2")
        auto_frame.pack(fill=tk.X, pady=2)

        # Auto trading controls frame
        auto_controls = ttk.Frame(auto_frame)
        auto_controls.pack(fill=tk.X)

        # Auto trading toggle and status in one row
        self.auto_trading = tk.BooleanVar(value=False)
        self.auto_trading_btn = ttk.Checkbutton(
            auto_controls,
            text="Enable Auto Trading",
            variable=self.auto_trading,
            command=self.toggle_auto_trading
        )
        self.auto_trading_btn.pack(side=tk.LEFT, padx=2)
        
        self.auto_status_label = ttk.Label(auto_controls, text="Disabled", foreground="red")
        self.auto_status_label.pack(side=tk.LEFT, padx=2)

        # Compact strategy display with hover
        strategy_summary = ttk.Label(auto_frame, 
            text="Strategy: MA Cross + RSI + Flow (Hover for details)",
            cursor="question_arrow"
        )
        strategy_summary.pack(fill=tk.X, pady=1)

        # Create tooltip for strategy details
        strategy_details = (
            "Strategy Parameters:\n"
            "• Leverage: 25x\n"
            "• Risk per Trade: 20% of capital\n\n"
            "Long Entry (any of):\n"
            "• RSI(5) < 40\n"
            "• 5m Netflow < -$100K\n"
            "• 1h Netflow < -$500K\n\n"
            "Short Entry (any of):\n"
            "• RSI(5) > 60\n"
            "• 5m Netflow > $100K\n"
            "• 1h Netflow > $500K\n\n"
            "Risk Management:\n"
            "• Stop Loss: -5%\n"
            "• Take Profit: 5%\n"
            "• Timeframe: 5-minute candles"
        )
        
        self.create_tooltip(strategy_summary, strategy_details)

        # Add tooltips for each parameter
        self.create_tooltip(contract_entry, 
            "Trading pair (e.g., BTCUSDT). Currently supporting BTCUSDT only.")
        
        self.create_tooltip(price_entry, 
            "Entry price (0 for market order). The bot uses market orders by default.")
        
        self.create_tooltip(leverage_entry, 
            "Position leverage (25x). Higher leverage means higher risk and potential returns.")
        
        self.create_tooltip(risk_entry, 
            "Risk per trade (20%). Percentage of account balance to risk on each trade.")
        
        self.create_tooltip(sl_entry, 
            "Stop Loss (-5%). Will close position at a loss if price moves against you by this percentage.")
        
        self.create_tooltip(tp_entry, 
            "Take Profit (5%). Will close position at a profit if price moves in your favor by this percentage.")
        
        self.create_tooltip(tif_menu, 
            "Time In Force: GTC (Good Till Cancel) recommended for this strategy.")

        # Add tooltips for market data
        self.create_tooltip(self.price_label, 
            "Current market price of the trading pair")

        # Add RSI tooltip
        self.create_tooltip(self.signal_label,
            "Trading signal based on RSI(5) and exchange flow conditions.\n"
            "RSI < 40 or flow conditions trigger long.\n"
            "RSI > 60 or flow conditions trigger short.")

        # Add strategy explanation tooltip to the trade frame
        strategy_info = """Trading Strategy:
- Entry Conditions:
  * Long: RSI(5) < 40 OR 5m Flow < -$100K OR 1h Flow < -$500K
  * Short: RSI(5) > 60 OR 5m Flow > $100K OR 1h Flow > $500K
- Risk Management:
  * Leverage: 25x
  * Risk per trade: 20% of balance
  * Take Profit: 5%
  * Stop Loss: -5%
- Timeframe: 5-minute candles"""
        
        self.create_tooltip(trade_frame, strategy_info)

        # Schedule periodic updates
        self.schedule_updates()

    def create_tooltip(self, widget, text):
        """Create a tooltip for a given widget."""
        tooltip = tk.Toplevel(widget)
        tooltip.withdraw()
        tooltip.wm_overrideredirect(True)
        
        label = ttk.Label(tooltip, text=text, justify=tk.LEFT,
                         relief=tk.SOLID, borderwidth=1,
                         background="#ffffe0", padding="3 3 3 3")
        label.pack()
        
        def show_tooltip(event=None):
            tooltip.deiconify()
            x = widget.winfo_rootx() + widget.winfo_width()
            y = widget.winfo_rooty()
            tooltip.geometry(f"+{x}+{y}")
        
        def hide_tooltip(event=None):
            tooltip.withdraw()
        
        widget.bind('<Enter>', show_tooltip)
        widget.bind('<Leave>', hide_tooltip)

    def create_positions_frame(self):
        """Create the positions frame with fixed height."""
        positions_frame = ttk.LabelFrame(self.main_container, text="Open Positions & Holdings", padding="5 5 5 5")
        positions_frame.pack(fill=tk.BOTH, padx=5, pady=5)

        # Holdings label
        self.holdings_var = tk.StringVar(value="USDT Balance: Loading...")
        holdings_label = ttk.Label(positions_frame, textvariable=self.holdings_var)
        holdings_label.pack(fill=tk.X, pady=(0, 5))

        # Create positions tree with fixed height
        columns = ('Contract', 'Size', 'Entry Price', 'Leverage', 'SL % (Price)', 'TP % (Price)', 'Edit', 'Action')
        self.positions_tree = ttk.Treeview(positions_frame, columns=columns, show='headings', height=2)
        
        # Configure column widths
        column_widths = {
            'Contract': 100,
            'Size': 100,
            'Entry Price': 100,
            'Leverage': 80,
            'SL % (Price)': 150,
            'TP % (Price)': 150,
            'Edit': 50,
            'Action': 50
        }
        
        for col, width in zip(columns, column_widths.values()):
            self.positions_tree.heading(col, text=col)
            self.positions_tree.column(col, width=width)
        
        self.positions_tree.pack(fill=tk.X, pady=(0, 5))

        # Button frame
        button_frame = ttk.Frame(positions_frame)
        button_frame.pack(fill=tk.X, pady=(0, 5))
        ttk.Button(button_frame, text="Refresh", command=self.update_positions_and_price).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Close All", command=self.close_all_positions).pack(side=tk.LEFT, padx=5)

    def create_log_frame(self):
        """Create the log frame with collapsible functionality."""
        # Initialize log frame state
        self.log_frame_expanded = False
        
        # Create a container frame for the log
        self.log_container = ttk.Frame(self.main_container)
        self.log_container.pack(fill=tk.X, pady=5)

        # Create expand/collapse button
        self.log_toggle_btn = ttk.Button(
            self.log_container, 
            text="▼ Show Log", 
            command=self.toggle_log_frame,
            style='Toolbutton'
        )
        self.log_toggle_btn.pack(fill=tk.X)

        # Create the actual log frame (initially hidden)
        self.log_frame = ttk.LabelFrame(self.log_container, text="Log", padding="5 5 5 5")
        self.log_text = scrolledtext.ScrolledText(self.log_frame, height=8)  # Reduced height
        self.log_text.pack(fill=tk.BOTH, expand=True)
        self.log_text.config(state='disabled')

    def toggle_log_frame(self):
        if self.log_frame_expanded:
            self.log_frame.pack_forget()
            self.log_toggle_btn.config(text="▼ Show Log")
        else:
            self.log_frame.pack(fill="both", expand=True)
            self.log_toggle_btn.config(text="▲ Hide Log")
        self.log_frame_expanded = not self.log_frame_expanded

    def log_message(self, message):
        self.log_text.config(state='normal')
        # Add message to log
        self.log_text.insert(tk.END, f"{datetime.now()}: {message}\n")
        # Keep only last 1000 lines to prevent memory bloat
        num_lines = int(self.log_text.index('end-1c').split('.')[0])
        if num_lines > 1000:
            self.log_text.delete('1.0', f'{num_lines-1000}.0')
        self.log_text.config(state='disabled')
        # Only auto-scroll if log frame is expanded
        if self.log_frame_expanded:
            self.log_text.see(tk.END)

    def load_trade_template(self, event=None):
        selected_trade = self.trade_var.get()
        if selected_trade:
            config = self.trade_configs[selected_trade]
            self.current_trade_params = config.copy()
            self.contract_var.set(config['contract'])
            self.direction_var.set(config['direction'])
            self.price_var.set(config['price'])
            self.tif_var.set(config['tif'])
            self.leverage_var.set(str(config['leverage']))
            self.risk_var.set(str(config['risk_percentage']))
            self.sl_var.set(str(config.get('stop_loss', '-2')))
            self.tp_var.set(str(config.get('take_profit', '5')))
            self.log_message(f"Loaded trade template: {selected_trade} with price: {config['price']}")
            self.update_market_price()

    def reset_to_template(self):
        selected_trade = self.trade_var.get()
        if selected_trade:
            self.load_trade_template()
        else:
            self.log_message("Please select a trade template first")

    def validate_trade_params(self):
        try:
            params = {
                'contract': self.contract_var.get().strip(),
                'direction': self.direction_var.get().strip(),
                'price': self.price_var.get().strip(),
                'tif': self.tif_var.get().strip(),
                'leverage': self.leverage_var.get().strip(),
                'risk_percentage': self.risk_var.get().strip(),
                'stop_loss': float(self.sl_var.get()),
                'take_profit': float(self.tp_var.get())
            }
            self.log_message(f"Raw params before validation: {params}")
            if not params['contract']:
                raise ValueError("Contract cannot be empty")
            if not params['direction']:
                raise ValueError("Direction must be selected")
            if not params['tif']:
                raise ValueError("Time in Force must be selected")
            price = float(params['price'])
            leverage = float(params['leverage'])
            risk_percentage = float(params['risk_percentage'])
            sl = params['stop_loss']
            tp = params['take_profit']
            if price < 0:
                raise ValueError("Price cannot be negative")
            if leverage <= 0:
                raise ValueError("Leverage must be positive")
            if risk_percentage <= 0 or risk_percentage > 1:
                raise ValueError("Risk percentage must be between 0 and 1")
            if sl >= 0 or tp <= 0:
                raise ValueError("Stop Loss must be negative, Take Profit must be positive")
            params['price'] = str(price)
            params['leverage'] = leverage
            params['risk_percentage'] = risk_percentage
            params['stop_loss'] = sl
            params['take_profit'] = tp
            self.log_message(f"Validated params: {params}")
            return params
        except ValueError as e:
            messagebox.showerror("Validation Error", str(e))
            return None
        except Exception as e:
            messagebox.showerror("Error", f"Invalid parameter format: {str(e)}")
            return None

    def load_coinglass_data(self):
        """Load and display Coinglass exchange flow data."""
        try:
            # Get the path to the coinglass data file
            current_dir = os.path.dirname(os.path.abspath(__file__))
            csv_file = os.path.join(current_dir, '..', 'coinglass', 'btc_spot_netflow.csv')
            
            if not os.path.exists(csv_file):
                self.log_message("Warning: Exchange flow data file not found")
                return
                
            # Read the CSV file
            df = pd.read_csv(csv_file)
            if df.empty:
                self.log_message("Warning: Exchange flow data file is empty")
                return
                
            # Sort by timestamp in descending order to get the latest data
            df['Timestamp'] = pd.to_datetime(df['Timestamp'], format='%d %b %Y, %H:%M')
            df = df.sort_values('Timestamp', ascending=False)
            
            # Get the latest row
            latest_row = df.iloc[0]
            
            # Update the labels with the latest data
            timestamp = latest_row['Timestamp'].strftime('%d %b %Y, %H:%M')
            self.exchange_flow_time_var.set(f"Last Update: {timestamp}")
            
            # Update flow labels with proper formatting
            flow_periods = ['5m', '15m', '30m', '1h', '2h', '4h', '6h', '8h', '12h', '24h']
            for period in flow_periods:
                if period in latest_row.index:
                    try:
                        # Convert string to float, handling any potential formatting
                        value_str = str(latest_row[period]).replace(',', '')
                        value = float(value_str)
                        
                        # Format the value based on its magnitude
                        if abs(value) >= 1_000_000:
                            formatted_value = f"{value/1_000_000:.1f}M"
                        elif abs(value) >= 1_000:
                            formatted_value = f"{value/1_000:.1f}K"
                        else:
                            formatted_value = f"{value:.1f}"
                        
                        # Determine color based on value
                        color = "green" if value > 0 else "red" if value < 0 else "gray"
                        
                        # Update the label
                        label_name = f"flow_{period}_label"
                        if hasattr(self, label_name):
                            label = getattr(self, label_name)
                            label.config(text=formatted_value, foreground=color)
                            
                    except (ValueError, KeyError) as e:
                        self.log_message(f"Error parsing {period} value: {e}")
                        continue
            
        except Exception as e:
            self.log_message(f"Error loading exchange flow data: {str(e)}")
            # Schedule retry after a short delay
            self.root.after(5000, self.load_coinglass_data)

    def calculate_rsi(self, closes, periods=14):
        """Calculate RSI using Binance's method."""
        try:
            # Calculate price changes
            delta = closes.diff()
            
            # Separate gains and losses
            gains = delta.where(delta > 0, 0)
            losses = -delta.where(delta < 0, 0)
            
            # First average
            avg_gains = gains.rolling(window=periods).mean()
            avg_losses = losses.rolling(window=periods).mean()
            
            # Calculate RS and RSI
            rs = avg_gains / avg_losses
            rsi = 100 - (100 / (1 + rs))
            
            return rsi
        except Exception as e:
            self.log_message(f"Error calculating RSI: {e}")
            return pd.Series([50] * len(closes))  # Return neutral RSI on error

    def calculate_1h_netflow(self, coinglass_data):
        """Calculate 1-hour netflow from Coinglass data."""
        try:
            # Get the last 12 entries (12 * 5min = 1 hour)
            recent_data = coinglass_data.head(12)
            # Sum the 5-minute netflow values
            total_flow = recent_data['5m'].sum()
            return total_flow
        except Exception as e:
            self.log_message(f"Error calculating 1h netflow: {e}")
            return None

    def generate_signal(self, price, ma7, ma25):
        """Generate trading signals based on MA crossovers, RSI, and exchange flows."""
        try:
            if None in (price, ma7, ma25):
                return "NO SIGNAL"

            # Get klines data for MA and RSI calculations
            contract = self.contract_var.get()
            klines = self.trader.client.futures_klines(
                symbol=contract,
                interval='5m',
                limit=100  # Get more data for accurate calculations
            )
            
            if not klines:
                return "NO SIGNAL"

            # Calculate all required indicators
            closes = pd.Series([float(k[4]) for k in klines])
            current_price = closes.iloc[-1]
            
            # Calculate moving averages
            ma5 = closes.rolling(window=5).mean().iloc[-1]
            ma20 = closes.rolling(window=20).mean().iloc[-1]
            ma50 = closes.rolling(window=50).mean().iloc[-1]
            
            # Calculate RSI
            rsi = self.calculate_rsi(closes).iloc[-1]
            
            # Get Coinglass flow data
            coinglass_data = self.load_coinglass_data()
            if coinglass_data:
                flow_5m = coinglass_data.get('5m', 0)
            else:
                flow_5m = 0

            # Log current indicators
            self.log_message(
                f"Signal Indicators - Price: {current_price:.2f}, MA5: {ma5:.2f}, "
                f"MA20: {ma20:.2f}, MA50: {ma50:.2f}, RSI: {rsi:.1f}, "
                f"Flow 5m: {flow_5m:,.0f}"
            )

            # Long signal conditions (exactly matching auto trading strategy)
            long_conditions = (
                ma5 > ma20 and
                rsi < 20 and
                flow_5m < -500000 and
                current_price > ma50
            )

            # Short signal conditions (exactly matching auto trading strategy)
            short_conditions = (
                ma5 < ma20 and
                rsi > 80 and
                flow_5m > 500000 and
                current_price < ma50
            )

            if long_conditions:
                return "BUY"
            elif short_conditions:
                return "SELL"

            return "NO SIGNAL"

        except Exception as e:
            self.log_message(f"Error generating signal: {e}")
            return "NO SIGNAL"

    def update_positions_and_price(self):
        """Update positions and market price with proper scheduling."""
        try:
            current_time = time.time() * 1000  # Convert to milliseconds
            
            # Prevent concurrent updates
            if not self.is_updating_positions:
                self.is_updating_positions = True
                try:
                    # Check if enough time has passed since last update
                    if current_time - self.last_position_update >= self.position_update_interval:
                        self.update_positions()
                        self.last_position_update = current_time
                finally:
                    self.is_updating_positions = False
            
            if not self.is_updating_price:
                self.is_updating_price = True
                try:
                    # Check if enough time has passed since last update
                    if current_time - self.last_price_update >= self.update_interval:
                        self.update_market_price()
                        self.last_price_update = current_time
                finally:
                    self.is_updating_price = False
                    
        except Exception as e:
            self.log_message(f"Error in update cycle: {str(e)}")
        finally:
            # Schedule next update using a single timer
            self.root.after(1000, self.update_positions_and_price)
    
    def update_positions(self):
        """Update positions with timeout handling."""
        try:
            # Get positions and account info with timeout
            account_info = self.trader.client.futures_account(timeout=5)
            position_info = self.trader.client.futures_position_information(timeout=5)
            open_orders = self.trader.client.futures_get_open_orders(timeout=5)
            
            # Clear existing items
            for item in self.positions_tree.get_children():
                self.positions_tree.delete(item)
            
            # Update balance display
            if account_info:
                total_wallet_balance = float(account_info.get('totalWalletBalance', 0))
                total_unrealized_profit = float(account_info.get('totalUnrealizedProfit', 0))
                available_balance = float(account_info.get('availableBalance', 0))
                balance_text = f"USDT Balance: {total_wallet_balance:.2f} (Available: {available_balance:.2f}) | Unrealized P&L: {total_unrealized_profit:.2f}"
                self.holdings_var.set(balance_text)
            
            # Update positions
            for position in position_info:
                pos_amt = float(position.get('positionAmt', 0))
                if abs(pos_amt) > 0:  # Only show non-zero positions
                    symbol = position['symbol']
                    entry_price = float(position.get('entryPrice', 0))
                    mark_price = float(position.get('markPrice', 0))
                    leverage = int(float(position.get('leverage', 10)))
                    
                    # Find SL/TP orders for this position
                    sl_order = next((order for order in open_orders 
                                   if order['symbol'] == symbol 
                                   and order['type'] == 'STOP_MARKET'), None)
                    tp_order = next((order for order in open_orders 
                                   if order['symbol'] == symbol 
                                   and order['type'] == 'TAKE_PROFIT_MARKET'), None)
                    
                    # Get SL/TP prices and calculate percentages
                    sl_price = float(sl_order['stopPrice']) if sl_order else None
                    tp_price = float(tp_order['stopPrice']) if tp_order else None
                    
                    # Determine position direction
                    direction = 'long' if pos_amt > 0 else 'short'
                    
                    # Calculate SL/TP percentages
                    if direction == 'long':
                        sl_percent = ((sl_price - entry_price) / entry_price * 100) if sl_price else None
                        tp_percent = ((tp_price - entry_price) / entry_price * 100) if tp_price else None
                    else:  # short
                        sl_percent = ((entry_price - sl_price) / entry_price * 100) if sl_price else None
                        tp_percent = ((entry_price - tp_price) / entry_price * 100) if tp_price else None
                    
                    # Get stored SL/TP values if available
                    stored_values = self.trader.sl_tp_orders.get(symbol, {})
                    if stored_values:
                        if sl_percent is None:
                            sl_percent = stored_values.get('stop_loss', -2.0)
                        if tp_percent is None:
                            tp_percent = stored_values.get('take_profit', 5.0)
                    
                    # Format display strings
                    sl_display = f"{sl_percent:.1f}% ({sl_price:.2f})" if sl_price else f"{sl_percent:.1f}% (Not set)" if sl_percent else "Not set"
                    tp_display = f"{tp_percent:.1f}% ({tp_price:.2f})" if tp_price else f"{tp_percent:.1f}% (Not set)" if tp_percent else "Not set"
                    
                    # Insert position into tree
                    self.positions_tree.insert('', 'end', values=(
                        symbol,
                        f"{pos_amt:.4f}",
                        f"{entry_price:.2f}",
                        f"{leverage}x",
                        sl_display,
                        tp_display,
                        "Edit",
                        "Close"
                    ))
                    
            # Bind click events for Edit and Close buttons
            self.positions_tree.bind('<ButtonRelease-1>', self.handle_position_click)
                    
        except Exception as e:
            self.log_message(f"Error updating positions: {str(e)}")
            # Schedule retry after a short delay
            self.root.after(5000, self.update_positions)

    def handle_position_click(self, event):
        """Handle clicks on the positions tree."""
        try:
            item = self.positions_tree.identify_row(event.y)
            column = self.positions_tree.identify_column(event.x)
            
            if not item:
                return
                
            values = self.positions_tree.item(item)['values']
            if not values:
                return
                
            symbol = values[0]
            pos_amt = float(values[1])
            entry_price = float(values[2].replace('x', ''))  # Remove 'x' from leverage
            
            # Handle Edit button click (column #7)
            if column == '#7':  # Edit column
                self.edit_position_sl_tp(symbol, pos_amt, entry_price)
            
            # Handle Close button click (column #8)
            elif column == '#8':  # Close column
                self.close_single_position(symbol, pos_amt)
                
        except Exception as e:
            self.log_message(f"Error handling position click: {str(e)}")

    def edit_position_sl_tp(self, symbol, pos_amt, entry_price):
        """Edit SL/TP for a position."""
        try:
            # Get current SL/TP values
            open_orders = self.trader.client.futures_get_open_orders(symbol=symbol)
            sl_order = next((order for order in open_orders if order['type'] == 'STOP_MARKET'), None)
            tp_order = next((order for order in open_orders if order['type'] == 'TAKE_PROFIT_MARKET'), None)
            
            current_sl_percent = 0
            current_tp_percent = 0
            
            if sl_order:
                sl_price = float(sl_order['stopPrice'])
                current_sl_percent = ((sl_price - entry_price) / entry_price * 100)
                if pos_amt < 0:  # Short position
                    current_sl_percent = -current_sl_percent
                    
            if tp_order:
                tp_price = float(tp_order['stopPrice'])
                current_tp_percent = ((tp_price - entry_price) / entry_price * 100)
                if pos_amt < 0:  # Short position
                    current_tp_percent = -current_tp_percent
            
            # Ask for new values
            new_sl = simpledialog.askfloat("Edit Stop Loss", 
                                         f"Enter new Stop Loss % for {symbol}\nCurrent: {current_sl_percent:.1f}%",
                                         initialvalue=current_sl_percent)
            if new_sl is None:
                return
                
            new_tp = simpledialog.askfloat("Edit Take Profit", 
                                         f"Enter new Take Profit % for {symbol}\nCurrent: {current_tp_percent:.1f}%",
                                         initialvalue=current_tp_percent)
            if new_tp is None:
                return
            
            # Cancel existing SL/TP orders
            if sl_order:
                self.trader.client.futures_cancel_order(symbol=symbol, orderId=sl_order['orderId'])
            if tp_order:
                self.trader.client.futures_cancel_order(symbol=symbol, orderId=tp_order['orderId'])
            
            # Place new SL/TP orders
            direction = 'long' if pos_amt > 0 else 'short'
            leverage = float(self.trader.client.futures_position_information(symbol=symbol)[0]['leverage'])
            
            success = self.trader.place_stop_loss_take_profit(
                symbol, entry_price, pos_amt, direction, new_sl, new_tp, leverage
            )
            
            if success:
                self.log_message(f"Successfully updated SL/TP for {symbol} to SL={new_sl:.1f}%, TP={new_tp:.1f}%")
            else:
                self.log_message(f"Failed to update SL/TP for {symbol}")
                
        except Exception as e:
            self.log_message(f"Error editing position SL/TP: {str(e)}")
        finally:
            self.update_positions_and_price()

    def close_single_position(self, symbol, size):
        """Close a single position."""
        try:
            self.log_message(f"Closing position: {symbol}, Size: {size}")
            
            # First cancel any existing SL/TP orders
            try:
                open_orders = self.trader.client.futures_get_open_orders(symbol=symbol)
                for order in open_orders:
                    if order['type'] in ['STOP_MARKET', 'TAKE_PROFIT_MARKET']:
                        self.trader.client.futures_cancel_order(
                            symbol=symbol,
                            orderId=order['orderId']
                        )
                        self.log_message(f"Cancelled {order['type']} order for {symbol}")
            except Exception as e:
                self.log_message(f"Error cancelling SL/TP orders: {str(e)}")
            
            # Then close the position
            success = self.trader.close_position(contract=symbol, size=size, price='0', tif='IOC')
            
            if success:
                self.log_message(f"Successfully closed position: {symbol}")
                # Remove the symbol from sl_tp_orders if it exists
                if hasattr(self.trader, 'sl_tp_orders') and symbol in self.trader.sl_tp_orders:
                    del self.trader.sl_tp_orders[symbol]
            else:
                self.log_message(f"Failed to close position: {symbol}")
                
        except Exception as e:
            self.log_message(f"Error closing position: {str(e)}")
        finally:
            self.update_positions_and_price()

    def update_market_price(self):
        """Update market price and indicators with timeout handling."""
        try:
            # Get the selected contract
            contract = self.contract_var.get()
            if not contract:
                return
            
            # Fetch klines data with timeout
            klines = self.trader.client.futures_klines(
                symbol=contract,
                interval='5m',
                limit=100,
                timeout=5
            )
            
            if not klines:
                return

            # Calculate indicators
            closes = pd.Series([float(k[4]) for k in klines])
            current_price = closes.iloc[-1]
            ma7 = closes.rolling(window=7).mean().iloc[-1]
            ma25 = closes.rolling(window=25).mean().iloc[-1]
            
            # Calculate RSI
            rsi = self.calculate_rsi(closes, periods=14)
            current_rsi = rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50

            # Store previous values for signal calculation
            self.prev_ma7 = closes.rolling(window=7).mean().iloc[-2]
            self.prev_ma25 = closes.rolling(window=25).mean().iloc[-2]
            self.prev_price = closes.iloc[-2]

            # Generate signal
            signal = self.generate_signal(current_price, ma7, ma25)
            
            # Update GUI elements in a single batch
            def update_gui():
                self.price_label.config(text=f"Price: {current_price:,.2f}")
                self.ma7_label.config(text=f"MA7: {ma7:.2f}")
                self.ma25_label.config(text=f"MA25: {ma25:.2f}")
                self.signal_label.config(
                    text=f"Signal: {signal} (RSI: {current_rsi:.1f})",
                    foreground=self.get_signal_color(signal)
                )
                self.update_signal_history(signal, current_rsi)
                
                # Load and update Coinglass data
                self.load_coinglass_data()
            
            # Schedule GUI updates to run in the main thread
            self.root.after_idle(update_gui)
            
        except Exception as e:
            self.log_message(f"Error updating market price: {str(e)}")

    def update_signal_history(self, signal, current_rsi):
        """Update signal history without blocking the GUI."""
        try:
            current_time = datetime.now()
            
            # Update signal history if it's a new signal
            if signal != "NO SIGNAL":
                if (signal != self.prev_signal or 
                    self.prev_signal_time is None or 
                    (current_time - self.prev_signal_time).total_seconds() >= 300):
                    
                    self.signal_history.append((current_time, signal))
                    if len(self.signal_history) > 100:
                        self.signal_history.pop(0)
                    
                    self.prev_signal = signal
                    self.prev_signal_time = current_time
            
            # Update signal history display
            def update_history_display():
                self.signal_history_text.config(state='normal')
                self.signal_history_text.delete(1.0, tk.END)
                for ts, sig in reversed(self.signal_history[-10:]):
                    self.signal_history_text.insert(tk.END, f"{ts.strftime('%H:%M:%S')}: {sig}\n")
                self.signal_history_text.config(state='disabled')
            
            # Schedule history display update to run in the main thread
            self.root.after_idle(update_history_display)
            
        except Exception as e:
            self.log_message(f"Error updating signal history: {str(e)}")

    def get_signal_color(self, signal):
        """Return color for signal display."""
        colors = {
            "STRONG BUY": "dark green",
            "BUY": "green",
            "NO SIGNAL": "black",
            "SELL": "red",
            "STRONG SELL": "dark red"
        }
        return colors.get(signal, "black")

    def execute_trade(self):
        self.log_message("Starting trade execution...")
        params = self.validate_trade_params()
        if not params:
            self.log_message("Trade validation failed")
            return

        # Use the SL/TP values from the interface
        params['stop_loss'] = float(self.sl_var.get())
        params['take_profit'] = float(self.tp_var.get())
        
        self.log_message(f"Executing trade with TP={params['take_profit']}%, SL={params['stop_loss']}%")
        success = self.trader.execute_trade(params)
        
        if success:
            contract = params['contract']
            direction = params['direction']
            size = self.trader.calculate_position_size(params)
            
            if size <= 0:
                self.log_message(f"Invalid position size: {size}")
                return

            # Get the actual entry price from the position
            positions = self.trader.get_open_positions()
            position = next((pos for pos in positions if pos['symbol'] == contract and float(pos['positionAmt']) != 0), None)
            if not position:
                self.log_message(f"No open position found for {contract} after trade execution")
                return

            entry_price = float(position['entryPrice'])
            leverage = float(params['leverage'])
            
            # Place SL/TP orders with the actual entry price
            try:
                success = self.trader.place_stop_loss_take_profit(
                    contract, entry_price, size, direction, 
                    params['stop_loss'], params['take_profit'], leverage
                )
                if success:
                    self.log_message(f"Successfully executed trade with TP={params['take_profit']}%, SL={params['stop_loss']}%")
                    
                    # Schedule position close after 1 hour
                    self.root.after(3600000, lambda: self.close_position_if_open(contract))
                else:
                    self.log_message("Failed to place SL/TP orders")
            except Exception as e:
                self.log_message(f"Error placing SL/TP orders: {e}")
        else:
            self.log_message("Failed to execute trade")
        
        self.update_positions_and_price()

    def close_position_if_open(self, contract):
        """Close a position if it's still open after the time limit."""
        try:
            positions = self.trader.get_open_positions()
            position = next((pos for pos in positions if pos['symbol'] == contract and float(pos['positionAmt']) != 0), None)
            
            if position:
                self.log_message(f"Time limit reached (1 hour) - Closing position for {contract}")
                size = float(position['positionAmt'])
                success = self.trader.close_position(contract=contract, size=size, price='0', tif='IOC')
                
                if success:
                    self.log_message(f"Successfully closed position after time limit: {contract}")
                else:
                    self.log_message(f"Failed to close position after time limit: {contract}")
                
                self.update_positions_and_price()
            else:
                self.log_message(f"No open position found for {contract} at time limit check")
        except Exception as e:
            self.log_message(f"Error in close_position_if_open for {contract}: {e}")

    def close_all_positions(self):
        self.log_message("Closing all positions...")
        success = self.trader.close_all_positions()
        if success:
            self.log_message("Successfully closed all positions")
        else:
            self.log_message("Failed to close some or all positions")
        self.update_positions_and_price()

    def toggle_auto_trading(self):
        """Toggle automatic trading mode."""
        if self.auto_trading.get():
            self.auto_status_label.config(text="Auto Trading: Enabled", foreground="green")
            self.log_message("Automatic trading enabled")
            # Set default parameters for auto trading
            self.contract_var.set("BTCUSDT")
            self.leverage_var.set("10")
            self.risk_var.set("10.0")
            self.sl_var.set("-5.0")
            self.tp_var.set("2.5")
            # Start auto trading monitoring
            self.check_auto_trading_conditions()
        else:
            self.auto_status_label.config(text="Auto Trading: Disabled", foreground="red")
            self.log_message("Automatic trading disabled")

    def check_auto_trading_conditions(self):
        """Check conditions for automatic trading."""
        if not self.auto_trading.get():
            return

        try:
            contract = self.contract_var.get()
            
            # Get klines data for MA calculations
            klines = self.trader.client.futures_klines(
                symbol=contract,
                interval='5m',
                limit=100
            )
            
            if not klines:
                return

            closes = pd.Series([float(k[4]) for k in klines])
            current_price = closes.iloc[-1]
            
            # Calculate moving averages
            ma5 = closes.rolling(window=5).mean().iloc[-1]
            ma20 = closes.rolling(window=20).mean().iloc[-1]
            ma50 = closes.rolling(window=50).mean().iloc[-1]
            
            # Calculate RSI
            rsi = self.calculate_rsi(closes).iloc[-1]
            
            # Get Coinglass flow data
            coinglass_data = self.load_coinglass_data()
            if coinglass_data:
                flow_5m = coinglass_data.get('5m', 0)
            else:
                flow_5m = 0

            # Check for open positions
            positions = self.trader.get_open_positions()
            has_open_position = any(
                float(pos['positionAmt']) != 0 
                for pos in positions 
                if pos['symbol'] == contract
            )

            if not has_open_position:
                # Long entry conditions
                long_conditions = (
                    ma5 > ma20 and
                    rsi < 20 and
                    flow_5m < -500000 and
                    current_price > ma50
                )

                # Short entry conditions
                short_conditions = (
                    ma5 < ma20 and
                    rsi > 80 and
                    flow_5m > 500000 and
                    current_price < ma50
                )

                if long_conditions:
                    self.direction_var.set("long")
                    self.execute_auto_trade()
                elif short_conditions:
                    self.direction_var.set("short")
                    self.execute_auto_trade()

            self.log_message(
                f"Auto Check - Price: {current_price:.2f}, MA5: {ma5:.2f}, "
                f"MA20: {ma20:.2f}, MA50: {ma50:.2f}, RSI: {rsi:.1f}, "
                f"Flow 5m: {flow_5m:,.0f}"
            )

        except Exception as e:
            self.log_message(f"Error in auto trading check: {str(e)}")
        finally:
            # Schedule next check in 5 seconds if auto trading is still enabled
            if self.auto_trading.get():
                self.root.after(5000, self.check_auto_trading_conditions)

    def execute_auto_trade(self):
        """Execute trade with automatic parameters."""
        try:
            params = {
                'contract': self.contract_var.get(),
                'direction': self.direction_var.get(),
                'price': '0',
                'tif': 'IOC',
                'leverage': float(self.leverage_var.get()),
                'risk_percentage': float(self.risk_var.get()),
                'stop_loss': float(self.sl_var.get()),
                'take_profit': float(self.tp_var.get())
            }

            self.log_message(f"Auto Trading - Executing {params['direction']} trade on {params['contract']}")
            success = self.trader.execute_trade(params)

            if success:
                self.log_message("Auto Trading - Trade executed successfully")
            else:
                self.log_message("Auto Trading - Trade execution failed")

        except Exception as e:
            self.log_message(f"Error in auto trade execution: {str(e)}")

    def schedule_updates(self):
        """Schedule periodic updates for various components."""
        # Update positions and price every 5 seconds
        self.root.after(5000, self.update_positions_and_price)
        
        # Update exchange flow data every 5 seconds
        self.root.after(5000, self.load_coinglass_data)
        
        # Schedule the next round of updates
        self.root.after(5000, self.schedule_updates)