import requests
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import csv
import os
import schedule
import time
import logging
import re
import json
import random
from datetime import datetime, timedelta
from fake_useragent import UserAgent
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(os.path.dirname(__file__), 'crawler.log'), encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# Initialize fetch history
fetch_history = []

def get_random_delay(min_seconds=1, max_seconds=3):
    """Generate a random delay between min_seconds and max_seconds"""
    return random.uniform(min_seconds, max_seconds)

def setup_driver():
    """Set up Chrome driver with enhanced anti-detection measures"""
    try:
        chrome_options = Options()
        
        # Proper headless mode configuration
        chrome_options.add_argument('--headless=new')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--start-maximized')
        chrome_options.add_argument('--disable-notifications')
        chrome_options.add_argument('--disable-popup-blocking')
        
        # Add random user agent
        ua = UserAgent()
        user_agent = ua.random
        chrome_options.add_argument(f'user-agent={user_agent}')
        logging.info(f"Using User-Agent: {user_agent}")
        
        # Add additional headers
        chrome_options.add_argument('--accept-language=en-US,en;q=0.9')
        chrome_options.add_argument('--accept=text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8')
        
        # Disable automation flags
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Additional headless settings
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--mute-audio')
        
        try:
            # Try to use ChromeDriverManager
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=chrome_options)
        except Exception as e:
            logging.error(f"Error using ChromeDriverManager: {e}")
            # Fallback to local chromedriver if available
            local_driver_path = os.path.join(os.path.dirname(__file__), 'chromedriver.exe')
            if os.path.exists(local_driver_path):
                logging.info("Using local chromedriver")
                service = Service(local_driver_path)
                driver = webdriver.Chrome(service=service, options=chrome_options)
            else:
                raise Exception("No valid chromedriver found")
        
        # Additional automation detection evasion
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
                Object.defineProperty(navigator, 'plugins', {
                    get: () => [1, 2, 3, 4, 5]
                });
                window.chrome = {
                    runtime: {}
                };
            '''
        })
        
        logging.info("Chrome driver setup completed successfully in headless mode")
        return driver
    except Exception as e:
        logging.error(f"Failed to setup Chrome driver: {e}")
        raise

def wait_and_find_element(driver, by, selector, timeout=10, retries=3):
    for attempt in range(retries):
        try:
            element = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((by, selector))
            )
            return element
        except TimeoutException:
            if attempt < retries - 1:
                logging.warning(f"Attempt {attempt + 1} failed. Retrying...")
                time.sleep(get_random_delay())
            else:
                logging.error(f"Failed to find element after {retries} attempts")
                raise
        except Exception as e:
            logging.error(f"Error finding element: {str(e)}")
            raise

def adjust_timestamp(fetch_timestamp, refresh_interval=5):
    """
    根据刷新间隔调整时间戳，使其对齐到最近的 5 分钟时间点
    fetch_timestamp: 程序运行时间（datetime 对象）
    refresh_interval: 刷新间隔（分钟），默认为 5 分钟
    返回：调整后的时间戳（字符串，格式为 "DD Mon YYYY, HH:MM"）
    """
    # 计算分钟数，调整到最近的 5 分钟时间点
    minutes = fetch_timestamp.minute
    adjusted_minutes = (minutes // refresh_interval) * refresh_interval
    adjusted_time = fetch_timestamp.replace(minute=adjusted_minutes, second=0, microsecond=0)
    # 如果分钟数被调整到 60，则需要进位到下一小时
    if adjusted_minutes == 60:
        adjusted_time = adjusted_time.replace(minute=0) + timedelta(hours=1)
    return adjusted_time.strftime('%d %b %Y, %H:%M')

def infer_refresh_time(fetch_history):
    """
    根据 fetch_history 中的时间戳推断刷新时间点
    fetch_history: 包含 (fetch_timestamp, netflow) 的列表
    返回：推断的刷新间隔（分钟）
    """
    if len(fetch_history) < 3:
        return 5  # 默认 5 分钟
    # 获取最近三次获取数据的时间
    t1 = fetch_history[-3][0]
    t2 = fetch_history[-2][0]
    t3 = fetch_history[-1][0]
    # 计算时间差（分钟）
    delta1 = (t2 - t1).total_seconds() / 60
    delta2 = (t3 - t2).total_seconds() / 60
    # 推断刷新间隔（取平均值并四舍五入到最近的整数）
    avg_delta = (delta1 + delta2) / 2
    return round(avg_delta / 5) * 5  # 假设刷新间隔是 5 分钟的倍数

def fetch_data():
    """Fetch data with enhanced error handling and retry logic"""
    logging.info("Starting data fetch...")
    driver = None
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            if driver:
                driver.quit()
            driver = setup_driver()
            url = "https://www.coinglass.com/spot-inflow-outflow"
            driver.get(url)
            logging.info("Page loaded, waiting for data...")
            
            # Add random delay between 3-7 seconds
            time.sleep(random.uniform(3, 7))
            
            # Try different methods to find the BTC data
            selectors = [
                "//tr[contains(., 'BTC')]",
                "//div[contains(@class, 'coin-row') and contains(., 'BTC')]",
                "//table//tr[.//td[contains(text(), 'BTC')]]",
                "//div[contains(@class, 'MuiTableRow-root') and contains(., 'BTC')]",
                "//div[contains(text(), 'BTC')]//ancestor::tr",
                "//div[contains(@class, 'table')]//tr[contains(., 'BTC')]"
            ]
            
            btc_row = None
            for selector in selectors:
                try:
                    btc_row = wait_and_find_element(driver, By.XPATH, selector, timeout=5)
                    if btc_row:
                        logging.info(f"Found BTC data using selector: {selector}")
                        break
                except Exception as e:
                    logging.debug(f"Selector failed: {selector}, Error: {e}")
                    continue
            
            if not btc_row:
                raise NoSuchElementException("Could not find BTC data with any selector")
            
            # Extract timestamp
            timestamp = datetime.now().strftime("%d %b %Y, %H:%M")
            
            # Extract and validate netflow data
            netflow_data = btc_row.text.strip()
            if not netflow_data:
                raise ValueError("Empty netflow data")
                
            logging.info(f"Raw data captured: {netflow_data}")
            
            # Validate data format
            if '$' not in netflow_data:
                raise ValueError("Invalid data format: no currency values found")
            
            result = {
                'timestamp': timestamp,
                'netflow': 'BTC',
                'data': netflow_data
            }
            
            logging.info(f"Data extracted successfully: {result}")
            return result
            
        except Exception as e:
            retry_count += 1
            logging.error(f"Attempt {retry_count}/{max_retries} failed: {str(e)}")
            if retry_count < max_retries:
                time.sleep(10)  # Wait before retry
            else:
                logging.error("All retry attempts failed")
                return None
        finally:
            if driver:
                try:
                    driver.quit()
                    logging.info("Browser closed successfully")
                except Exception as e:
                    logging.warning(f"Error closing browser: {str(e)}")

def save_data(timestamp, netflow_data):
    """Save data to CSV file with proper formatting"""
    csv_file = 'btc_spot_netflow.csv'
    
    try:
        # Parse the netflow data
        data_parts = netflow_data.split()
        values = []
        market_cap = None
        
        # Extract values, looking for currency amounts
        for part in data_parts:
            if part.startswith('$') or part.startswith('-$'):
                # Remove the '$' and convert to numeric value
                value = part.replace('$', '')
                multiplier = 1
                
                # Handle different units (T, B, M, K)
                if value.endswith('T'):
                    multiplier = 1_000_000_000_000
                    value = value[:-1]
                elif value.endswith('B'):
                    multiplier = 1_000_000_000
                    value = value[:-1]
                elif value.endswith('M'):
                    multiplier = 1_000_000
                    value = value[:-1]
                elif value.endswith('K'):
                    multiplier = 1_000
                    value = value[:-1]
                
                # Convert to numeric value
                try:
                    numeric_value = float(value) * multiplier
                    values.append(str(numeric_value))
                except ValueError as e:
                    logging.warning(f"Could not convert value {value}: {str(e)}")
                    values.append(part)  # Keep original value if conversion fails
            
            elif part.startswith('Market') and len(data_parts) > data_parts.index(part) + 2:
                # Extract market cap
                cap_value = data_parts[data_parts.index(part) + 2]
                if cap_value.startswith('$'):
                    market_cap = cap_value
        
        if not values:
            logging.error("No valid netflow values found in the data")
            return
            
        # Create file with header if it doesn't exist
        if not os.path.exists(csv_file):
            with open(csv_file, 'w', newline='', encoding='utf-8') as file:
                writer = csv.writer(file)
                header = ['Timestamp', '5m', '15m', '30m', '1h', '2h', '4h', 
                         '6h', '8h', '12h', '24h', '7d', '15d', '30d', 'Market Cap']
                writer.writerow(header)
        
        # Append the data
        with open(csv_file, 'a', newline='', encoding='utf-8') as file:
            writer = csv.writer(file)
            row = [timestamp] + values
            if market_cap:
                row.append(market_cap)
            writer.writerow(row)
            logging.info(f"Data saved to CSV: {timestamp}, {len(values)} values")
            
    except Exception as e:
        logging.error(f"Error saving data to CSV: {str(e)}")
        logging.error(f"Raw netflow data: {netflow_data}")

def fetch_and_store_data():
    """Fetch and store data with proper error handling"""
    logging.info("Scheduled task triggered")
    try:
        result = fetch_data()
        if result:
            timestamp, netflow = result['timestamp'], result['data']
            save_data(timestamp, netflow)
            logging.info(f"Data saved successfully: {timestamp}")
        else:
            logging.warning("No valid data received, retrying in next cycle")
    except Exception as e:
        logging.error(f"Error in fetch_and_store_data: {str(e)}")

def main():
    """Main function with improved error handling and scheduling"""
    logging.info("Starting crawler main function")
    
    # Schedule the task to run every 5 minutes
    schedule.every(5).minutes.do(fetch_and_store_data)
    
    # Initial run
    retry_count = 0
    max_retries = 3
    initial_success = False
    
    while retry_count < max_retries and not initial_success:
        try:
            logging.info("Attempting initial data fetch...")
            result = fetch_and_store_data()
            if result:
                initial_success = True
                logging.info("Initial data fetch successful")
            else:
                retry_count += 1
                logging.warning(f"Initial fetch attempt {retry_count} failed")
                time.sleep(10)
        except Exception as e:
            retry_count += 1
            logging.error(f"Error during initial fetch attempt {retry_count}: {str(e)}")
            time.sleep(10)
    
    if not initial_success:
        logging.error("Failed to fetch initial data after maximum retries")
        return
    
    # Main loop
    logging.info("Starting main loop")
    consecutive_errors = 0
    max_consecutive_errors = 5
    
    while True:
        try:
            # Run pending tasks
            schedule.run_pending()
            
            # Check if the data file exists and is being updated
            csv_file = os.path.join(os.path.dirname(__file__), 'btc_spot_netflow.csv')
            if os.path.exists(csv_file):
                last_modified = os.path.getmtime(csv_file)
                current_time = time.time()
                if current_time - last_modified > 600:  # 10 minutes
                    logging.warning("Data file hasn't been updated in 10 minutes")
                    result = fetch_and_store_data()
                    if result:
                        consecutive_errors = 0
            
            # Sleep for a short time
            time.sleep(1)
            consecutive_errors = 0  # Reset error counter on success
            
        except Exception as e:
            consecutive_errors += 1
            logging.error(f"Error in main loop: {str(e)}")
            if consecutive_errors >= max_consecutive_errors:
                logging.critical(f"Too many consecutive errors ({consecutive_errors}). Restarting crawler...")
                # Try to restart by running initial fetch again
                try:
                    result = fetch_and_store_data()
                    if result:
                        consecutive_errors = 0
                        logging.info("Successfully recovered from errors")
                        continue
                except Exception as restart_error:
                    logging.error(f"Failed to restart after errors: {str(restart_error)}")
                break
            time.sleep(5)

if __name__ == "__main__":
    logging.info("Crawler starting up")
    while True:  # Outer loop for automatic restart
        try:
            main()
            logging.error("Main loop exited, restarting in 30 seconds...")
            time.sleep(30)
        except KeyboardInterrupt:
            logging.info("Crawler stopped by user")
            break
        except Exception as e:
            logging.error(f"Fatal error: {str(e)}")
            logging.info("Restarting in 30 seconds...")
            time.sleep(30)