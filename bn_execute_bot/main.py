import tkinter as tk
from tkinter import messagebox
import os
import sys
import subprocess
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

        trader = BinanceFuturesTrader(API_KEY, API_SECRET, testnet=True)
        root = tk.Tk()
        app = TradingGUI(root, trader)
        
        def on_closing():
            """Handle application shutdown."""
            if crawler_process:
                print("Terminating Coinglass crawler...")
                crawler_process.terminate()
                crawler_process.wait()  # Wait for the process to finish
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