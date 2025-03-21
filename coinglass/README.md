# Bitcoin Spot Netflow Crawler

A Python-based web crawler that automatically fetches and tracks Bitcoin spot inflow/outflow data from CoinGlass.com. The script collects data at regular intervals and stores it in a structured CSV format for analysis.

## Features

- Automated data collection from CoinGlass.com's spot inflow/outflow page
- Collects Bitcoin netflow data across multiple timeframes (5m to 30d)
- Tracks market capitalization
- Anti-detection measures including random user agent rotation
- Robust error handling and retry mechanisms
- Scheduled data collection (every 5 minutes)
- Data saved in CSV format for easy analysis

## Requirements

- Python 3.7+
- Chrome browser
- ChromeDriver (compatible with your Chrome version)

## Dependencies

```
selenium==4.15.2
schedule==1.2.2
fake-useragent==2.1.0
beautifulsoup4==4.12.2
requests==2.31.0
```

## Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/bitcoin-spot-netflow-crawler.git
cd bitcoin-spot-netflow-crawler
```

2. Install required packages:
```bash
pip install -r requirements.txt
```

3. Download ChromeDriver:
   - Visit [ChromeDriver Downloads](https://sites.google.com/chromium.org/driver/)
   - Download the version matching your Chrome browser
   - Extract and place `chromedriver.exe` in the specified path in the script

4. Update the ChromeDriver path in `btc_crawler.py`:
```python
service = Service(r'path/to/your/chromedriver.exe')
```

## Usage

Run the script:
```bash
python btc_crawler.py
```

The script will:
1. Start collecting data immediately
2. Create a CSV file named `btc_spot_netflow.csv`
3. Log activities to `crawler.log`
4. Continue running and collecting data every 5 minutes

## Output Format

The CSV file contains the following columns:
- Timestamp
- 5m netflow
- 15m netflow
- 30m netflow
- 1h netflow
- 2h netflow
- 4h netflow
- 6h netflow
- 8h netflow
- 12h netflow
- 24h netflow
- 7d netflow
- 15d netflow
- 30d netflow
- Market Cap

All monetary values are converted to numeric format (in USD).

## Logging

The script logs all activities to `crawler.log`, including:
- Data fetch attempts
- Successful data captures
- Errors and retries
- Data saving operations

## Error Handling

The script includes robust error handling for:
- Network issues
- Website structure changes
- Data parsing errors
- File operations
- Browser automation issues

## Contributing

Feel free to fork the repository and submit pull requests. For major changes, please open an issue first to discuss what you would like to change.

## License

[MIT](https://choosealicense.com/licenses/mit/)

## Disclaimer

This script is for educational purposes only. Please review and comply with CoinGlass.com's terms of service before use. The author is not responsible for any misuse of this tool. 