"""Test uppercase variations."""
import sys, json, os

sys.path.insert(0, "backend")
from scraper import GeMScraper

scraper = GeMScraper()
url = "https://mkp.gem.gov.in/furniture-and-furnishings-accommodation-furniture-furniture-revolving-chair-v5-/search"

# Test different variations in UPPERCASE
cases = [
    # Seat upholstery material (C6065E)
    ("C6065E", "MESH"),
    ("C6065E", "FABRICS"),
    ("C6065E", "POLYESTER"),
    ("C6065E", "FABRIC"),
    ("C6065E", "MESH FABRICS"),
    ("C6065E", "POLYESTER FABRIC"),
    
    # Backrest Height (C4978E)
    ("C4978E", "MID"),
    ("C4978E", "LOW"),
    ("C4978E", "BACK"),
    ("C4978E", "MID-BACK"),
    ("C4978E", "LOW-BACK"),
    
    # Type of Chair (C2168E)
    ("C2168E", "REVOLVING"),
    ("C2168E", "CHAIR"),
    ("C2168E", "WHEELS"),
    ("C2168E", "REVOLVING CHAIR OF ADJUSTABLE HEIGHT WITH WHEELS"),
    
    # Seat Height Mechanism (C4048E)
    ("C4048E", "PNEUMATIC"),
    ("C4048E", "HYDRAULIC"),
    ("C4048E", "PNEUMATIC MECHANISM (GAS LIFT)"),
    ("C4048E", "HYDRAULIC MECHANISM"),
    
    # Backrest Width (C3029E)
    ("C3029E", "LOW"),
    ("C3029E", "MEDIUM"),
    ("C3029E", "HIGH"),
]

print("=== TESTING UPPERCASE TOKENS ===")
for key, val in cases:
    params = {key: val, "format": "json"}
    r = scraper._session.get(url, params=params)
    try:
        total = r.json().get("number_of_results", 0)
        if total > 0:
            print(f"SUCCESS: {key}={repr(val)} -> total={total}")
        else:
            print(f"  0 results: {key}={repr(val)}")
    except Exception as e:
        print(f"  {key}={repr(val)} -> failed: {e}")
print("Done testing.")














