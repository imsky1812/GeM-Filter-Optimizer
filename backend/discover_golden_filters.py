import requests
import json
import time

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
})

url = "https://mkp.gem.gov.in/medical-equipment-and-accessories-and-supplies-dental-equipment-and-supplies-dental-clinical-furniture-dental-chair/search?page=1&format=json"

try:
    print(f"Fetching {url}...")
    r = session.get(url, timeout=15)
    print(f"Status code: {r.status_code}")
    data = r.json()
    
    facets = data.get("facets", {})
    print(f"Found {len(facets)} facet categories.")
    
    for category_code, category_data in facets.items():
        print(f"\n--- Category: {category_code} ---")
        if isinstance(category_data, list):
            for f in category_data:
                name = f.get("name", "")
                code = f.get("code", "")
                print(f"  Filter: {name} ({code})")
                if "golden" in str(f).lower() or "l1" in str(f).lower() or "mse" in name.lower() or "make in india" in name.lower():
                    print(f"  *** POTENTIAL GOLDEN FILTER ***: {json.dumps(f)}")
        elif isinstance(category_data, dict):
            for f_code, f in category_data.items():
                name = f.get("name", "")
                code = f.get("code", "")
                print(f"  Filter: {name} ({code})")
                if "golden" in str(f).lower() or "l1" in str(f).lower() or "mse" in name.lower() or "make in india" in name.lower():
                    print(f"  *** POTENTIAL GOLDEN FILTER ***: {json.dumps(f)}")
except Exception as e:
    print(f"Error: {e}")
