import time
from scraper import GeMScraper
import logging

logging.basicConfig(level=logging.DEBUG)

if __name__ == "__main__":
    s = GeMScraper()
    start = time.time()
    url = "https://mkp.gem.gov.in/computer-displays-interactive-panels-with-cpu/"
    print(f"Scraping {url}...")
    try:
        res = s.scrape(url, "Uttar Pradesh")
        print(f"Scrape completed in {time.time()-start:.2f} seconds")
        print(f"Products: {len(res['products'])}, Filters: {len(res['filters'])}")
    except Exception as e:
        print(f"Failed: {e}")
