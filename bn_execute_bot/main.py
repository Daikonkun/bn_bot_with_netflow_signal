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
from datetime import datetime

def start_coinglass_crawler():
    """Start the Coinglass crawler in a separate process with enhanced monitoring."""
    try:
        # Get the absolute path to btc_crawler.py using the current script's location
        current_dir = os.path.dirname(os.path.abspath(__file__))
        crawler_path = os.path.abspath(os.path.join(current_dir, '..', 'coinglass', 'btc_crawler.py'))
        
        print(f"Looking for crawler at: {crawler_path}")
        
        if not os.path.exists(crawler_path):
            print(f"Error: Crawler script not found at {crawler_path}")
            return None
            
        # Create logs directory if it doesn't exist
        logs_dir = os.path.join(os.path.dirname(crawler_path), 'logs')
        os.makedirs(logs_dir, exist_ok=True)
        
        # Set up log files with absolute paths
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stdout_log = os.path.join(logs_dir, f'crawler_output_{timestamp}.log')
        stderr_log = os.path.join(logs_dir, f'crawler_error_{timestamp}.log')
        
        print(f"Starting crawler process...")
        
        # Start the crawler script
        startupinfo = None
        if sys.platform == 'win32':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        
        # Start the crawler with output redirection to files
        with open(stdout_log, 'w', encoding='utf-8') as stdout_file, \
             open(stderr_log, 'w', encoding='utf-8') as stderr_file:
            
            crawler_process = subprocess.Popen(
                [sys.executable, crawler_path],
                stdout=stdout_file,
                stderr=stderr_file,
                startupinfo=startupinfo,
                cwd=os.path.dirname(crawler_path)  # Set working directory to crawler's directory
            )
            
            # Check if process started successfully
            time.sleep(2)
            if crawler_process.poll() is None:
                print(f"Started Coinglass crawler (PID: {crawler_process.pid})")
                print(f"Logs are being written to:\nOutput: {stdout_log}\nErrors: {stderr_log}")
                return crawler_process
            else:
                print("Error: Crawler process failed to start")
                return None
            
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