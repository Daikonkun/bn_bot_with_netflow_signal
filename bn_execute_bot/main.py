import tkinter as tk
from tkinter import messagebox
import os
import sys
import subprocess
import threading
import time
from dotenv import load_dotenv
from trader import BinanceFuturesTrader
from gui import TradingGUI

def start_coinglass_crawler():
    """Start the Coinglass crawler in a separate process."""
    try:
        # Get the absolute path to btc_crawler.py
        crawler_path = os.path.abspath(os.path.join('..', 'coinglass', 'btc_crawler.py'))
        
        # Start the crawler script
        crawler_process = subprocess.Popen([sys.executable, crawler_path],
                                         stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE,
                                         creationflags=subprocess.CREATE_NEW_CONSOLE)  # New window for Windows
        
        print(f"Started Coinglass crawler (PID: {crawler_process.pid})")
        return crawler_process
    except Exception as e:
        print(f"Error starting Coinglass crawler: {e}")
        return None

def strategy_loop(trader, stop_event):
    """Run the trading strategy in a loop."""
    try:
        print("Starting strategy execution loop...")
        while not stop_event.is_set():
            try:
                # Execute strategy for BTCUSDT
                trader.execute_strategy("BTCUSDT")
                
                # Wait for 5 minutes before next check (matching the timeframe)
                for _ in range(30):  # 30 * 10 seconds = 5 minutes
                    if stop_event.is_set():
                        break
                    time.sleep(10)  # Check every 10 seconds if we need to stop
                    
            except Exception as e:
                print(f"Error in strategy loop: {e}")
                time.sleep(10)  # Wait before retrying
                
    except Exception as e:
        print(f"Fatal error in strategy loop: {e}")
    finally:
        print("Strategy execution loop stopped.")

def main():
    try:
        # Start Coinglass crawler first
        crawler_process = start_coinglass_crawler()
        
        # Load environment variables from .env file
        load_dotenv()

        API_KEY = os.getenv('BINANCE_API_KEY')
        API_SECRET = os.getenv('BINANCE_API_SECRET')
        if not API_KEY or not API_SECRET:
            raise ValueError("API keys not found in environment variables. Please set BINANCE_API_KEY and BINANCE_API_SECRET in a .env file or system environment.")

        # Create trader instance
        trader = BinanceFuturesTrader(API_KEY, API_SECRET, testnet=True)
        
        # Create stop event for strategy thread
        stop_event = threading.Event()
        
        # Start strategy thread
        strategy_thread = threading.Thread(target=strategy_loop, args=(trader, stop_event))
        strategy_thread.daemon = True  # Thread will be terminated when main program exits
        strategy_thread.start()
        
        # Create and start GUI
        root = tk.Tk()
        app = TradingGUI(root, trader)
        
        def on_closing():
            """Handle application shutdown."""
            try:
                # Stop strategy loop
                print("Stopping strategy execution...")
                stop_event.set()
                strategy_thread.join(timeout=5)  # Wait up to 5 seconds for thread to finish
                
                # Stop Coinglass crawler
                if crawler_process:
                    print("Terminating Coinglass crawler...")
                    crawler_process.terminate()
                    crawler_process.wait()  # Wait for the process to finish
                
                # Cleanup trader resources
                trader.cleanup()
                
                # Destroy GUI
                root.destroy()
                
            except Exception as e:
                print(f"Error during shutdown: {e}")
                root.destroy()
        
        # Bind the window close event
        root.protocol("WM_DELETE_WINDOW", on_closing)
        root.mainloop()

    except ValueError as e:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Error", str(e))
        root.destroy()
    except Exception as e:
        print(f"Unexpected error in main(): {e}")
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Error", f"Unexpected error: {str(e)}")
        root.destroy()
    finally:
        # Ensure crawler is terminated if something goes wrong
        if 'crawler_process' in locals() and crawler_process:
            crawler_process.terminate()

if __name__ == "__main__":
    main()