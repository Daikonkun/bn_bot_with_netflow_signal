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
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('crawler.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# 用于存储最近三次获取数据的时间和 Netflow 数据
fetch_history = []

def get_random_delay(min_seconds=1, max_seconds=3):
    """Generate a random delay between min_seconds and max_seconds"""
    return random.uniform(min_seconds, max_seconds)

def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--ignore-certificate-errors')
    chrome_options.add_argument('--ignore-ssl-errors')
    chrome_options.add_argument('--disable-web-security')
    chrome_options.add_argument('--allow-running-insecure-content')
    chrome_options.add_argument('--disable-software-rasterizer')
    
    # Add random user agent
    ua = UserAgent()
    chrome_options.add_argument(f'user-agent={ua.random}')
    
    # Disable automation flags
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # Use ChromeDriverManager to handle driver installation
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    # Additional automation detection evasion
    driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
        'source': '''
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        '''
    })
    
    return driver

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
    logging.info("Starting data fetch...")
    driver = None
    try:
        driver = setup_driver()
        url = "https://www.coinglass.com/spot-inflow-outflow"
        driver.get(url)
        logging.info("Page loaded, waiting for data...")
        time.sleep(5)  # Initial wait for page load

        # Try multiple selectors for the BTC data row
        selectors = [
            "//tr[contains(., 'BTC')]",  # XPath for any row containing BTC
            "//div[contains(@class, 'coin-row') and contains(., 'BTC')]",  # Alternative XPath
            "//table//tr[.//td[contains(text(), 'BTC')]]",  # Another alternative
            "//div[contains(@class, 'MuiTableRow-root') and contains(., 'BTC')]"  # MUI specific
        ]

        btc_row = None
        for selector in selectors:
            try:
                btc_row = wait_and_find_element(driver, By.XPATH, selector)
                if btc_row:
                    break
            except:
                continue

        if not btc_row:
            raise NoSuchElementException("Could not find BTC data row with any selector")

        # Extract timestamp
        timestamp = datetime.now().strftime("%d %b %Y, %H:%M")
        logging.info(f"Timestamp captured: {timestamp}")

        # Extract netflow data
        netflow_data = btc_row.text.strip()
        logging.info(f"Raw data captured: {netflow_data}")

        # Process and store the data
        result = {
            'timestamp': timestamp,
            'netflow': 'BTC',
            'data': netflow_data
        }
        
        logging.info(f"Data extracted successfully: {result}")
        return result

    except Exception as e:
        logging.error(f"Error during data fetch: {str(e)}")
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
    """抓取并存储数据"""
    logging.info("定时任务触发")
    result = fetch_data()
    if result:
        timestamp, netflow = result['timestamp'], result['data']
        save_data(timestamp, netflow)
        logging.info(f"成功保存数据: {timestamp}")
    else:
        logging.warning("未获取到有效数据，未保存")

# 设置定时任务，每 5 分钟运行一次
schedule.every(5).minutes.do(fetch_and_store_data)

def main():
    logging.info("Script started")
    try:
        data = fetch_data()
        if data:
            logging.info(f"Successfully fetched data: {data}")
            # Save the data to CSV
            save_data(data['timestamp'], data['data'])
        else:
            logging.error("Failed to fetch data")
    except Exception as e:
        logging.error(f"Main execution error: {str(e)}")
    logging.info("Script completed")

if __name__ == "__main__":
    logging.info("爬虫启动")
    main()
    while True:
        schedule.run_pending()
        time.sleep(1)